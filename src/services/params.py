"""Реестр параметров конфигурации для страницы «Параметры» (DASH-3).

Описывает параметры, которые лежат в таблице ``config`` БД: тип, границы,
группу, способ применения и предупреждения об опасных значениях.

Приоритет источников — **.env → БД → runtime**:

1. ``.env`` (объект ``settings``) задаёт базовое значение при старте;
2. значение из таблицы ``config`` перекрывает ``.env`` (его правит админ);
3. runtime-состояние — то, что реально читает сервис в текущем цикле
   (например, ``doctor_scan_enabled``).

Применение без рестарта возможно там, где сервис перечитывает значение сам
(``apply_mode="hot"``) или на следующей итерации цикла (``apply_mode="next_cycle"``).
Параметры, которые читаются только при инициализации, помечены ``restart``.
"""

from __future__ import annotations

import asyncio
import math
import re
import weakref
from dataclasses import dataclass
from typing import Any, Literal

from loguru import logger

from src.config import (
    CONFIG_KEY_ADMIN_IDS,
    CONFIG_KEY_API_BASE_URL,
    CONFIG_KEY_API_TIMEOUT,
    CONFIG_KEY_CHECK_INTERVAL,
    CONFIG_KEY_CLEANUP_INTERVAL,
    CONFIG_KEY_CSRF_TOKEN,
    CONFIG_KEY_DEFAULT_BIRTHDAY,
    CONFIG_KEY_DEFAULT_CLINIC_ID,
    CONFIG_KEY_DISCOVERY_INTERVAL,
    CONFIG_KEY_DISCOVERY_PATIENT_ADULT,
    CONFIG_KEY_DISCOVERY_PATIENT_CHILD,
    CONFIG_KEY_ENVIRONMENT,
    CONFIG_KEY_ERROR_NOTIFY_ENABLED,
    CONFIG_KEY_MESSAGE_TTL_SECONDS,
    CONFIG_KEY_REFERER_URL,
    CONFIG_KEY_SLOT_COMPACT_THRESHOLD,
    CONFIG_KEY_SLOT_DETAIL_THRESHOLD,
    CONFIG_KEY_SLOT_THRESHOLD_ABSOLUTE,
    CONFIG_KEY_SLOT_THRESHOLD_PERCENTAGE,
    CONFIG_KEY_USER_RATE_LIMIT_MAX,
    CONFIG_KEY_USER_RATE_LIMIT_PERIOD,
    settings,
)

# Порядок разрешения значения параметра (документируется на странице).
RESOLUTION_ORDER = (".env", "БД", "runtime")

ApplyMode = Literal["hot", "next_cycle", "restart"]

# Ключ, который живёт только в БД (в .env его нет).
DOCTOR_SCAN_KEY = "doctor_scan_enabled"

# Маска секретного значения в UI, API и журнале.
MASK = "***"

# Ключи, переопределённые в текущем процессе (источник «runtime»).
_RUNTIME_OVERRIDES: set[str] = set()

# Сериализация изменений параметров: чтение-изменение-запись без гонок.
_param_locks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
    weakref.WeakKeyDictionary()
)


def _set_lock() -> asyncio.Lock:
    """Ленивый per-loop ``asyncio.Lock`` для изменений параметров.

    Модульная область не имеет running loop'а, поэтому примитив создаётся при
    первом обращении в текущем loop'е (правило 2,
    ``specs/design/event-loop-ownership.md``); реестр — ``WeakKeyDictionary``,
    чтобы loop не удерживался ссылкой.
    """
    loop = asyncio.get_running_loop()
    lock = _param_locks.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _param_locks[loop] = lock
    return lock


@dataclass(frozen=True)
class ParamSpec:
    """Описание параметра конфигурации."""

    key: str
    title: str
    description: str
    kind: Literal["int", "float", "bool", "str", "enum"]
    group: str
    apply_mode: ApplyMode = "next_cycle"
    settings_attr: str | None = None
    """Имя атрибута ``settings``; ``None`` — источник только БД."""
    min_value: float | None = None
    max_value: float | None = None
    choices: tuple[str, ...] = ()
    danger: bool = False
    """Опасный параметр: правка требует понимания последствий."""
    secret: bool = False
    """Секрет: значение маскируется в UI/API и не пишется в журнал."""
    db_default: str | None = None
    """Значение по умолчанию для параметров, живущих только в БД."""
    change_warning: str | None = None
    """Предупреждение, показываемое только при отличии от действующего значения."""


PARAMS: dict[str, ParamSpec] = {
    # ── Мониторинг ────────────────────────────────────────────
    CONFIG_KEY_CHECK_INTERVAL: ParamSpec(
        key=CONFIG_KEY_CHECK_INTERVAL,
        title="Интервал проверки слотов",
        description="Как часто опрашивать API по отслеживаемым врачам, секунды.",
        kind="int",
        group="Мониторинг",
        settings_attr="CHECK_INTERVAL",
        min_value=30,
        max_value=86400,
    ),
    CONFIG_KEY_DISCOVERY_INTERVAL: ParamSpec(
        key=CONFIG_KEY_DISCOVERY_INTERVAL,
        title="Интервал поиска врачей",
        description="Период фонового сканирования врачей по клиникам, секунды.",
        kind="int",
        group="Мониторинг",
        settings_attr="DISCOVERY_INTERVAL",
        min_value=60,
        max_value=86400,
    ),
    CONFIG_KEY_API_TIMEOUT: ParamSpec(
        key=CONFIG_KEY_API_TIMEOUT,
        title="Таймаут API",
        description="Сколько ждать ответа zdrav.lenreg.ru, секунды.",
        kind="float",
        group="Мониторинг",
        apply_mode="restart",
        settings_attr="API_TIMEOUT",
        min_value=1,
        max_value=120,
    ),
    CONFIG_KEY_MESSAGE_TTL_SECONDS: ParamSpec(
        key=CONFIG_KEY_MESSAGE_TTL_SECONDS,
        title="Время жизни уведомлений",
        description="Через сколько секунд удалять отправленные сообщения.",
        kind="int",
        group="Мониторинг",
        settings_attr="MESSAGE_TTL_SECONDS",
        min_value=3600,
        max_value=31536000,
    ),
    CONFIG_KEY_CLEANUP_INTERVAL: ParamSpec(
        key=CONFIG_KEY_CLEANUP_INTERVAL,
        title="Интервал очистки",
        description="Как часто запускать очистку старых сообщений, секунды.",
        kind="int",
        group="Мониторинг",
        settings_attr="CLEANUP_INTERVAL",
        min_value=60,
        max_value=86400,
    ),
    DOCTOR_SCAN_KEY: ParamSpec(
        key=DOCTOR_SCAN_KEY,
        title="Плановое сканирование врачей",
        description=(
            "Включено ли фоновое сканирование. Хранится только в БД и "
            "перечитывается на каждой итерации цикла поиска."
        ),
        kind="bool",
        group="Мониторинг",
        apply_mode="next_cycle",
        db_default="1",
    ),
    # ── Пороги слотов ─────────────────────────────────────────
    CONFIG_KEY_SLOT_THRESHOLD_ABSOLUTE: ParamSpec(
        key=CONFIG_KEY_SLOT_THRESHOLD_ABSOLUTE,
        title="Порог слотов (абсолютный)",
        description="Сообщать, если свободных слотов не меньше этого числа.",
        kind="int",
        group="Пороги слотов",
        settings_attr="SLOT_THRESHOLD_ABSOLUTE",
        min_value=1,
        max_value=100,
    ),
    CONFIG_KEY_SLOT_THRESHOLD_PERCENTAGE: ParamSpec(
        key=CONFIG_KEY_SLOT_THRESHOLD_PERCENTAGE,
        title="Порог слотов (доля)",
        description="Сообщать при доле свободных слотов не меньше указанной (0–1).",
        kind="float",
        group="Пороги слотов",
        settings_attr="SLOT_THRESHOLD_PERCENTAGE",
        min_value=0.01,
        max_value=1.0,
    ),
    CONFIG_KEY_SLOT_DETAIL_THRESHOLD: ParamSpec(
        key=CONFIG_KEY_SLOT_DETAIL_THRESHOLD,
        title="Порог детального списка",
        description="До какого числа слотов показывать подробный список.",
        kind="int",
        group="Пороги слотов",
        settings_attr="SLOT_DETAIL_THRESHOLD",
        min_value=1,
        max_value=100,
    ),
    CONFIG_KEY_SLOT_COMPACT_THRESHOLD: ParamSpec(
        key=CONFIG_KEY_SLOT_COMPACT_THRESHOLD,
        title="Порог компактного режима",
        description="С какого числа слотов переключаться на компактный вывод.",
        kind="int",
        group="Пороги слотов",
        settings_attr="SLOT_COMPACT_THRESHOLD",
        min_value=1,
        max_value=100,
    ),
    # ── Клиника и API ─────────────────────────────────────────
    CONFIG_KEY_DEFAULT_CLINIC_ID: ParamSpec(
        key=CONFIG_KEY_DEFAULT_CLINIC_ID,
        title="Клиника по умолчанию",
        description="ID клиники, с которой работает бот.",
        kind="str",
        group="Клиника и API",
        settings_attr="DEFAULT_CLINIC_ID",
        danger=True,
        change_warning="Смена клиники меняет выдачу для всех пользователей.",
    ),
    CONFIG_KEY_DEFAULT_BIRTHDAY: ParamSpec(
        key=CONFIG_KEY_DEFAULT_BIRTHDAY,
        title="Дата рождения по умолчанию",
        description="Дата рождения для регистрации (ГГГГ-ММ-ДД).",
        kind="str",
        group="Клиника и API",
        settings_attr="DEFAULT_BIRTHDAY",
    ),
    CONFIG_KEY_DISCOVERY_PATIENT_ADULT: ParamSpec(
        key=CONFIG_KEY_DISCOVERY_PATIENT_ADULT,
        title="Пациент для поиска (взрослый)",
        description="ID пациента, от имени которого ищутся врачи.",
        kind="str",
        group="Клиника и API",
        settings_attr="DISCOVERY_PATIENT_ID_ADULT",
        danger=True,
    ),
    CONFIG_KEY_DISCOVERY_PATIENT_CHILD: ParamSpec(
        key=CONFIG_KEY_DISCOVERY_PATIENT_CHILD,
        title="Пациент для поиска (детский)",
        description="ID детского пациента для поиска врачей.",
        kind="str",
        group="Клиника и API",
        settings_attr="DISCOVERY_PATIENT_ID_CHILD",
    ),
    CONFIG_KEY_API_BASE_URL: ParamSpec(
        key=CONFIG_KEY_API_BASE_URL,
        title="Базовый URL API",
        description="Адрес API клиники.",
        kind="str",
        group="Клиника и API",
        settings_attr="API_BASE_URL",
        apply_mode="restart",
        danger=True,
    ),
    CONFIG_KEY_REFERER_URL: ParamSpec(
        key=CONFIG_KEY_REFERER_URL,
        title="Referer",
        description="Заголовок Referer для запросов к API.",
        kind="str",
        group="Клиника и API",
        settings_attr="REFERER_URL",
        apply_mode="restart",
    ),
    CONFIG_KEY_CSRF_TOKEN: ParamSpec(
        key=CONFIG_KEY_CSRF_TOKEN,
        title="CSRF-токен",
        description="Токен для запросов к API клиники.",
        kind="str",
        group="Клиника и API",
        settings_attr="CSRF_TOKEN",
        apply_mode="restart",
        danger=True,
        secret=True,
    ),
    # ── Прочее ────────────────────────────────────────────────
    CONFIG_KEY_ADMIN_IDS: ParamSpec(
        key=CONFIG_KEY_ADMIN_IDS,
        title="ID администраторов",
        description="Telegram-id администраторов через запятую.",
        kind="str",
        group="Прочее",
        settings_attr="ADMIN_IDS",
        apply_mode="restart",
        danger=True,
    ),
    CONFIG_KEY_ERROR_NOTIFY_ENABLED: ParamSpec(
        key=CONFIG_KEY_ERROR_NOTIFY_ENABLED,
        title="Уведомления об ошибках",
        description="Отправлять ли администраторам сообщения об ошибках.",
        kind="bool",
        group="Прочее",
        settings_attr="ERROR_NOTIFY_ENABLED",
    ),
    CONFIG_KEY_USER_RATE_LIMIT_MAX: ParamSpec(
        key=CONFIG_KEY_USER_RATE_LIMIT_MAX,
        title="Лимит запросов пользователя",
        description="Сколько запросов подряд разрешено пользователю.",
        kind="int",
        group="Прочее",
        settings_attr="USER_RATE_LIMIT_MAX",
        min_value=1,
        max_value=1000,
    ),
    CONFIG_KEY_USER_RATE_LIMIT_PERIOD: ParamSpec(
        key=CONFIG_KEY_USER_RATE_LIMIT_PERIOD,
        title="Окно лимита запросов",
        description="Длительность окна лимита, секунды.",
        kind="int",
        group="Прочее",
        settings_attr="USER_RATE_LIMIT_PERIOD",
        min_value=1,
        max_value=3600,
    ),
    CONFIG_KEY_ENVIRONMENT: ParamSpec(
        key=CONFIG_KEY_ENVIRONMENT,
        title="Окружение",
        description="Режим работы: production, staging или development.",
        kind="enum",
        group="Прочее",
        settings_attr="ENVIRONMENT",
        apply_mode="restart",
        choices=("production", "staging", "development"),
        danger=True,
    ),
}

_BOOL_TRUE = {"1", "true", "yes", "on", "да"}
_BOOL_FALSE = {"0", "false", "no", "off", "нет"}


class ParamError(ValueError):
    """Некорректное значение параметра."""


def parse_value(spec: ParamSpec, raw: str) -> Any:
    """Преобразует строку из формы/БД в типизированное значение.

    Args:
        spec: Описание параметра.
        raw: Сырое значение.

    Returns:
        Значение нужного типа.

    Raises:
        ParamError: Значение не соответствует типу или границам.
    """
    text = (raw or "").strip()

    if spec.kind == "bool":
        low = text.lower()
        if low in _BOOL_TRUE:
            return True
        if low in _BOOL_FALSE:
            return False
        raise ParamError("Ожидается логическое значение (1/0, true/false).")

    if spec.kind in ("int", "float"):
        try:
            number: Any = int(text) if spec.kind == "int" else float(text)
        except ValueError as exc:
            kind = "целое число" if spec.kind == "int" else "число"
            raise ParamError(f"Ожидается {kind}.") from exc
        if isinstance(number, float) and not math.isfinite(number):
            raise ParamError("Значение должно быть конечным числом.")
        if spec.min_value is not None and number < spec.min_value:
            raise ParamError(f"Минимум: {spec.min_value}.")
        if spec.max_value is not None and number > spec.max_value:
            raise ParamError(f"Максимум: {spec.max_value}.")
        return number

    if spec.kind == "enum":
        if text not in spec.choices:
            raise ParamError(f"Допустимые значения: {', '.join(spec.choices)}.")
        return text

    if text == "" and spec.danger:
        raise ParamError("Пустое значение для этого параметра запрещено.")

    if text:
        _validate_str_format(spec.key, text)
    return text


def _validate_str_format(key: str, text: str) -> None:
    """Проверяет формат составных строковых параметров.

    Raises:
        ParamError: Формат значения не соответствует ожидаемому.
    """
    if key in (CONFIG_KEY_API_BASE_URL, CONFIG_KEY_REFERER_URL):
        if not text.startswith(("http://", "https://")):
            raise ParamError("Ожидается URL, начинающийся с http:// или https://.")
        return

    if key == CONFIG_KEY_ADMIN_IDS:
        parts = [part.strip() for part in text.split(",") if part.strip()]
        if not parts or any(not part.isdigit() for part in parts):
            raise ParamError("Ожидается список Telegram-id через запятую.")
        return

    if key == CONFIG_KEY_DEFAULT_BIRTHDAY and not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}", text
    ):
        raise ParamError("Ожидается дата в формате ГГГГ-ММ-ДД.")


def check_warnings(
    spec: ParamSpec, value: Any, current: Any | None = None
) -> list[str]:
    """Собирает предупреждения о значении параметра.

    Args:
        spec: Описание параметра.
        value: Проверяемое значение.

    Returns:
        Список предупреждений (пустой, если значение безопасное).
    """
    warnings: list[str] = []

    if (
        spec.kind == "str"
        and spec.settings_attr == "API_BASE_URL"
        and isinstance(value, str)
        and not value.startswith("https://")
    ):
        warnings.append("Адрес API должен начинаться с https://.")

    if spec.key == CONFIG_KEY_CHECK_INTERVAL and isinstance(value, int) and value < 60:
        warnings.append("Проверка чаще раза в минуту может привести к блокировке API.")

    if (
        spec.change_warning
        and current is not None
        and _format(value) != _format(current)
    ):
        warnings.append(spec.change_warning)

    if spec.danger:
        warnings.append(
            "Опасный параметр: изменение влияет на работу бота "
            f"(применение — {_apply_label(spec.apply_mode)})."
        )

    if spec.apply_mode == "restart":
        warnings.append("Применится после перезапуска бота.")

    return warnings


def _apply_label(mode: ApplyMode) -> str:
    """Человекочитаемая подпись способа применения."""
    return {
        "hot": "сразу",
        "next_cycle": "со следующей итерации",
        "restart": "после рестарта",
    }[mode]


def _settings_value(spec: ParamSpec) -> Any:
    """Значение параметра из ``.env`` (объекта settings)."""
    if spec.settings_attr is None:
        return None
    return getattr(settings, spec.settings_attr, None)


def _format(value: Any) -> str:
    """Строковое представление значения для UI и БД."""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def _display_value(spec: ParamSpec, value: Any) -> str:
    """Значение для UI и API: секреты маскируются."""
    if spec.secret:
        return MASK if _format(value) else "—"
    return _format(value)


async def effective_value(db: Any, key: str) -> str:
    """Действующее значение параметра с учётом приоритета источников.

    Returns:
        Значение из БД, иначе из ``.env``, иначе дефолт БД, иначе пустая строка.
    """
    spec = PARAMS.get(key)
    if spec is None:
        return ""
    stored_all = await db.config.get_all_config()
    if key in stored_all:
        return str(stored_all[key])
    if spec.settings_attr is not None:
        return _format(_settings_value(spec))
    if spec.db_default is not None:
        return spec.db_default
    return ""


async def collect_params(db: Any) -> list[dict[str, Any]]:
    """Собирает параметры с эффективными значениями и источником.

    Args:
        db: Фасад БД (``app.state.db``).

    Returns:
        Список словарей: ключ, описание, значение, источник, применение,
        предупреждения и признак «значение переопределено в БД».
    """
    stored = await db.config.get_all_config()
    result: list[dict[str, Any]] = []

    for key, spec in PARAMS.items():
        raw_db = stored.get(key)
        if key in _RUNTIME_OVERRIDES:
            source = "runtime"
            value = _settings_value(spec) if spec.settings_attr is not None else raw_db
        elif raw_db is not None:
            source = "БД"
            try:
                value = parse_value(spec, raw_db)
            except ParamError:
                value = raw_db
        elif spec.settings_attr is not None:
            source = ".env"
            value = _settings_value(spec)
        elif spec.db_default is not None:
            source = "по умолчанию"
            value = parse_value(spec, spec.db_default)
        else:
            source = "runtime"
            value = True if spec.kind == "bool" else ""

        result.append(
            {
                "key": key,
                "title": spec.title,
                "description": spec.description,
                "group": spec.group,
                "kind": spec.kind,
                "apply_mode": spec.apply_mode,
                "apply_label": _apply_label(spec.apply_mode),
                "danger": spec.danger,
                "min_value": spec.min_value,
                "max_value": spec.max_value,
                "choices": list(spec.choices),
                "value": _display_value(spec, value),
                "raw_value": None if spec.secret else value,
                "source": source,
                "overridden": raw_db is not None,
                "warnings": check_warnings(spec, value),
            }
        )

    return result


# Пары «меньший — больший»: меньший не может превысить больший.
_THRESHOLD_ORDER: tuple[tuple[str, str], ...] = (
    (CONFIG_KEY_SLOT_DETAIL_THRESHOLD, CONFIG_KEY_SLOT_COMPACT_THRESHOLD),
)


async def _cross_validate(db: Any, spec: ParamSpec, value: Any) -> None:
    """Проверяет согласованность связанных параметров.

    Raises:
        ParamError: Значение нарушает взаимное ограничение пары порогов.
    """
    stored = await db.config.get_all_config()
    for lower_key, upper_key in _THRESHOLD_ORDER:
        if spec.key not in (lower_key, upper_key):
            continue
        other_key = upper_key if spec.key == lower_key else lower_key
        other_spec = PARAMS.get(other_key)
        if other_spec is None:
            continue
        other_raw = stored.get(other_key)
        if other_raw is None and other_spec.settings_attr is not None:
            other_raw = _format(_settings_value(other_spec))
        if other_raw is None:
            other_raw = other_spec.db_default
        if other_raw is None:
            continue
        try:
            other_value = parse_value(other_spec, str(other_raw))
        except ParamError:
            continue
        if spec.key == lower_key and value > other_value:
            raise ParamError(
                f"Значение должно быть не больше порога "
                f"«{other_spec.title}» ({other_value})."
            )
        if spec.key == upper_key and value < other_value:
            raise ParamError(
                f"Значение должно быть не меньше порога "
                f"«{other_spec.title}» ({other_value})."
            )


async def set_param(
    db: Any,
    key: str,
    raw: str,
    actor: str = "unknown",
) -> dict[str, Any]:
    """Проверяет и сохраняет параметр, применяя его где возможно.

    Args:
        db: Фасад БД.
        key: Ключ параметра из реестра.
        raw: Новое значение из формы.
        actor: Кто меняет (для журнала).

    Returns:
        Словарь с новым значением, источником, статусом применения и
        предупреждениями.

    Raises:
        KeyError: Ключа нет в реестре.
        ParamError: Значение не прошло валидацию.
    """
    from src.services.audit import log_action

    spec = PARAMS.get(key)
    if spec is None:
        raise KeyError(key)

    # Секрет нельзя «сохранить» маской или пустым полем: иначе реальное
    # значение затрётся строкой "***" или пустой строкой.
    if spec.secret and raw.strip() in ("", MASK):
        raise ParamError("Секрет не изменён: введите новое значение.")

    value = parse_value(spec, raw)

    async with _set_lock():
        # Прежнее значение — действующее (БД, иначе .env, иначе дефолт БД).
        previous = await effective_value(db, key)
        await _cross_validate(db, spec, value)

        await db.config.set_config(key, _format(value))

        applied = _apply_label(spec.apply_mode)
        if spec.apply_mode != "restart" and spec.settings_attr is not None:
            try:
                setattr(settings, spec.settings_attr, value)
            except Exception as exc:
                logger.warning(f"params: не удалось применить {key} в runtime: {exc}")
                _RUNTIME_OVERRIDES.discard(key)
                applied = "после рестарта"
            else:
                _RUNTIME_OVERRIDES.add(key)

    try:
        previous_value: Any | None = parse_value(spec, previous)
    except ParamError:
        previous_value = None
    warnings = check_warnings(spec, value, previous_value)
    await log_action(
        db,
        actor,
        "config_change",
        target=key,
        old=MASK if spec.secret else previous,
        new=MASK if spec.secret else _format(value),
        applied=applied,
        warnings=warnings,
    )

    # Источник в ответе должен совпадать с тем, что отдаёт GET /api/config:
    # если значение применено в runtime — это "runtime", иначе значение
    # лежит только в БД и вступит в силу при следующем цикле или рестарте.
    source = "runtime" if key in _RUNTIME_OVERRIDES else "БД"

    return {
        "key": key,
        "value": _display_value(spec, value),
        "source": source,
        "applied": applied,
        "warnings": warnings,
    }
