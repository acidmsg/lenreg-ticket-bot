"""Запись действий администратора в журнал audit_log (DASH-2).

Единая точка логирования: действия дашборда (вход, сканирование, бэкапы,
смена пароля) не должны падать из-за сбоя журнала, поэтому ошибки записи
только логируются.
"""

from __future__ import annotations

from typing import Any

from loguru import logger


def actor_from_request(request: Any) -> str:
    """Возвращает логин администратора из запроса.

    Args:
        request: FastAPI-запрос (логин кладёт middleware сессии).

    Returns:
        Логин администратора или ``unknown``, если сессия не определена.
    """
    state = getattr(request, "state", None)
    user = getattr(state, "dashboard_user", None)
    return str(user) if user else "unknown"


async def log_action(
    db: Any,
    actor: str,
    action: str,
    target: str = "",
    **payload: Any,
) -> None:
    """Пишет действие администратора в журнал.

    Args:
        db: Фасад БД (``app.state.db``).
        actor: Автор действия (логин, ``system``, ``bot``).
        action: Машиночитаемый код действия.
        target: Объект действия.
        **payload: Дополнительные данные события.
    """
    try:
        await db.audit.add_event(
            actor=actor, action=action, target=target, payload=dict(payload)
        )
    except Exception as exc:
        logger.warning(f"audit: не удалось записать действие {action}: {exc}")
