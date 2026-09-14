"""
FSM-мастер настройки фильтра отслеживания (задача T-21, раздел 9 дизайна).

Мастер проводит пользователя по пяти шагам ввода (интервал дат, интервал
времени, конкретные даты), показывает сводку и сохраняет полный набор из пяти
полей фильтра в запись мониторинга пары пациент + врач.

Формат ввода бота — ``ДД.ММ.ГГГГ`` и ``ЧЧ:ММ``; формат хранения — ``ГГГГ-ММ-ДД``
и ``ЧЧ:ММ`` (§9.2, §9.6). Пустое значение любого поля означает «ограничение не
задано»; все пять шагов можно пропустить — фильтр сохраняется пустым (§9.3.6).
"""

import json
import re
from datetime import date, datetime, timedelta
from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger

from src.database.manager import DatabaseManager
from src.database.types import DoctorEntry
from src.handlers.callbacks import (
    CB_BACK_TO_MAIN,
    CB_FILTER_BACK,
    CB_FILTER_CANCEL,
    CB_FILTER_DONE,
    CB_FILTER_SKIP,
    FILTER_WIZARD_STEPS,
    FILTER_WIZARD_SUMMARY_STEP,
)
from src.i18n import _
from src.keyboards.inline import (
    get_filter_summary_keyboard,
    get_filter_wizard_keyboard,
)

router = Router()

# ── Константы модели фильтра (§9.3.5, §9.6) ───────────────────────────────────

#: Максимальный горизонт даты фильтра — 365 дней от сегодня.
FILTER_MAX_HORIZON_DAYS = 365

#: Максимальное число конкретных дат в allow-списке.
FILTER_MAX_SPECIFIC_DATES = 10

#: Прочерк для пустой границы интервала в сводке.
_EMPTY_BOUNDARY = "—"


class FilterSetupStates(StatesGroup):
    """Шаги мастера фильтра (имена совпадают с ``FILTER_WIZARD_STEPS``)."""

    wait_date_from = State()
    wait_date_to = State()
    wait_time_from = State()
    wait_time_to = State()
    wait_specific_dates = State()
    wait_summary = State()


class FilterInputError(ValueError):
    """Ошибка валидации ввода мастера; несёт ключ локализации сообщения."""

    def __init__(self, message_key: str) -> None:
        super().__init__(message_key)
        self.message_key = message_key


# ── Метаданные шагов ─────────────────────────────────────────────────────────
# Порядок шагов задан единственным источником — FILTER_WIZARD_STEPS.

_STEP_STATES: dict[str, State] = dict(
    zip(
        (*FILTER_WIZARD_STEPS, FILTER_WIZARD_SUMMARY_STEP),
        (
            FilterSetupStates.wait_date_from,
            FilterSetupStates.wait_date_to,
            FilterSetupStates.wait_time_from,
            FilterSetupStates.wait_time_to,
            FilterSetupStates.wait_specific_dates,
            FilterSetupStates.wait_summary,
        ),
        strict=True,
    )
)

_STEP_FIELDS: dict[str, str] = dict(
    zip(
        FILTER_WIZARD_STEPS,
        ("date_from", "date_to", "time_from", "time_to", "specific_dates"),
        strict=True,
    )
)

_STEP_PROMPTS: dict[str, str] = dict(
    zip(
        FILTER_WIZARD_STEPS,
        (
            "filter-step-date-from",
            "filter-step-date-to",
            "filter-step-time-from",
            "filter-step-time-to",
            "filter-step-specific-dates",
        ),
        strict=True,
    )
)

# Состояния ввода (без шага подтверждения) и полный список состояний мастера.
_INPUT_STATES: tuple[State, ...] = tuple(
    _STEP_STATES[step] for step in FILTER_WIZARD_STEPS
)
_ALL_STATES: tuple[State, ...] = tuple(_STEP_STATES.values())


# ── Валидация (§9.3.5, §9.6) ─────────────────────────────────────────────────


def _parse_display_date(value: str) -> date:
    """Разбирает дату ``ДД.ММ.ГГГГ`` со строгой проверкой формата.

    Raises:
        FilterInputError: Если формат даты некорректен.
    """
    text = value.strip()
    try:
        parsed = datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError as exc:
        raise FilterInputError("filter-err-date") from exc
    if parsed.strftime("%d.%m.%Y") != text:
        raise FilterInputError("filter-err-date")
    return parsed


def validate_date(value: str, *, today: date | None = None) -> str:
    """Проверяет дату ``ДД.ММ.ГГГГ`` и возвращает её в формате ``ГГГГ-ММ-ДД``.

    Границы: не раньше сегодня и не позже сегодня + ``FILTER_MAX_HORIZON_DAYS``.

    Raises:
        FilterInputError: С ключом локализации ошибки.
    """
    current = today or date.today()
    parsed = _parse_display_date(value)
    if parsed < current:
        raise FilterInputError("filter-err-date-past")
    if parsed > current + timedelta(days=FILTER_MAX_HORIZON_DAYS):
        raise FilterInputError("filter-err-date")
    return parsed.isoformat()


def validate_time(value: str) -> str:
    """Проверяет время ``ЧЧ:ММ`` со строгим форматом.

    Raises:
        FilterInputError: С ключом ``filter-err-time``.
    """
    text = value.strip()
    try:
        parsed = datetime.strptime(text, "%H:%M").time()
    except ValueError as exc:
        raise FilterInputError("filter-err-time") from exc
    if parsed.strftime("%H:%M") != text:
        raise FilterInputError("filter-err-time")
    return text


def parse_specific_dates(value: str, *, today: date | None = None) -> list[str]:
    """Разбирает allow-список дат (1–10) в отсортированный список ``ГГГГ-ММ-ДД``.

    Даты разделяются запятой и/или пробелом; дубликаты удаляются, даты в прошлом
    запрещены (§9.3.5).

    Raises:
        FilterInputError: С ключом ``filter-err-specific-dates``.
    """
    current = today or date.today()
    tokens = [token for token in re.split(r"[\s,]+", value.strip()) if token]
    if not tokens or len(tokens) > FILTER_MAX_SPECIFIC_DATES:
        raise FilterInputError("filter-err-specific-dates")

    parsed_dates: set[str] = set()
    for token in tokens:
        try:
            parsed = _parse_display_date(token)
        except FilterInputError as exc:
            raise FilterInputError("filter-err-specific-dates") from exc
        if parsed < current:
            raise FilterInputError("filter-err-specific-dates")
        parsed_dates.add(parsed.isoformat())
    return sorted(parsed_dates)


def validate_date_range(date_from: str, date_to: str) -> None:
    """Проверяет, что верхняя граница дат не раньше нижней (§9.3.5).

    Raises:
        FilterInputError: С ключом ``filter-err-date-range``.
    """
    if date_from and date_to and date_to < date_from:
        raise FilterInputError("filter-err-date-range")


def validate_time_range(time_from: str, time_to: str) -> None:
    """Проверяет, что конец интервала времени не раньше начала (§9.3.5).

    Raises:
        FilterInputError: С ключом ``filter-err-time-range``.
    """
    if time_from and time_to and time_to < time_from:
        raise FilterInputError("filter-err-time-range")


# ── Служебные функции мастера ────────────────────────────────────────────────


def _format_display_date(iso_date: str) -> str:
    """Преобразует дату ``ГГГГ-ММ-ДД`` в ``ДД.ММ.ГГГГ`` для отображения."""
    if not iso_date:
        return _EMPTY_BOUNDARY
    try:
        return date.fromisoformat(iso_date).strftime("%d.%m.%Y")
    except ValueError:
        return iso_date


def build_summary_text(data: dict[str, Any]) -> str:
    """Формирует сводку фильтра для шага подтверждения (§9.3.4)."""
    lines = [_("filter-step-summary-title")]

    date_from = str(data.get("date_from", ""))
    date_to = str(data.get("date_to", ""))
    if date_from or date_to:
        lines.append(
            _("filter-summary-date-range").format(
                date_from=_format_display_date(date_from),
                date_to=_format_display_date(date_to),
            )
        )

    time_from = str(data.get("time_from", ""))
    time_to = str(data.get("time_to", ""))
    if time_from or time_to:
        lines.append(
            _("filter-summary-time-range").format(
                time_from=time_from or _EMPTY_BOUNDARY,
                time_to=time_to or _EMPTY_BOUNDARY,
            )
        )

    specific_dates = [str(item) for item in (data.get("specific_dates") or [])]
    if specific_dates:
        lines.append(
            _("filter-summary-specific-dates").format(
                dates=", ".join(_format_display_date(item) for item in specific_dates)
            )
        )

    if len(lines) == 1:
        lines.append(_("filter-summary-empty"))
    return "\n".join(lines)


def _build_filter_payload(data: dict[str, Any]) -> dict[str, str]:
    """Собирает полный набор из пяти полей фильтра в формате хранения (§9.3.6)."""
    specific_dates = [str(item) for item in (data.get("specific_dates") or [])]
    return {
        "date_from": str(data.get("date_from", "")),
        "date_to": str(data.get("date_to", "")),
        "time_from": str(data.get("time_from", "")),
        "time_to": str(data.get("time_to", "")),
        "specific_dates": json.dumps(specific_dates, ensure_ascii=False),
    }


def _is_filter_empty(filter_data: dict[str, str]) -> bool:
    """Проверяет, что все пять полей фильтра пусты (§9.3.6)."""
    bounds_empty = all(
        not filter_data.get(field)
        for field in ("date_from", "date_to", "time_from", "time_to")
    )
    return bounds_empty and filter_data.get("specific_dates", "") in ("", "[]")


async def _current_step(state: FSMContext) -> str:
    """Возвращает имя текущего шага FSM без имени StatesGroup."""
    return (await state.get_state() or "").rsplit(":", 1)[-1]


def _next_step(step: str) -> str:
    """Возвращает следующий шаг мастера; после последнего — шаг сводки."""
    index = FILTER_WIZARD_STEPS.index(step)
    if index + 1 < len(FILTER_WIZARD_STEPS):
        return FILTER_WIZARD_STEPS[index + 1]
    return FILTER_WIZARD_SUMMARY_STEP


def _previous_step(step: str) -> str | None:
    """Возвращает предыдущий шаг мастера; для первого шага — ``None``."""
    if step == FILTER_WIZARD_SUMMARY_STEP:
        return FILTER_WIZARD_STEPS[-1]
    index = FILTER_WIZARD_STEPS.index(step)
    if index == 0:
        return None
    return FILTER_WIZARD_STEPS[index - 1]


def _parse_step_value(step: str, raw_value: str, data: dict[str, Any]) -> Any:
    """Валидирует ввод шага и возвращает значение для FSM-данных.

    Args:
        step: Имя состояния шага (из ``FILTER_WIZARD_STEPS``).
        raw_value: Сырой текст пользователя.
        data: Текущие FSM-данные (для проверки границ интервалов).

    Raises:
        FilterInputError: Если ввод не проходит валидацию шага.
    """
    field = _STEP_FIELDS[step]
    if field == "date_from":
        return validate_date(raw_value)
    if field == "date_to":
        value = validate_date(raw_value)
        validate_date_range(str(data.get("date_from", "")), value)
        return value
    if field == "time_from":
        return validate_time(raw_value)
    if field == "time_to":
        value = validate_time(raw_value)
        validate_time_range(str(data.get("time_from", "")), value)
        return value
    return parse_specific_dates(raw_value)


def _empty_step_value(step: str) -> Any:
    """Возвращает «пустое» значение поля шага (сброс ограничения)."""
    return [] if _STEP_FIELDS[step] == "specific_dates" else ""


async def _send_text(
    message: Message,
    text: str,
    markup: InlineKeyboardMarkup,
    *,
    edit: bool,
) -> None:
    """Редактирует сообщение либо отправляет новое, если редактирование недоступно."""
    if edit:
        try:
            await message.edit_text(text, reply_markup=markup)
            return
        except TelegramAPIError:
            logger.debug("Не удалось отредактировать сообщение мастера фильтра")
    await message.answer(text, reply_markup=markup)


async def _render_step(
    message: Message,
    state: FSMContext,
    step: str,
    *,
    edit: bool,
) -> None:
    """Показывает шаг мастера: промпт поля либо сводку фильтра."""
    await state.set_state(_STEP_STATES[step])
    if step == FILTER_WIZARD_SUMMARY_STEP:
        data = await state.get_data()
        text = build_summary_text(data)
        markup = get_filter_summary_keyboard()
    else:
        text = _(_STEP_PROMPTS[step])
        markup = get_filter_wizard_keyboard(step)
    await _send_text(message, text, markup, edit=edit)


def _back_to_main_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура возврата в главное меню после мастера (§9.3.6)."""
    return (
        InlineKeyboardBuilder()
        .button(text=_("btn-back-to-main"), callback_data=CB_BACK_TO_MAIN)
        .as_markup()
    )


async def begin_filter_wizard(
    call: CallbackQuery,
    state: FSMContext,
    db: DatabaseManager,
    p_id: str,
    clinic_id: str,
    d_id: str,
    *,
    doctor_name: str | None = None,
    doctor_specialty: str | None = None,
    created: bool = False,
) -> None:
    """Точка входа мастера: сохраняет контекст в FSM и показывает шаг 1 (§9.3.1).

    Args:
        call: Callback текущего сообщения (кнопка «В отслеживание»/«Настроить фильтр»).
        state: FSM-контекст пользователя.
        db: Менеджер БД (для догрузки имени и специальности врача).
        p_id: ID пациента.
        clinic_id: ID клиники (участвует в навигации и страховочном пересоздании).
        d_id: ID врача.
        doctor_name: Имя врача, если уже известно вызывающему коду.
        doctor_specialty: Специальность врача, если уже известна вызывающему коду.
        created: Флаг «запись добавлена этим мастером».
    """
    if not call.from_user or not call.message:
        return

    if not doctor_name or doctor_specialty is None:
        doctors_list = await db.get_doctors_for_clinic(clinic_id)
        doc_raw = doctors_list.get(d_id)
        if doc_raw:
            doc_info: DoctorEntry = doc_raw
            doctor_name = doctor_name or doc_info.get("name", _("doctor-fallback-name"))
            doctor_specialty = doctor_specialty or doc_info.get("specialty", "")

    # Сброс незавершённого предыдущего мастера и установка контекста пары.
    await state.clear()
    await state.update_data(
        p_id=p_id,
        clinic_id=clinic_id,
        d_id=d_id,
        d_name=doctor_name or d_id,
        doctor_specialty=doctor_specialty or "",
        date_from="",
        date_to="",
        time_from="",
        time_to="",
        specific_dates=[],
        created=created,
    )

    await call.answer()
    if isinstance(call.message, Message):
        await _render_step(call.message, state, FILTER_WIZARD_STEPS[0], edit=True)


# ── Обработчики мастера ──────────────────────────────────────────────────────


@router.message(StateFilter(*_INPUT_STATES))
async def process_filter_input(message: Message, state: FSMContext) -> None:
    """Обрабатывает текстовый ввод шага: валидация и переход к следующему шагу."""
    if not message.text:
        return

    step = await _current_step(state)
    data = await state.get_data()
    try:
        value = _parse_step_value(step, message.text, data)
    except FilterInputError as exc:
        await message.answer(
            _(exc.message_key),
            reply_markup=get_filter_wizard_keyboard(step),
        )
        return

    await state.update_data(**{_STEP_FIELDS[step]: value})
    await _render_step(message, state, _next_step(step), edit=False)


@router.callback_query(F.data == CB_FILTER_SKIP, StateFilter(*_INPUT_STATES))
async def skip_filter_step(call: CallbackQuery, state: FSMContext) -> None:
    """Пропускает текущее поле: соответствующее ограничение не задаётся (§9.3.5)."""
    if not call.from_user:
        return

    step = await _current_step(state)
    await state.update_data(**{_STEP_FIELDS[step]: _empty_step_value(step)})
    await call.answer()
    if isinstance(call.message, Message):
        await _render_step(call.message, state, _next_step(step), edit=True)


@router.callback_query(F.data == CB_FILTER_BACK, StateFilter(*_ALL_STATES))
async def back_filter_step(call: CallbackQuery, state: FSMContext) -> None:
    """Возвращает мастера к предыдущему шагу (на первом шаге кнопки нет)."""
    if not call.from_user:
        return

    previous = _previous_step(await _current_step(state))
    if previous is None:
        return

    await call.answer()
    if isinstance(call.message, Message):
        await _render_step(call.message, state, previous, edit=True)


@router.callback_query(
    F.data == CB_FILTER_DONE, StateFilter(_STEP_STATES[FILTER_WIZARD_SUMMARY_STEP])
)
async def confirm_filter_setup(
    call: CallbackQuery,
    state: FSMContext,
    db: DatabaseManager,
) -> None:
    """Сохраняет собранный фильтр и показывает результат (§9.3.6)."""
    if not call.from_user:
        return

    await call.answer()
    data = await state.get_data()
    uid = str(call.from_user.id)
    p_id = str(data.get("p_id", ""))
    d_id = str(data.get("d_id", ""))
    clinic_id = str(data.get("clinic_id", ""))
    filter_data = _build_filter_payload(data)

    try:
        await db.update_monitoring_filter(uid, p_id, d_id, filter_data)
    except ValueError:
        # Запись снята параллельно — пересоздаём её и повторяем сохранение.
        logger.warning(
            "Мониторинг не найден при сохранении фильтра, пересоздаём: "
            "uid={}, p_id={}, d_id={}",
            uid,
            p_id,
            d_id,
        )
        await db.toggle_monitoring(
            uid,
            p_id,
            d_id,
            str(data.get("d_name", d_id)),
            clinic_id,
            str(data.get("doctor_specialty", "")),
            date="",
        )
        await db.update_monitoring_filter(uid, p_id, d_id, filter_data)

    await state.clear()
    result_key = (
        "filter-saved-empty" if _is_filter_empty(filter_data) else "filter-saved"
    )
    if isinstance(call.message, Message):
        await _send_text(
            call.message,
            _(result_key),
            _back_to_main_keyboard(),
            edit=True,
        )


@router.callback_query(F.data == CB_FILTER_CANCEL, StateFilter(*_ALL_STATES))
async def cancel_filter_setup(call: CallbackQuery, state: FSMContext) -> None:
    """Отменяет мастер; запись мониторинга остаётся без фильтра (§9.3.6)."""
    if not call.from_user:
        return

    await state.clear()
    await call.answer()
    if isinstance(call.message, Message):
        await _send_text(
            call.message,
            _("filter-cancelled"),
            _back_to_main_keyboard(),
            edit=True,
        )
