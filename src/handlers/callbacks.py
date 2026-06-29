"""
Типизированные CallbackData и строковые константы префиксов для callback-ов бота.

CallbackData с полями данных — для строгой типизации и валидации через aiogram.
Строковые константы CB_* — для callback'ов без полезной нагрузки (только префикс).
"""

from aiogram.filters.callback_data import CallbackData

# ── Строковые константы для callback'ов без полей данных ─────────────────────

CB_ADD_PATIENT = "start_add_p"
CB_STOP_ALL = "stop_all"
CB_BACK_TO_MAIN = "back_to_main"
CB_EXPORT_CSV = "export_csv"
CB_EXPORT_JSON = "export_json"
CB_SKIP_ALIAS = "skip_alias"
CB_CANCEL_REGISTRATION = "cancel_registration"
CB_NOOP = "noop"
CB_MY_BOOKINGS = "my_bookings"

# ── Типизированные CallbackData с полями данных ──────────────────────────────


class PatientSelect(CallbackData, prefix="sel_p"):
    """Выбор пациента: sel_p_{p_id}."""

    p_id: str


class DeletePatientAsk(CallbackData, prefix="del_p_ask"):
    """Запрос подтверждения удаления пациента: del_p_ask_{p_id}."""

    p_id: str


class DeletePatientConfirm(CallbackData, prefix="del_p_yes"):
    """Подтверждение удаления пациента: del_p_yes_{p_id}."""

    p_id: str


class ToggleDoctor(CallbackData, prefix="tgl"):
    """Переключение мониторинга врача: tgl_{p_id}_{clinic_id}_{d_id}."""

    p_id: str
    clinic_id: str
    d_id: str


class BackToClinics(CallbackData, prefix="back_to_clinics"):
    """Возврат к списку клиник: back_to_clinics_{p_id}_{city_idx}."""

    p_id: str
    city_idx: str


class StopClinicMonitoring(CallbackData, prefix="stop_clinic"):
    """Сброс мониторинга клиники: stop_clinic_{p_id}_{clinic_id}."""

    p_id: str
    clinic_id: str


class CitySelect(CallbackData, prefix="sel_cty"):
    """Выбор города: sel_cty_{p_id}_{idx} (idx = 'all' или 1-based индекс)."""

    p_id: str
    idx: str


class ClinicSelect(CallbackData, prefix="sel_c"):
    """Выбор клиники: sel_c_{p_id}_{clinic_id}_{city_idx}."""

    p_id: str
    clinic_id: str
    city_idx: str


class BackToCities(CallbackData, prefix="back_to_cities"):
    """Возврат к городам: back_to_cities_{p_id}."""

    p_id: str


class StopPatientMonitoring(CallbackData, prefix="stop_patient"):
    """Сброс мониторинга пациента: stop_patient_{p_id}_{origin}_{city_idx}."""

    p_id: str
    origin: str
    city_idx: str = "all"


class BookSlotLegacy(CallbackData, prefix="book"):
    """Запись на слот (старый flow — из уведомлений мониторинга):
    book_{p_id}_{clinic_id}_{d_id}_{appt_id}_{DD.MM}_{HH:MM}."""

    p_id: str
    clinic_id: str
    d_id: str
    appointment_id: str
    slot_date: str  # "ДД.ММ"
    slot_time: str  # "ЧЧ:ММ"


class BookConfirmLegacy(CallbackData, prefix="book_yes"):
    """Подтверждение записи (старый flow):
    book_yes_{p_id}_{clinic_id}_{d_id}_{appointment_id}."""

    p_id: str
    clinic_id: str
    d_id: str
    appointment_id: str


class BookCancel(CallbackData, prefix="book_no"):
    """Отмена записи: book_no_{p_id}_{clinic_id}_{d_id}."""

    p_id: str
    clinic_id: str
    d_id: str


# ── Новые CallbackData для PopupSection (Фаза 1 рефакторинга UX) ──


class DoctorSection(CallbackData, prefix="doc_sec"):
    """Открытие секции врача: doc_sec_{p_id}_{clinic_id}_{d_id}."""

    p_id: str
    clinic_id: str
    d_id: str


class CloseSection(CallbackData, prefix="close_sec"):
    """Закрытие секции: close_sec_{p_id}."""

    p_id: str


class StartMonitoring(CallbackData, prefix="start_mon"):
    """Добавление врача в отслеживание: start_mon_{p_id}_{clinic_id}_{d_id}."""

    p_id: str
    clinic_id: str
    d_id: str


class BookSlot(CallbackData, prefix="book_slot"):
    """Выбор слота для записи (новый flow — из PopupSection):
    book_slot_{p_id}_{clinic_id}_{d_id}_{appointment_id}_{date}_{time}."""

    p_id: str
    clinic_id: str
    d_id: str
    appointment_id: str
    date: str  # ДД.ММ.ГГГГ
    time: str  # ЧЧ:ММ


class BookConfirm(CallbackData, prefix="book_conf"):
    """Подтверждение записи (новый flow):
    book_conf_{p_id}_{clinic_id}_{d_id}_{appointment_id}_{date}_{time}."""

    p_id: str
    clinic_id: str
    d_id: str
    appointment_id: str
    date: str  # ДД.ММ.ГГГГ
    time: str  # ЧЧ:ММ


class SelectPatientForBooking(CallbackData, prefix="sel_pat_book"):
    """Выбор пациента для записи: sel_pat_book_{p_id}_{clinic_id}_{d_id}."""

    p_id: str
    clinic_id: str
    d_id: str
