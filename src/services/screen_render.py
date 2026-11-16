"""
Чистый рендерер экрана чата (single screen message), вариант B.

Модуль не выполняет ввода-вывода и не обращается к текущему времени: всё, что
влияет на результат, приходит аргументами (:class:`ScreenContext`). Благодаря
этому рендер покрывается юнит-тестами без БД и без Telegram, а ``render_hash``
остаётся стабильным.

Экран варианта B — карточка состояния, а не журнал событий: заголовок со
статусом проверки, сводка пар, до трёх пар с новыми талонами, до пяти пар
слежения, ближайшая запись, счётчики пациентов и подсказка действия.
Относительные метки («5 минут назад») входят в текст, но **не** в hash: иначе
экран «менялся» бы каждую минуту без изменения состояния.

Клавиатура в этом модуле не собирается: её строит слой ``handlers`` по
состоянию :class:`RenderedScreen` (дизайн §10.2, схема S2).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from src.config import settings
from src.i18n import _

# Резерв символов на заголовок, хвост «ещё N пар» и разделители.
_FOOTER_RESERVE = 160
# Минимальный бюджет тела экрана: ниже него отсечение бессмысленно.
_MIN_BODY_BUDGET = 200
# Сколько пар показывается в блоке «Новые талоны» (дизайн §7.2).
_NEW_BLOCK_LIMIT = 3
# Сколько пар показывается в блоке слежения (дизайн §7.2).
_TRACK_BLOCK_LIMIT = 5

PrimaryAction = Literal["add_patient", "book", "open_pairs", "open_app"]
"""Ведущее действие экрана — по нему строится контекстная кнопка S2."""


@dataclass(frozen=True, slots=True)
class ScreenItem:
    """Один врач в экране: стабильные данные, без ORM/DB-записей.

    ``last_event_label`` — уже готовая относительная метка времени (например,
    «5 минут назад»). Она попадает в текст, но **не** входит в ``render_hash``.
    """

    p_id: int
    d_id: int
    patient_name: str
    doctor_name: str
    has_new_events: bool
    lines: tuple[str, ...] = ()
    clinic_name: str = ""
    last_event_label: str = ""


@dataclass(frozen=True, slots=True)
class BookingSummary:
    """Ближайшая запись для блока «Ближайшая запись» (данные из локальной БД)."""

    slot_date: str
    slot_time: str
    doctor_name: str
    clinic_name: str = ""
    patient_name: str = ""


@dataclass(frozen=True, slots=True)
class ScreenContext:
    """Полное состояние экрана v2; собирается снаружи (хендлер, монитор).

    Поля со значениями по умолчанию позволяют передавать только то, что уже
    доступно вызывающему коду: сбор реальных данных (избранное, записи, время
    проверки) — отдельный этап, рендер от этого не зависит.
    """

    items: Sequence[ScreenItem] = ()
    """Пары «пациент — врач» со строками слотов."""

    patients_count: int = 0
    """Сколько пациентов у пользователя (``user_patients``)."""

    favorites_count: int = 0
    """Сколько клиник в избранном (``favorite_clinics``)."""

    monitored_pairs_count: int = 0
    """Сколько пар в мониторинге (может превышать число показанных врачей)."""

    nearest_booking: BookingSummary | None = None
    """Ближайшая активная запись либо ``None``."""

    last_check_at: int = 0
    """Unix-время последней проверки пар; ``0`` — проверок ещё не было."""

    api_available: bool | None = None
    """Доступность портала: ``True``/``False``, ``None`` — неизвестно."""

    iter_errors: int = 0
    """Сколько пар текущей итерации завершились ошибкой запроса слотов."""

    event_count: int = 0
    """Сколько пар текущей итерации дали новые события (для счётчиков записи)."""

    new_events_count: int = 0
    """Сколько новых событий показано с прошлого визита пользователя."""

    is_new_user: bool = False
    """У пользователя нет ни одного пациента (полный онбординг)."""

    now: int = 0
    """Unix-время рендера для относительных меток; в hash не входит."""


@dataclass(frozen=True, slots=True)
class ScreenLimits:
    """Лимиты рендера; по умолчанию — значения из конфигурации."""

    max_doctors: int = settings.SCREEN_MAX_DOCTORS
    max_lines: int = settings.SCREEN_MAX_LINES
    soft_limit: int = settings.SCREEN_TEXT_SOFT_LIMIT


@dataclass(frozen=True, slots=True)
class RenderedScreen:
    """Результат рендера экрана: текст, hash и состояние для кнопок S2."""

    text: str
    """Готовый текст сообщения (без разметки, лимит — ``soft_limit``)."""

    render_hash: str
    """SHA-256 канонического состояния: порядок, флаги новизны, строки врачей."""

    items: list[tuple[int, int]]
    """Пары ``(p_id, d_id)`` показанных врачей — для deep-link кнопки."""

    truncated: bool
    """``True``, если часть пар не поместилась в экран."""

    event_count: int
    """Сколько пар пришло на вход рендера."""

    primary_action: PrimaryAction = "open_app"
    """Ведущее действие экрана (схема кнопок S2)."""

    pair_for_deeplink: tuple[int, int] | None = None
    """Пара для deep-link ``slots_<p>_<d>``; не более одной на экран."""

    pair_doctor_name: str = ""
    """Короткое имя врача пары для подписи кнопки номерков."""

    is_new_user: bool = False
    """Экран показал онбординг (нет пациентов)."""

    has_monitoring: bool = False
    """У пользователя есть хотя бы одна пара в слежении."""

    new_events_count: int = 0
    """Число пар с новыми талонами."""


def render_screen(
    context: ScreenContext, *, limits: ScreenLimits | None = None
) -> RenderedScreen:
    """Собирает текст экрана варианта B и его стабильный hash.

    Порядок: пациент → новые события сверху → имя врача. Отсечение идёт по
    трём пределам: число врачей, число событий в блоке и мягкий лимит символов.
    """
    active = limits or ScreenLimits()
    if _is_new_user(context):
        return _render_onboarding(context)
    ordered = _sort_items(context.items)
    new_items, track_items = _split_sections(ordered, active.max_doctors)
    new_blocks, used_rows = _build_blocks(new_items, active.max_lines)
    track_blocks, _rows = _build_blocks(track_items, active.max_lines - used_rows)
    new_blocks, track_blocks, text = _fit_sections(
        context, new_blocks, track_blocks, _char_budget(active), len(ordered)
    )
    shown = [item for block in (*new_blocks, *track_blocks) for item, _rows in block[1]]
    dropped = len(ordered) - len(shown)
    deeplink_pair = _deeplink_pair(shown)
    return RenderedScreen(
        text=text,
        render_hash=_compute_hash(context, shown, truncated=dropped > 0),
        items=[(item.p_id, item.d_id) for item in shown],
        truncated=dropped > 0,
        event_count=len(ordered),
        primary_action=_primary_action(context),
        pair_for_deeplink=deeplink_pair,
        pair_doctor_name=_deeplink_doctor(shown),
        is_new_user=False,
        has_monitoring=_has_monitoring(context),
        new_events_count=sum(1 for item in ordered if item.has_new_events),
    )


def _is_new_user(context: ScreenContext) -> bool:
    """Онбординг показывается, когда у пользователя нет ни пациентов, ни пар."""
    return context.is_new_user or (context.patients_count == 0 and not context.items)


def _has_monitoring(context: ScreenContext) -> bool:
    """Есть ли у пользователя хотя бы одна отслеживаемая пара."""
    return bool(context.monitored_pairs_count or context.items)


def _primary_action(context: ScreenContext) -> PrimaryAction:
    """Ведущее действие: добавление, номерки пары с событием либо записи."""
    if not _has_monitoring(context):
        return "add_patient"
    if any(item.has_new_events for item in context.items):
        return "open_pairs"
    return "book"


def _deeplink_pair(shown: Sequence[ScreenItem]) -> tuple[int, int] | None:
    """Пара для deep-link: первая показанная пара с новыми талонами."""
    for item in shown:
        if item.has_new_events:
            return (item.p_id, item.d_id)
    return None


def _deeplink_doctor(shown: Sequence[ScreenItem]) -> str:
    """Короткое имя врача первой пары с новыми талонами (для подписи кнопки)."""
    for item in shown:
        if item.has_new_events:
            return item.doctor_name
    return ""


def _sort_items(items: Sequence[ScreenItem]) -> list[ScreenItem]:
    """Сортирует «пациент → наличие новых событий → имя врача»."""
    return sorted(items, key=_sort_key)


def _sort_key(item: ScreenItem) -> tuple[str, int, str]:
    """Ключ сортировки строки врача (новые события — выше)."""
    return (
        item.patient_name.casefold(),
        0 if item.has_new_events else 1,
        item.doctor_name.casefold(),
    )


def _split_sections(
    ordered: Sequence[ScreenItem], max_doctors: int
) -> tuple[list[ScreenItem], list[ScreenItem]]:
    """Делит пары на блок «Новые талоны» и блок слежения с учётом лимитов."""
    limit = min(len(ordered), max_doctors)
    new_items = [item for item in ordered if item.has_new_events][:_NEW_BLOCK_LIMIT]
    new_items = new_items[:limit]
    taken = {id(item) for item in new_items}
    rest = [item for item in ordered if id(item) not in taken]
    track_limit = max(limit - len(new_items), 0)
    track_items = rest[: min(_TRACK_BLOCK_LIMIT, track_limit)]
    return new_items, track_items


def _patient_header(patient_name: str) -> str:
    """Заголовок блока пациента."""
    return _("screen-patient-header").format(name=patient_name)


def _slots_state(item: ScreenItem) -> str:
    """Состояние слотов пары: ``present``, ``none`` либо ``pending``.

    Пустые ``lines`` означают, что пару ещё не проверяли в этой итерации:
    блок помечается «данные обновятся», а не пустотой.
    """
    if not item.lines:
        return "pending"
    if item.lines == (str(_("slots-disappeared-body")),):
        return "none"
    return "present"


def _slots_suffix(item: ScreenItem) -> str:
    """Короткий статус слотов для строки врача."""
    state = _slots_state(item)
    if state == "present":
        return str(_("screen-v2-has-slots"))
    if state == "none":
        return str(_("screen-v2-doctor-no-slots"))
    return str(_("screen-v2-data-pending"))


def _doctor_rows(item: ScreenItem) -> list[str]:
    """Строки одного врача: имя со статусом слотов и детализация слотов."""
    marker = _("screen-new-marker") if item.has_new_events else _("screen-old-marker")
    head = _("screen-v2-doctor-row").format(
        marker=marker, doctor=item.doctor_name, slots=_slots_suffix(item)
    )
    if _slots_state(item) != "present":
        return [head]
    indent = _("screen-slot-indent")
    return [head, *(f"{indent}{line}" for line in item.lines)]


def _build_blocks(
    items: Sequence[ScreenItem], max_rows: int
) -> tuple[list[tuple[str, list[tuple[ScreenItem, list[str]]]]], int]:
    """Группирует строки по пациентам, соблюдая лимит строк."""
    blocks: list[tuple[str, list[tuple[ScreenItem, list[str]]]]] = []
    rows_used = 0
    for item in items:
        item_rows = _doctor_rows(item)
        if rows_used + len(item_rows) > max_rows:
            break
        if not blocks or blocks[-1][0] != item.patient_name:
            blocks.append((item.patient_name, []))
        blocks[-1][1].append((item, item_rows))
        rows_used += len(item_rows)
    return blocks, rows_used


def _block_lines(
    blocks: Sequence[tuple[str, list[tuple[ScreenItem, list[str]]]]],
    *,
    leading_blank: bool,
) -> list[str]:
    """Строки блоков пациентов; ``leading_blank`` — пустая строка перед первым."""
    lines: list[str] = []
    for index, (patient_name, entries) in enumerate(blocks):
        if leading_blank or index:
            lines.append("")
        lines.append(_patient_header(patient_name))
        for _item, rows in entries:
            lines.extend(rows)
    return lines


def _header_lines(context: ScreenContext) -> list[str]:
    """Заголовок экрана: название, статус проверки, сводка пар и доступность API."""
    lines = [_("screen-v2-title"), _status_line(context)]
    if _has_monitoring(context):
        lines.append(
            _("screen-v2-pairs").format(
                count=context.monitored_pairs_count or len(context.items),
                patients=context.patients_count,
            )
        )
    api_line = _api_line(context)
    if api_line:
        lines.append(api_line)
    errors_line = _check_errors_line(context)
    if errors_line:
        lines.append(errors_line)
    return lines


def _compose_text(
    context: ScreenContext,
    new_blocks: Sequence[tuple[str, list[tuple[ScreenItem, list[str]]]]],
    track_blocks: Sequence[tuple[str, list[tuple[ScreenItem, list[str]]]]],
    total: int,
) -> str:
    """Собирает итоговый текст экрана из блоков и хвостов усечения."""
    lines = _header_lines(context)
    if new_blocks:
        new_count = sum(1 for item in context.items if item.has_new_events)
        lines.extend(("", _("screen-v2-new-header").format(count=new_count)))
        lines.extend(_block_lines(new_blocks, leading_blank=False))
    if track_blocks:
        lines.append("")
        lines.extend(_block_lines(track_blocks, leading_blank=False))
    if not _has_monitoring(context):
        lines.extend(("", _("screen-v2-empty-monitoring")))
    elif _all_without_slots(new_blocks, track_blocks):
        lines.extend(("", _("screen-v2-empty-slots")))
    shown = sum(len(entries) for _name, entries in (*new_blocks, *track_blocks))
    if total > shown:
        lines.extend(("", _("screen-v2-more-pairs").format(count=total - shown)))
    lines.extend(_booking_lines(context.nearest_booking))
    lines.extend(_context_lines(context))
    lines.extend(("", _("screen-v2-footer-hint")))
    return "\n".join(lines)


def _all_without_slots(
    new_blocks: Sequence[tuple[str, list[tuple[ScreenItem, list[str]]]]],
    track_blocks: Sequence[tuple[str, list[tuple[ScreenItem, list[str]]]]],
) -> bool:
    """Ни у одной показанной пары нет строк слотов."""
    return not any(
        _slots_state(item) == "present"
        for block in (*new_blocks, *track_blocks)
        for item, _rows in block[1]
    )


def _booking_lines(booking: BookingSummary | None) -> list[str]:
    """Блок ближайшей записи; без записи блок скрывается целиком."""
    if booking is None:
        return []
    return [
        "",
        _("screen-v2-bookings-header"),
        _("screen-v2-booking-row").format(
            date=booking.slot_date,
            time=booking.slot_time,
            doctor=booking.doctor_name,
            patient=booking.patient_name or booking.clinic_name,
        ),
    ]


def _context_lines(context: ScreenContext) -> list[str]:
    """Строка счётчиков пациентов и избранного (скрывается при нулях)."""
    if context.patients_count <= 0 and context.favorites_count <= 0:
        return []
    return [
        "",
        _("screen-v2-context").format(
            patients=context.patients_count, favorites=context.favorites_count
        ),
    ]


def _fit_sections(
    context: ScreenContext,
    new_blocks: list[tuple[str, list[tuple[ScreenItem, list[str]]]]],
    track_blocks: list[tuple[str, list[tuple[ScreenItem, list[str]]]]],
    budget: int,
    total: int,
) -> tuple[
    list[tuple[str, list[tuple[ScreenItem, list[str]]]]],
    list[tuple[str, list[tuple[ScreenItem, list[str]]]]],
    str,
]:
    """Отбрасывает хвостовые строки, пока текст не уложится в бюджет."""
    while True:
        text = _compose_text(context, new_blocks, track_blocks, total)
        if len(text) <= budget:
            return new_blocks, track_blocks, text
        if not _pop_last_row(track_blocks) and not _pop_last_row(new_blocks):
            return new_blocks, track_blocks, text


def _pop_last_row(
    blocks: list[tuple[str, list[tuple[ScreenItem, list[str]]]]],
) -> bool:
    """Убирает последнюю строку последнего блока; ``False`` — убирать нечего."""
    while blocks:
        entries = blocks[-1][1]
        if entries:
            entries.pop()
            if not entries:
                blocks.pop()
            return True
        blocks.pop()
    return False


def _render_onboarding(context: ScreenContext) -> RenderedScreen:
    """Полный онбординг для пользователя без пациентов (дизайн §7.3)."""
    lines = [
        _("screen-v2-onboarding-title"),
        "",
        _("screen-v2-onboarding-body"),
        "",
        _("screen-v2-onboarding-steps-header"),
        f"1. {_('screen-v2-onboarding-step-1')}",
        f"2. {_('screen-v2-onboarding-step-2')}",
        f"3. {_('screen-v2-onboarding-step-3')}",
        "",
        _("screen-v2-onboarding-footer").format(minutes=settings.CHECK_INTERVAL // 60),
    ]
    return RenderedScreen(
        text="\n".join(lines),
        render_hash=_compute_hash(context, (), truncated=False),
        items=[],
        truncated=False,
        event_count=0,
        primary_action="add_patient",
        is_new_user=True,
        has_monitoring=False,
    )


def _status_line(context: ScreenContext) -> str:
    """Строка статуса проверки: «проверено N назад · следующий цикл ~M»."""
    if context.last_check_at <= 0:
        return str(_("screen-v2-never-checked"))
    now = context.now or context.last_check_at
    elapsed = max(now - context.last_check_at, 0)
    eta_seconds = max(settings.CHECK_INTERVAL - elapsed, 0)
    eta_minutes = max((eta_seconds + 59) // 60, 1)
    return _("screen-v2-status").format(
        ago=_relative_ago(elapsed),
        eta=_("screen-v2-eta-minutes").format(minutes=eta_minutes),
    )


def _relative_ago(elapsed_seconds: int) -> str:
    """Относительная метка «только что / N минут назад / N часов назад»."""
    if elapsed_seconds < 60:
        return str(_("screen-v2-ago-now"))
    minutes = elapsed_seconds // 60
    if minutes < 60:
        return _("screen-v2-ago-minutes").format(minutes=minutes)
    return _("screen-v2-ago-hours").format(hours=minutes // 60)


def _check_errors_line(context: ScreenContext) -> str | None:
    """Предупреждение о сбоях проверки в текущей итерации.

    Строка появляется только при ``iter_errors > 0``: пользователь должен
    знать, что часть пар не проверена и данные могли устареть.
    """
    if context.iter_errors <= 0:
        return None
    return _("screen-v2-check-errors").format(count=context.iter_errors)


def _api_line(context: ScreenContext) -> str | None:
    """Строка доступности портала; ``None`` — состояние неизвестно."""
    if context.api_available is None:
        return None
    if context.api_available:
        return str(_("screen-v2-api-ok"))
    retry_at = _clock_label((context.now or 0) + settings.CHECK_INTERVAL)
    return _("screen-v2-api-down").format(time=retry_at)


def _clock_label(unix_seconds: int) -> str:
    """Метка времени ``ЧЧ:ММ`` по переданному моменту (без текущего времени)."""
    return datetime.fromtimestamp(unix_seconds).strftime("%H:%M")


def _char_budget(limits: ScreenLimits) -> int:
    """Бюджет символов на тело экрана: мягкий лимит минус заголовок и хвост."""
    reserve = len(_("screen-v2-title")) + _FOOTER_RESERVE
    return max(limits.soft_limit - reserve, _MIN_BODY_BUDGET)


def _compute_hash(
    context: ScreenContext, shown: Sequence[ScreenItem], *, truncated: bool
) -> str:
    """SHA-256 канонического состояния экрана.

    В hash входят: состояние онбординга, порядок показа, пара ``(p_id, d_id)``,
    имена, флаг новизны, строки слотов, клиника, признак усечения, счётчики,
    абсолютное время последней проверки, доступность портала, число ошибок
    проверки и ближайшая запись. Не входят: ``now`` и относительные метки
    времени — они меняются от рендера к рендеру без изменения состояния.
    """
    booking = context.nearest_booking
    payload = {
        "is_new_user": _is_new_user(context),
        "items": [
            [
                item.p_id,
                item.d_id,
                item.patient_name,
                item.doctor_name,
                item.has_new_events,
                list(item.lines),
                item.clinic_name,
            ]
            for item in shown
        ],
        "truncated": truncated,
        "event_count": len(context.items),
        "monitored_pairs_count": context.monitored_pairs_count,
        "patients_count": context.patients_count,
        "favorites_count": context.favorites_count,
        "new_events_count": context.new_events_count,
        "last_check_at": context.last_check_at,
        "api_available": context.api_available,
        "iter_errors": context.iter_errors,
        "booking": None
        if booking is None
        else [
            booking.slot_date,
            booking.slot_time,
            booking.doctor_name,
            booking.clinic_name,
            booking.patient_name,
        ],
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
