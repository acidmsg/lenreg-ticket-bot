from datetime import datetime

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dateutil.relativedelta import (
    relativedelta,
)
from loguru import logger

from src.config import settings
from src.database.types import ClinicInfo
from src.handlers.callbacks import (
    AddPatient,
    BackToCities,
    BackToClinics,
    BackToMain,
    CancelRegistration,
    CitySelect,
    ClinicSelect,
    DeletePatientAsk,
    DeletePatientConfirm,
    PatientSelect,
    SkipAlias,
    StopAllMonitoring,
    StopClinicMonitoring,
    StopPatientMonitoring,
    ToggleDoctor,
)
from src.i18n import _
from src.utils.helpers import is_cabinet, is_child, shorten_fio, shorten_specialty


def get_main_menu_keyboard(
    mini_app_url: str | None = None,
) -> ReplyKeyboardMarkup | None:
    """Создаёт reply-клавиатуру с кнопкой Mini App.

    Если mini_app_url не указан или пуст — возвращает None.
    """
    if not mini_app_url:
        return None

    buttons = [
        [KeyboardButton(text="🌐 Мониторинг", web_app=WebAppInfo(url=mini_app_url))]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_patient_selection(patients: dict, monitoring: dict):
    builder = InlineKeyboardBuilder()

    # Сортируем пациентов по имени (псевдониму или ФИО) в алфавитном порядке
    sorted_patients = sorted(
        patients.items(),
        key=lambda x: (x[1].get("alias") or x[1].get("fio", "")).lower(),
    )

    for p_id, p_info in sorted_patients:
        name = p_info.get("alias") or p_info.get("fio")
        count = len(monitoring.get(p_id, {}))
        label = f"👤 {name} ({count})" if count > 0 else f"👤 {name}"

        builder.button(text=label, callback_data=PatientSelect(p_id=p_id).pack())
        builder.button(text="🗑", callback_data=DeletePatientAsk(p_id=p_id).pack())

    builder.button(text=_("btn-add-patient"), callback_data=AddPatient().pack())

    # Определяем, есть ли хоть один активный мониторинг
    has_active_monitoring = any(len(docs) > 0 for docs in monitoring.values())

    if has_active_monitoring:
        builder.button(
            text=_("btn-reset-all-monitoring"),
            callback_data=StopAllMonitoring().pack(),
        )

    adjustments = [2] * len(patients) + [1]
    builder.adjust(*adjustments)
    return builder.as_markup()


def get_doctor_selection(
    p_id: str,
    clinic_id: str,
    doctors_list: dict,
    monitored: dict,
    bday_str: str = "",
    city_idx: str = "all",
):
    builder = InlineKeyboardBuilder()

    doctors_humans = []
    doctors_cabinets = []

    # Определяем, нужно ли фильтровать по детским специальностям в стоматологии
    is_dental = clinic_id == settings.DENTAL_CLINIC_ID
    patient_is_child = is_child(bday_str) if is_dental and bday_str else None

    for d_id, info in doctors_list.items():
        if isinstance(info, dict):
            raw_name = info.get("name", "Unknown")
            raw_spec = info.get("specialty", "")
        else:
            raw_name = d_id
            raw_spec = ""

        # Фильтрация для стоматологии (клиника 272):
        # - Для детей — только специальности с "детск" в названии
        #   (Детская стоматология, Детский профилактический осмотр и т.п.)
        # - Для взрослых — все, кроме специальностей с "детск" в названии
        if is_dental and patient_is_child is not None:
            spec_lower = raw_spec.lower() if raw_spec else ""
            is_pediatric = "детск" in spec_lower if spec_lower else False
            if patient_is_child and not is_pediatric:
                continue  # ребёнку показываем только детские специальности
            if not patient_is_child and is_pediatric:
                continue  # взрослому не показываем детские специальности

        if is_cabinet(raw_name):
            doctors_cabinets.append(
                {
                    "id": d_id,
                    "name": raw_name,
                }
            )
        else:
            doctors_humans.append(
                {
                    "id": d_id,
                    "name": shorten_fio(raw_name),
                    "specialty": shorten_specialty(raw_spec),
                }
            )

    # Сортируем врачей по специальности, затем по фамилии
    doctors_humans.sort(key=lambda x: (x["specialty"], x["name"]))
    # Кабинеты — в алфавитном порядке по name
    doctors_cabinets.sort(key=lambda x: x["name"])

    # Кнопки врачей
    for doc in doctors_humans:
        d_id = doc["id"]
        status = "✅ " if d_id in monitored else "▫️ "
        label = f"{status}[{doc['specialty']}] {doc['name']}"
        builder.button(
            text=label,
            callback_data=ToggleDoctor(
                p_id=p_id, clinic_id=clinic_id, d_id=d_id
            ).pack(),
        )

    # Кнопки кабинетов (без разделителя)
    for doc in doctors_cabinets:
        d_id = doc["id"]
        status = "✅ " if d_id in monitored else "▫️ "
        label = f"{status}{doc['name']}"
        builder.button(
            text=label,
            callback_data=ToggleDoctor(
                p_id=p_id, clinic_id=clinic_id, d_id=d_id
            ).pack(),
        )

    # Навигация
    builder.button(
        text=_("btn-back-to-clinics"),
        callback_data=BackToClinics(p_id=p_id, city_idx=city_idx).pack(),
    )
    builder.button(text=_("btn-back-to-list"), callback_data=BackToMain().pack())

    # Кнопка сброса мониторинга этой клиники —
    # только если есть мониторинг в этой клинике
    has_clinic_monitoring = any(
        isinstance(d_info, dict) and d_info.get("clinic_id") == clinic_id
        for d_info in monitored.values()
    )
    if has_clinic_monitoring:
        builder.button(
            text=_("btn-reset-clinic-monitoring"),
            callback_data=StopClinicMonitoring(p_id=p_id, clinic_id=clinic_id).pack(),
        )

    builder.adjust(1, 1)
    return builder.as_markup()


def get_confirm_deletion(p_id: str):
    builder = InlineKeyboardBuilder()
    builder.button(
        text=_("btn-yes-delete"),
        callback_data=DeletePatientConfirm(p_id=p_id).pack(),
    )
    builder.button(
        text=_("btn-no"),
        callback_data=PatientSelect(p_id=p_id).pack(),
    )
    builder.adjust(2)
    return builder.as_markup()


def _short_clinic_label(clinic_name: str, count: int) -> str:
    """Сокращает длинное название клиники до читаемого вида."""
    count_str = f" ({count})" if count > 0 else ""

    # Пробуем выделить тип отделения после последней кавычки " — самое информативное
    last_quote = clinic_name.rfind('"')
    if last_quote > 0 and last_quote < len(clinic_name) - 1:
        dept_part = clinic_name[last_quote + 1 :].strip()
        if dept_part:
            return f"{dept_part}{count_str}"

    # Если кавычек нет, берём последнее слово или сокращаем до ~50 символов
    words = clinic_name.split()
    if len(words) == 1:
        return f"{clinic_name}{count_str}"
    if len(clinic_name) > 50:
        return f"{clinic_name[:50]}...{count_str}"
    return f"{clinic_name}{count_str}"


def get_city_selection(
    p_id: str,
    cities: list[str] | None = None,
    monitoring: dict | None = None,
    clinics_data: list[ClinicInfo] | None = None,
):
    """
    Клавиатура выбора города.
    В callback_data передаём индекс города (1-based), чтобы избежать кириллицы.
    monitoring — словарь мониторинга пользователя {p_id: {d_id: {clinic_id: ...}}}
    clinics_data — список клиник с city для подсчёта мониторинга по городам.
    """
    builder = InlineKeyboardBuilder()

    # Считаем количество мониторинга на город
    p_monitoring = monitoring.get(p_id, {}) if monitoring else {}
    has_patient_monitoring = bool(p_monitoring)

    # Карта clinic_id → city
    clinic_city: dict[str, str] = {}
    if clinics_data:
        for cl in clinics_data:
            clinic_city[cl["clinic_id"]] = cl.get("city", "")

    # Считаем, сколько мониторингов в каждом городе
    city_counts: dict[str, int] = {}
    for _d_id, d_info in p_monitoring.items():
        if isinstance(d_info, dict):
            c_id = d_info.get("clinic_id", "")
            city = clinic_city.get(c_id, _("city-fallback-other"))
            city_counts[city] = city_counts.get(city, 0) + 1

    if not cities:
        total = sum(city_counts.values())
        label = (
            _("btn-all-clinics-with-count").format(count=total)
            if total > 0
            else _("btn-all-clinics")
        )
        builder.button(
            text=label,
            callback_data=CitySelect(p_id=p_id, idx="all").pack(),
        )
    else:
        for idx, city in enumerate(cities, start=1):
            cnt = city_counts.get(city, 0)
            label = (
                _("btn-city-with-count").format(city=city, count=cnt)
                if cnt > 0
                else _("btn-city").format(city=city)
            )
            builder.button(
                text=label,
                callback_data=CitySelect(p_id=p_id, idx=str(idx)).pack(),
            )
        # Кнопка "Все города"
        total = sum(city_counts.values())
        label = (
            _("btn-all-cities-with-count").format(count=total)
            if total > 0
            else _("btn-all-cities")
        )
        builder.button(
            text=label,
            callback_data=CitySelect(p_id=p_id, idx="all").pack(),
        )

    # Навигация и сброс
    builder.button(text=_("btn-back-to-list"), callback_data=BackToMain().pack())
    if has_patient_monitoring:
        builder.button(
            text=_("btn-reset-patient-monitoring"),
            callback_data=StopPatientMonitoring(p_id=p_id, origin="city").pack(),
        )

    builder.adjust(2)
    return builder.as_markup()


def get_clinic_selection(
    p_id: str,
    bday_str: str,
    selected_city: str | None = None,
    monitoring: dict | None = None,
    clinic_names: dict[str, str] | None = None,
    clinics_data: list[ClinicInfo] | None = None,
    city_idx: str = "all",
):
    """
    Если selected_city задан — показывает только клиники этого города.
    Если selected_city не задан или '__all' — все подходящие клиники.
    clinics_data: список словарей с ключами clinic_id, name, type, city.
    city_idx: индекс города из sel_cty_ (или "all"), передаётся в callback
    для возможности возврата из списка врачей обратно к клиникам.
    """
    builder = InlineKeyboardBuilder()

    if clinic_names is None:
        clinic_names = {}

    try:
        bday = datetime.strptime(bday_str, "%Y-%m-%d")
        age = relativedelta(datetime.now(), bday).years
    except (ValueError, TypeError):
        logger.exception("Не удалось распарсить дату рождения: {}", bday_str)
        age = 18

    p_monitoring = monitoring.get(p_id, {}) if monitoring else {}

    # clinics_data — обязательный параметр (получается из БД)
    clinic_list = clinics_data if clinics_data else []

    show_all = (not selected_city) or selected_city == "__all"

    for clinic in clinic_list:
        c_id = clinic["clinic_id"]
        clinic_type = clinic.get("type", "adult")

        # Фильтрация по возрасту
        if clinic_type == "child" and age >= 18:
            continue
        if clinic_type == "adult" and age < 18:
            continue

        # Фильтрация по городу
        if not show_all:
            clinic_city = clinic.get("city", "")
            if clinic_city != selected_city:
                continue

        count = sum(1 for doc in p_monitoring.values() if doc.get("clinic_id") == c_id)
        display_name = clinic_names.get(c_id) or clinic.get("name", "Unknown")
        label = _short_clinic_label(display_name, count)
        # В callback_data передаём city_idx
        # для возможности возврата из врачей обратно к клиникам
        builder.button(
            text=label,
            callback_data=ClinicSelect(
                p_id=p_id, clinic_id=c_id, city_idx=city_idx
            ).pack(),
        )

    # Навигация
    builder.button(
        text=_("btn-back-to-cities"),
        callback_data=BackToCities(p_id=p_id).pack(),
    )
    builder.button(text=_("btn-back-to-list"), callback_data=BackToMain().pack())

    # Кнопка сброса мониторинга этого пациента —
    # только если есть хоть один мониторинг у пациента
    if p_monitoring:
        builder.button(
            text=_("btn-reset-patient-monitoring"),
            callback_data=StopPatientMonitoring(
                p_id=p_id, origin="clinic", city_idx=city_idx
            ).pack(),
        )

    builder.adjust(1)
    return builder.as_markup()


def get_registration_keyboard(step: str):
    builder = InlineKeyboardBuilder()
    if step == "alias":
        builder.button(text=_("btn-skip"), callback_data=SkipAlias().pack())
    builder.button(
        text=_("btn-cancel-registration"), callback_data=CancelRegistration().pack()
    )
    builder.adjust(1)
    return builder.as_markup()
