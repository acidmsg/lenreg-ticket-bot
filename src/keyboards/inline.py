from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.config import settings
from src.database.types import ClinicInfo
from src.handlers.callbacks import (
    CB_ADD_PATIENT,
    CB_BACK_TO_MAIN,
    CB_CANCEL_REGISTRATION,
    CB_FILTER_BACK,
    CB_FILTER_CANCEL,
    CB_FILTER_DONE,
    CB_FILTER_SKIP,
    CB_SKIP_ALIAS,
    CB_STOP_ALL,
    FILTER_WIZARD_STEPS,
    FILTER_WIZARD_SUMMARY_STEP,
    BackToCities,
    BackToClinics,
    BookConfirm,
    BookSlot,
    CitySelect,
    ClinicSelect,
    CloseSection,
    DeletePatientAsk,
    DeletePatientConfirm,
    DoctorSection,
    FilterSetup,
    PatientSelect,
    SelectPatientForBooking,
    StartMonitoring,
    StopClinicMonitoring,
    StopPatientMonitoring,
)
from src.i18n import _
from src.utils.helpers import (
    format_slot_date,
    is_cabinet,
    is_child,
    shorten_fio,
    shorten_specialty,
)


def get_main_menu_keyboard(
    mini_app_url: str | None = None,
) -> ReplyKeyboardMarkup | None:
    """Создаёт reply-клавиатуру с кнопками Mini App и «Мои записи».

    Если mini_app_url не указан или пуст — возвращает None.
    """
    if not mini_app_url:
        return None

    buttons = [
        [KeyboardButton(text="🌐 Поиск талонов", web_app=WebAppInfo(url=mini_app_url))],
        [KeyboardButton(text="📋 Мои записи")],
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

    builder.button(text=_("btn-add-patient"), callback_data=CB_ADD_PATIENT)

    # Определяем, есть ли хоть один активный мониторинг
    has_active_monitoring = any(len(docs) > 0 for docs in monitoring.values())

    if has_active_monitoring:
        builder.button(
            text=_("btn-reset-all-monitoring"),
            callback_data=CB_STOP_ALL,
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
            callback_data=DoctorSection(
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
            callback_data=DoctorSection(
                p_id=p_id, clinic_id=clinic_id, d_id=d_id
            ).pack(),
        )

    # Навигация
    builder.button(
        text=_("btn-back-to-clinics"),
        callback_data=BackToClinics(p_id=p_id, city_idx=city_idx).pack(),
    )
    builder.button(text=_("btn-back-to-list"), callback_data=CB_BACK_TO_MAIN)

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
    builder.button(text=_("btn-back-to-list"), callback_data=CB_BACK_TO_MAIN)
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

    patient_is_child = is_child(bday_str)

    p_monitoring = monitoring.get(p_id, {}) if monitoring else {}

    # clinics_data — обязательный параметр (получается из БД)
    clinic_list = clinics_data if clinics_data else []

    show_all = (not selected_city) or selected_city == "__all"

    for clinic in clinic_list:
        c_id = clinic["clinic_id"]
        clinic_type = clinic.get("type", "adult")

        # Фильтрация по возрасту
        if clinic_type == "child" and not patient_is_child:
            continue
        if clinic_type == "adult" and patient_is_child:
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
    builder.button(text=_("btn-back-to-list"), callback_data=CB_BACK_TO_MAIN)

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
        builder.button(text=_("btn-skip"), callback_data=CB_SKIP_ALIAS)
    builder.button(
        text=_("btn-cancel-registration"), callback_data=CB_CANCEL_REGISTRATION
    )
    builder.adjust(1)
    return builder.as_markup()


# ── Новые клавиатурные хелперы для PopupSection (Фаза 1 рефакторинга UX) ──


def get_slot_grid_keyboard(
    slots_result,
    p_id: str,
    clinic_id: str,
    d_id: str,
):
    """Клавиатура-сетка слотов, сгруппированных по датам.

    Для каждой даты — ряд кнопок с временем. Каждый слот — кнопка с callback
    BookSlot (prefix="book_slot"): в callback передаются только идентификаторы
    (§11.1.2), дата и время остаются в тексте кнопки и берутся из ``DateInfo``.

    Args:
        slots_result: CheckSlotsResult с полем .slots (список AppointmentSlot).
        p_id: ID пациента.
        clinic_id: ID клиники.
        d_id: ID врача.
    """
    from collections import defaultdict

    builder = InlineKeyboardBuilder()

    # Группируем слоты по дате
    by_date: dict[str, list[tuple[str, str]]] = defaultdict(list)
    # ключ = дата (ДД.ММ.ГГГГ), значение = список (время, appointment_id)

    for slot in slots_result.slots:
        date_display = format_slot_date(slot.date_start)
        by_date[date_display].append((slot.date_start.time, slot.id))

    # Сортируем даты
    for date_display in sorted(by_date.keys()):
        time_slots = sorted(by_date[date_display], key=lambda x: x[0])

        for time_str, appointment_id in time_slots:
            label = f"📅 {date_display} в {time_str}"
            builder.button(
                text=label,
                callback_data=BookSlot(
                    p_id=p_id,
                    clinic_id=clinic_id,
                    d_id=d_id,
                    appointment_id=appointment_id,
                ).pack(),
            )

    builder.adjust(1)
    return builder.as_markup()


def get_monitoring_action(
    p_id: str,
    clinic_id: str,
    d_id: str,
    is_monitored: bool,
) -> tuple[str, str]:
    """Возвращает пару (текст, callback_data) кнопки мониторинга секции врача.

    Если врач отслеживается — кнопка ведёт в мастер настройки фильтра (§9.3.1),
    иначе — добавляет врача в отслеживание.

    Args:
        p_id: ID пациента.
        clinic_id: ID клиники.
        d_id: ID врача.
        is_monitored: Врач уже отслеживается для этой пары пациент + врач.
    """
    if is_monitored:
        callback_data = FilterSetup(
            p_id=p_id,
            clinic_id=clinic_id,
            d_id=d_id,
        ).pack()
        return _("btn-filter-setup"), callback_data

    callback_data = StartMonitoring(
        p_id=p_id,
        clinic_id=clinic_id,
        d_id=d_id,
    ).pack()
    return _("btn-start-monitoring"), callback_data


def get_filter_wizard_keyboard(step: str):
    """Клавиатура шага мастера фильтра (§9.3.4).

    Шаги ввода (1–5): [⏭ Пропустить] + [↩ Назад] (кроме первого) + [✕ Отмена].
    Шаг подтверждения: [✅ Готово] + [↩ Назад] + [✕ Отмена].

    Args:
        step: Имя состояния шага мастера (из ``FILTER_WIZARD_STEPS``
            либо ``FILTER_WIZARD_SUMMARY_STEP``).
    """
    builder = InlineKeyboardBuilder()
    if step == FILTER_WIZARD_SUMMARY_STEP:
        builder.button(text=_("btn-filter-done"), callback_data=CB_FILTER_DONE)
    else:
        builder.button(text=_("btn-filter-skip"), callback_data=CB_FILTER_SKIP)
    if step != FILTER_WIZARD_STEPS[0]:
        builder.button(text=_("btn-filter-back"), callback_data=CB_FILTER_BACK)
    builder.button(text=_("btn-filter-cancel"), callback_data=CB_FILTER_CANCEL)
    builder.adjust(1)
    return builder.as_markup()


def get_filter_summary_keyboard():
    """Клавиатура шага подтверждения фильтра: [✅ Готово] + [↩ Назад] + [✕ Отмена]."""
    return get_filter_wizard_keyboard(FILTER_WIZARD_SUMMARY_STEP)


def get_doctor_section_keyboard(
    p_id: str,
    clinic_id: str,
    d_id: str,
    is_monitored: bool = False,
):
    """Клавиатура секции врача: кнопка мониторинга + [✕ Закрыть].

    Кнопка мониторинга переключается по состоянию отслеживания: [🔔 В отслеживание]
    при ``is_monitored=False`` и [🔎 Настроить фильтр] при ``is_monitored=True``.

    Args:
        p_id: ID пациента.
        clinic_id: ID клиники.
        d_id: ID врача.
        is_monitored: Врач уже отслеживается для этой пары пациент + врач.
    """
    builder = InlineKeyboardBuilder()
    action_text, action_callback = get_monitoring_action(
        p_id, clinic_id, d_id, is_monitored
    )
    builder.button(text=action_text, callback_data=action_callback)
    builder.button(
        text=_("btn-close-section"),
        callback_data=CloseSection(p_id=p_id).pack(),
    )
    builder.adjust(1)
    return builder.as_markup()


def get_booking_section_confirm_keyboard(
    p_id: str,
    clinic_id: str,
    d_id: str,
    appointment_id: str,
):
    """Клавиатура подтверждения записи (новый flow — из PopupSection):
    [✅ Подтвердить] [↩ Назад].

    Кнопка «Назад» возвращает в DoctorSection (re-query слотов).
    ``BookConfirm`` несёт только идентификаторы (§11.1.3); дата и время
    на шаге подтверждения резолвятся заново из свежего ``check_slots()``.

    Args:
        p_id: ID пациента.
        clinic_id: ID клиники.
        d_id: ID врача.
        appointment_id: ID слота из API.
    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text=_("btn-booking-confirm"),
        callback_data=BookConfirm(
            p_id=p_id,
            clinic_id=clinic_id,
            d_id=d_id,
            appointment_id=appointment_id,
        ).pack(),
    )
    builder.button(
        text=_("btn-booking-back"),
        callback_data=DoctorSection(
            p_id=p_id,
            clinic_id=clinic_id,
            d_id=d_id,
        ).pack(),
    )
    builder.adjust(2)
    return builder.as_markup()


def get_patient_select_keyboard(
    patients: list[dict],
    clinic_id: str,
    d_id: str,
):
    """Клавиатура выбора пациента для записи к врачу.

    Args:
        patients: Список пациентов [{"p_id": str, "name": str}, ...].
        clinic_id: ID клиники.
        d_id: ID врача.
    """
    builder = InlineKeyboardBuilder()

    for pat in patients:
        builder.button(
            text=f"👤 {pat['name']}",
            callback_data=SelectPatientForBooking(
                p_id=pat["p_id"],
                clinic_id=clinic_id,
                d_id=d_id,
            ).pack(),
        )

    builder.adjust(1)
    return builder.as_markup()
