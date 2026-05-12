from datetime import datetime

from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.utils.helpers import is_cabinet, is_child, shorten_fio, shorten_specialty


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

        builder.button(text=label, callback_data=f"sel_p_{p_id}")
        builder.button(text="🗑", callback_data=f"del_p_ask_{p_id}")

    builder.button(text="➕ Добавить пациента", callback_data="start_add_p")

    # Определяем, есть ли хоть один активный мониторинг
    has_active_monitoring = any(len(docs) > 0 for docs in monitoring.values())

    if has_active_monitoring:
        builder.button(text="🛑 Сбросить весь мониторинг", callback_data="stop_all")

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
    _dental_clinic_id = "272"
    is_dental = clinic_id == _dental_clinic_id
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
        builder.button(text=label, callback_data=f"tgl_{p_id}_{clinic_id}_{d_id}")

    # Кнопки кабинетов (без разделителя)
    for doc in doctors_cabinets:
        d_id = doc["id"]
        status = "✅ " if d_id in monitored else "▫️ "
        label = f"{status}{doc['name']}"
        builder.button(text=label, callback_data=f"tgl_{p_id}_{clinic_id}_{d_id}")

    # Навигация
    builder.button(
        text="⬅️ К выбору клиники",
        callback_data=f"back_to_clinics_{p_id}_{city_idx}",
    )
    builder.button(text="⬅️ Назад к списку", callback_data="back_to_main")

    # Кнопка сброса мониторинга этой клиники —
    # только если есть мониторинг в этой клинике
    has_clinic_monitoring = any(
        isinstance(d_info, dict) and d_info.get("clinic_id") == clinic_id
        for d_info in monitored.values()
    )
    if has_clinic_monitoring:
        builder.button(
            text="🛑 Сбросить мониторинг этой клиники",
            callback_data=f"stop_clinic_{p_id}_{clinic_id}",
        )

    builder.adjust(1, 1)
    return builder.as_markup()


def get_confirm_deletion(p_id: str):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить", callback_data=f"del_p_yes_{p_id}")
    builder.button(text="❌ Нет", callback_data=f"sel_p_{p_id}")
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
    if len(clinic_name) > 50:
        return f"{clinic_name[:50]}...{count_str}"
    return f"{clinic_name}{count_str}"


def get_city_selection(
    p_id: str,
    cities: list[str] | None = None,
    monitoring: dict | None = None,
    clinics_data: list[dict] | None = None,
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
    for d_id, d_info in p_monitoring.items():
        if isinstance(d_info, dict):
            c_id = d_info.get("clinic_id", "")
            city = clinic_city.get(c_id, "Прочее")
            city_counts[city] = city_counts.get(city, 0) + 1

    if not cities:
        total = sum(city_counts.values())
        label = f"🏥 Все клиники ({total})" if total > 0 else "🏥 Все клиники"
        builder.button(text=label, callback_data=f"sel_cty_{p_id}_all")
    else:
        for idx, city in enumerate(cities, start=1):
            cnt = city_counts.get(city, 0)
            label = f"📍 {city} ({cnt})" if cnt > 0 else f"📍 {city}"
            builder.button(text=label, callback_data=f"sel_cty_{p_id}_{idx}")
        # Кнопка "Все города"
        total = sum(city_counts.values())
        label = f"🏥 Все ({total})" if total > 0 else "🏥 Все"
        builder.button(text=label, callback_data=f"sel_cty_{p_id}_all")

    # Навигация и сброс
    builder.button(text="⬅️ Назад к списку", callback_data="back_to_main")
    if has_patient_monitoring:
        builder.button(
            text="🛑 Сбросить мониторинг этого пациента",
            callback_data=f"stop_patient_{p_id}_city",
        )

    builder.adjust(2)
    return builder.as_markup()


def get_clinic_selection(
    p_id: str,
    bday_str: str,
    selected_city: str | None = None,
    monitoring: dict | None = None,
    clinic_names: dict[str, str] | None = None,
    clinics_data: list[dict] | None = None,
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
        age = (datetime.now() - bday).days // 365
    except ValueError, TypeError:
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
        builder.button(text=label, callback_data=f"sel_c_{p_id}_{c_id}_{city_idx}")

    # Навигация
    builder.button(
        text="⬅️ К выбору города",
        callback_data=f"back_to_cities_{p_id}",
    )
    builder.button(text="⬅️ Назад к списку", callback_data="back_to_main")

    # Кнопка сброса мониторинга этого пациента —
    # только если есть хоть один мониторинг у пациента
    if p_monitoring:
        builder.button(
            text="🛑 Сбросить мониторинг этого пациента",
            callback_data=f"stop_patient_{p_id}_clinic_{city_idx}",
        )

    builder.adjust(1)
    return builder.as_markup()


def get_registration_keyboard(step: str):
    builder = InlineKeyboardBuilder()
    if step == "alias":
        builder.button(text="Пропустить", callback_data="skip_alias")
    builder.button(text="❌ Отмена регистрации", callback_data="cancel_registration")
    builder.adjust(1)
    return builder.as_markup()
