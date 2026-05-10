from datetime import datetime

from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import CLINICS_REGISTRY
from utils.helpers import is_cabinet, is_child, shorten_fio, shorten_specialty


def get_patient_selection(patients: dict, monitoring: dict):
    builder = InlineKeyboardBuilder()
    for p_id, p_info in patients.items():
        name = p_info.get("alias") or p_info.get("fio")
        count = len(monitoring.get(p_id, {}))
        label = f"👤 {name} ({count})" if count > 0 else f"👤 {name}"

        builder.button(text=label, callback_data=f"sel_p_{p_id}")
        builder.button(text="🗑", callback_data=f"del_p_ask_{p_id}")

    builder.button(text="➕ Добавить пациента", callback_data="start_add_p")
    # Кнопка сброса всего мониторинга — всегда внизу
    builder.button(text="🛑 Сбросить весь мониторинг", callback_data="stop_all")
    adjustments = [2] * len(patients) + [1, 1]
    builder.adjust(*adjustments)
    return builder.as_markup()


def get_doctor_selection(
    p_id: str, clinic_id: str, doctors_list: dict, monitored: dict, bday_str: str = ""
):
    builder = InlineKeyboardBuilder()

    doctors_humans = []
    doctors_cabinets = []

    # Определяем, нужно ли фильтровать по детским специальностям в стоматологии
    is_dental = clinic_id == "272"
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

    builder.button(text="⬅️ Назад к списку", callback_data="back_to_main")
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


def get_clinic_selection(p_id: str, bday_str: str, monitoring: dict | None = None):
    builder = InlineKeyboardBuilder()

    # Расчет возраста
    try:
        bday = datetime.strptime(bday_str, "%Y-%m-%d")
        age = (datetime.now() - bday).days // 365
    except:
        age = 18

    p_monitoring = monitoring.get(p_id, {}) if monitoring else {}

    for c_id, info in CLINICS_REGISTRY.items():
        if info.type == "child" and age >= 18:
            continue
        if info.type == "adult" and age < 18:
            continue

        # Считаем сколько врачей мониторится в этой клинике
        count = sum(1 for doc in p_monitoring.values() if doc.get("clinic_id") == c_id)
        label = f"{info.name} ({count})" if count > 0 else info.name
        builder.button(text=label, callback_data=f"sel_c_{p_id}_{c_id}")

    builder.button(text="⬅️ Назад к списку", callback_data="back_to_main")
    # Кнопка сброса мониторинга этого пациента (всех его клиник)
    builder.button(
        text="🛑 Сбросить мониторинг этого пациента",
        callback_data=f"stop_patient_{p_id}",
    )
    builder.adjust(1)
    return builder.as_markup()


def get_skip_alias_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Пропустить", callback_data="skip_alias")
    return builder.as_markup()
