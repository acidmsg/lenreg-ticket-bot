"""
Типизированные CallbackData для всех callback-ов бота.

Использует aiogram.filters.callback_data.CallbackData для строгой
типизации и валидации callback_data.
"""

from aiogram.filters.callback_data import CallbackData


class PatientSelect(CallbackData, prefix="sel_p"):
    """Выбор пациента: sel_p_{p_id}."""
    p_id: str


class DeletePatientAsk(CallbackData, prefix="del_p_ask"):
    """Запрос подтверждения удаления пациента: del_p_ask_{p_id}."""
    p_id: str


class DeletePatientConfirm(CallbackData, prefix="del_p_yes"):
    """Подтверждение удаления пациента: del_p_yes_{p_id}."""
    p_id: str


class AddPatient(CallbackData, prefix="start_add_p"):
    """Добавление нового пациента (без параметров)."""


class StopAllMonitoring(CallbackData, prefix="stop_all"):
    """Сброс всего мониторинга (без параметров)."""


class ToggleDoctor(CallbackData, prefix="tgl"):
    """Переключение мониторинга врача: tgl_{p_id}_{clinic_id}_{d_id}."""
    p_id: str
    clinic_id: str
    d_id: str


class BackToClinics(CallbackData, prefix="back_to_clinics"):
    """Возврат к списку клиник: back_to_clinics_{p_id}_{city_idx}."""
    p_id: str
    city_idx: str


class BackToMain(CallbackData, prefix="back_to_main"):
    """Возврат на главную (без параметров)."""


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


class ExportCSV(CallbackData, prefix="export_csv"):
    """Экспорт в CSV (без параметров)."""


class ExportJSON(CallbackData, prefix="export_json"):
    """Экспорт в JSON (без параметров)."""


class SkipAlias(CallbackData, prefix="skip_alias"):
    """Пропуск ввода псевдонима (регистрация, без параметров)."""


class CancelRegistration(CallbackData, prefix="cancel_registration"):
    """Отмена регистрации (без параметров)."""


class StopPatientMonitoring(CallbackData, prefix="stop_patient"):
    """Сброс мониторинга пациента: stop_patient_{p_id}_{origin}_{city_idx}."""
    p_id: str
    origin: str
    city_idx: str = ""
