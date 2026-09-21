"""Административные действия над пользователем (DASH-8).

Карточка ``/users/{uid}`` умеет приостанавливать мониторинг, удалять врача
или пациента и сбрасывать состояние FSM. Каждое действие выполняется только
с явным подтверждением и пишется в ``audit_log``.

Действия, меняющие состав мониторинга, обновляют кеш данных менеджера:
иначе цикл мониторинга продолжил бы работать по устаревшему снимку.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from src.services.audit import log_action


@dataclass(frozen=True)
class ActionParam:
    """Параметр действия, который вводит администратор."""

    name: str
    label: str
    required: bool = False


@dataclass(frozen=True)
class UserAction:
    """Описание действия над пользователем."""

    name: str
    title: str
    description: str
    params: tuple[ActionParam, ...] = field(default_factory=tuple)
    audit_action: str = "user_action"


ACTIONS: dict[str, UserAction] = {
    "pause": UserAction(
        name="pause",
        title="Пауза мониторинга",
        description=(
            "Приостанавливает проверки для пользователя. Цепочки "
            "пациент-врач сохраняются."
        ),
        audit_action="user_pause",
    ),
    "resume": UserAction(
        name="resume",
        title="Возобновить мониторинг",
        description="Снимает паузу и возвращает пользователя в цикл проверок.",
        audit_action="user_resume",
    ),
    "delete_doctor": UserAction(
        name="delete_doctor",
        title="Удалить врача",
        description="Убирает врача из мониторинга пользователя по всем пациентам.",
        params=(ActionParam("d_id", "d_id врача", required=True),),
        audit_action="user_doctor_deleted",
    ),
    "delete_patient": UserAction(
        name="delete_patient",
        title="Удалить пациента",
        description="Убирает пациента из мониторинга пользователя.",
        params=(ActionParam("p_id", "p_id пациента", required=True),),
        audit_action="user_patient_deleted",
    ),
    "reset_fsm": UserAction(
        name="reset_fsm",
        title="Сброс состояния диалога",
        description=(
            "Удаляет состояние FSM пользователя в Redis: следующий шаг "
            "диалога начнётся заново."
        ),
        audit_action="user_fsm_reset",
    ),
}


def action_view(action: UserAction) -> dict[str, Any]:
    """Представление действия для страницы и API."""
    return {
        "name": action.name,
        "title": action.title,
        "description": action.description,
        "params": [
            {"name": param.name, "label": param.label, "required": param.required}
            for param in action.params
        ],
    }


def _require_param(action: UserAction, params: dict[str, str], name: str) -> str:
    """Возвращает обязательный параметр действия.

    Raises:
        ValueError: Параметр не заполнен.
    """
    value = str(params.get(name, "") or "").strip()
    if not value:
        label = next(
            (param.label for param in action.params if param.name == name), name
        )
        raise ValueError(f"Параметр «{label}» обязателен.")
    return value


async def run_action(
    db: Any,
    uid: str,
    name: str,
    params: dict[str, str],
    confirm: bool,
    actor: str,
) -> dict[str, Any]:
    """Выполняет действие над пользователем и пишет его в журнал.

    Args:
        db: Менеджер БД (кеш и репозитории).
        uid: Идентификатор пользователя.
        name: Имя действия из реестра.
        params: Значения параметров.
        confirm: Подтверждение администратора.
        actor: Кто выполняет действие.

    Returns:
        Результат со статусом и, при необходимости, счётчиком изменений.

    Raises:
        KeyError: Действия нет в реестре.
        ValueError: Параметры не прошли проверку.
    """
    action = ACTIONS.get(name)
    if action is None:
        raise KeyError(name)

    if not confirm:
        await log_action(
            db, actor, "user_action_confirm_required", target=uid, action_name=name
        )
        return {
            "status": "confirm_required",
            "action": name,
            "message": "Действие требует подтверждения.",
        }

    unknown = set(params) - {param.name for param in action.params}
    if unknown:
        raise ValueError(f"Неизвестные параметры: {', '.join(sorted(unknown))}")

    changed = 0
    message = ""

    if name == "pause":
        await db.set_user_paused(uid, True)
        changed = 1
        message = "Мониторинг приостановлен."
    elif name == "resume":
        await db.set_user_paused(uid, False)
        changed = 1
        message = "Мониторинг возобновлён."
    elif name == "delete_doctor":
        d_id = _require_param(action, params, "d_id")
        changed = await db.delete_doctor(uid, d_id)
        message = f"Удалено цепочек: {changed}."
        await db.refresh_cache()
    elif name == "delete_patient":
        p_id = _require_param(action, params, "p_id")
        changed = await db.delete_patient(uid, p_id)
        message = (
            "Пациент удалён из мониторинга."
            if changed
            else "Пациент не найден: ничего не удалено."
        )
        await db.refresh_cache()
    elif name == "reset_fsm":
        changed = await _reset_fsm(uid)
        message = f"Удалено ключей FSM: {changed}."

    result = {
        "status": "ok",
        "action": name,
        "uid": uid,
        "changed": changed,
        "message": message,
    }

    await log_action(
        db,
        actor,
        action.audit_action,
        target=uid,
        action_name=name,
        changed=changed,
        params={key: value for key, value in params.items() if value},
    )
    return result


async def _reset_fsm(uid: str) -> int:
    """Удаляет состояние FSM пользователя в Redis.

    Ключи aiogram по умолчанию: ``fsm:<bot_id>:<chat_id>:<user_id>:state``
    и ``:data``; в личном чате ``chat_id`` совпадает с ``user_id``.

    Returns:
        Сколько ключей удалено (0, если Redis недоступен).
    """
    from src.utils.redis import RedisClient

    if not uid.isdigit():
        # uid приходит из URL: glob-символы в нём увели бы SCAN на чужие
        # ключи, поэтому нечисловой идентификатор не обрабатываем вовсе.
        logger.warning("Сброс FSM: uid не похож на Telegram ID — пропуск")
        return 0

    try:
        client = await RedisClient.get_instance()
        if not client.is_available:
            logger.warning("Сброс FSM: Redis недоступен, ключи не удалены")
            return 0

        # Ключи aiogram по умолчанию: fsm:<bot_id>:<chat_id>:<user_id>:<suffix>.
        # В личном чате chat_id == user_id == uid, поэтому шаблон фиксирует обе
        # позиции: состояния чужих чатов под него не попадают.
        pattern = f"fsm:*:{uid}:{uid}:*"
        deleted = 0
        batch: list[str] = []
        # SCAN вместо KEYS: KEYS блокирует Redis на всё время обхода.
        async for key in client.client.scan_iter(match=pattern, count=100):
            batch.append(key)
            if len(batch) >= 100:
                deleted += int(await client.delete(*batch) or 0)
                batch.clear()
        if batch:
            deleted += int(await client.delete(*batch) or 0)
        return deleted
    except Exception:
        logger.opt(exception=True).warning("Сброс FSM: не удалось удалить ключи")
        return 0
