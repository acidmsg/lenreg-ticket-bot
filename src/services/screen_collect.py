"""Сборщик элементов единого экрана из данных мониторинга.

Общий хелпер монитора и хендлера ``/start``: превращает сохранённые структуры
пользователя (``patients`` + ``monitoring``) в список
:class:`~src.services.screen_render.ScreenItem` и сводит ближайшую запись к
:class:`~src.services.screen_render.BookingSummary`. Внешний API и Telegram
здесь не используются: единственные источники — структуры пользователя и
локальная БД, поэтому модуль одинаково пригоден в фоне и в хендлере.

Строки слотов приходят снаружи готовыми (:func:`slot_lines` вызывается в
контексте языка пользователя): рендерер не форматирует слоты, а сборщик не
дублирует форматирование уведомлений — используется :func:`format_slots`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.config import settings
from src.database.manager import DatabaseManager
from src.database.types import BookingEntry, MonitoringEntry, PatientInfo
from src.i18n import _
from src.services.screen_render import BookingSummary, ScreenItem
from src.utils.helpers import format_slots, shorten_fio


@dataclass(frozen=True, slots=True)
class PairState:
    """Состояние пары «пациент — врач» за одну итерацию мониторинга.

    Attributes:
        p_id: Идентификатор пациента (строка из данных мониторинга).
        d_id: Идентификатор врача.
        has_new_events: Было ли по паре событие в этой итерации (именно оно
            даёт push через замену экрана).
        display_slots: Слоты для показа с маркером ``[NEW]``; ``None`` — слоты
            исчезли либо событий не было.
        slots: Актуальные слоты пары после фильтрации настройками пользователя.
    """

    p_id: str
    d_id: str
    has_new_events: bool
    display_slots: tuple[str, ...] | None = None
    slots: tuple[str, ...] = ()


def parse_id(raw: object) -> int:
    """Приводит идентификатор из данных пользователя к ``int``.

    ``ScreenItem`` и клавиатура экрана работают с числовыми id. Исторически в
    БД могли попасть нечисловые значения: для них возвращается ``0``, чтобы
    экран не терял строку врача из-за формата идентификатора.
    """
    try:
        return int(str(raw))
    except (TypeError, ValueError):
        return 0


def slot_lines(state: PairState) -> tuple[str, ...]:
    """Краткие строки слотов пары тем же форматтером, что у уведомления.

    Вызывать в контексте языка получателя: ярлыки дней недели и подписи
    приходят из i18n.
    """
    if state.has_new_events and state.display_slots is None:
        return (str(_("slots-disappeared-body")),)
    source = state.display_slots
    if source is None:
        source = state.slots
    if not source:
        return (str(_("slots-disappeared-body")),)
    return tuple(
        format_slots(
            list(source),
            detail_threshold=settings.SLOT_DETAIL_THRESHOLD,
            compact_threshold=settings.SLOT_COMPACT_THRESHOLD,
        )
    )


async def nearest_booking_summary(
    db: DatabaseManager, uid: str, now_ts: float
) -> BookingSummary | None:
    """Ближайшая активная запись пользователя для блока «Ближайшая запись».

    Читает локальную БД (``bookings``): внешний портал не опрашивается,
    прошедшие приёмы отброшены, порядок — по дате и времени приёма.
    """
    upcoming = await db.list_upcoming_bookings(uid, now_ts, limit=1)
    return booking_summary(upcoming[0]) if upcoming else None


def booking_summary(booking: BookingEntry) -> BookingSummary:
    """Сводит запись из БД к данным блока «Ближайшая запись» (дизайн §7.1)."""
    return BookingSummary(
        slot_date=str(booking.get("slot_date", "")),
        slot_time=str(booking.get("slot_time", "")),
        doctor_name=shorten_fio(str(booking.get("doctor_name", ""))),
        clinic_name=str(booking.get("clinic_name", "")),
        patient_name=str(booking.get("patient_name", "")),
    )


def build_screen_items(
    patients: Mapping[str, PatientInfo],
    monitoring: Mapping[str, Mapping[str, MonitoringEntry | str]],
    *,
    states: Sequence[PairState] = (),
    clinic_names: Mapping[str, str] | None = None,
) -> list[ScreenItem]:
    """Собирает полную сводку мониторинга пользователя для экрана.

    В экран попадают **все** пары пользователя, а не только изменившиеся:
    состав мониторинга — это состояние, а не журнал событий (дизайн §7.3).
    Пары без события в текущей итерации показываются без маркера новизны.

    Args:
        patients: Пациенты пользователя (``user_data['patients']``).
        monitoring: Мониторинг пользователя (``user_data['monitoring']``).
        states: Состояния пар текущей итерации; отсутствующие пары попадают в
            экран без строк слотов (например, при ошибке API).
        clinic_names: Кэш названий клиник по ``clinic_id``; пустое значение —
            название неизвестно, строка врача выводится без клиники.

    Returns:
        Список элементов экрана в порядке мониторинга (сортировку выполняет
        рендерер).
    """
    by_pair = {(state.p_id, state.d_id): state for state in states}
    names = clinic_names or {}
    items: list[ScreenItem] = []
    for p_id, doctors in monitoring.items():
        patient_info = patients.get(p_id)
        if patient_info is None:
            continue
        patient_name = _patient_name(patient_info)
        for d_id, d_info in doctors.items():
            state = by_pair.get((p_id, d_id))
            doctor_name, clinic_id = _doctor_fields(d_info, patient_info)
            items.append(
                ScreenItem(
                    p_id=parse_id(p_id),
                    d_id=parse_id(d_id),
                    patient_name=patient_name,
                    doctor_name=shorten_fio(doctor_name) or _("doctor-fallback-name"),
                    has_new_events=bool(state is not None and state.has_new_events),
                    lines=slot_lines(state) if state is not None else (),
                    clinic_name=names.get(clinic_id, ""),
                )
            )
    return items


def _patient_name(patient_info: PatientInfo) -> str:
    """Отображаемое имя пациента: псевдоним, иначе ФИО."""
    return (
        patient_info.get("alias")
        or patient_info.get("fio")
        or _("patient-fallback-name")
    )


def _doctor_fields(
    d_info: MonitoringEntry | str, patient_info: PatientInfo
) -> tuple[str, str]:
    """Возвращает имя врача и его ``clinic_id`` из записи мониторинга.

    Поддерживается устаревший строковый формат записи (только ФИО).
    """
    if isinstance(d_info, dict):
        clinic_id = str(
            d_info.get("clinic_id", patient_info.get("clinic_id", "")) or ""
        )
        return d_info.get("name", _("doctor-fallback-name")), clinic_id
    patient_clinic = str(patient_info.get("clinic_id", "") or "")
    return str(d_info), patient_clinic
