from datetime import datetime

from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from utils.helpers import is_cabinet, shorten_fio, shorten_specialty


def get_main_menu():
    builder = ReplyKeyboardBuilder()
    builder.button(text="🔍 Настроить поиск")
    builder.button(text="🛑 Стоп все")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


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
    p_id: str, clinic_id: str, doctors_list: dict, monitored: dict
):
    builder = InlineKeyboardBuilder()

    doctors_humans = []
    doctors_cabinets = []

    for d_id, info in doctors_list.items():
        if isinstance(info, dict):
            raw_name = info.get("name", "Unknown")
            raw_spec = info.get("specialty", "")
        else:
            raw_name = d_id
            raw_spec = ""

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

    clinics = {
        "272": {"name": "Стоматологическая", "type": "all"},
        "271": {"name": "Взрослая", "type": "adult"},
        "161": {"name": "Детская", "type": "child"},
    }

    for c_id, info in clinics.items():
        if info["type"] == "child" and age >= 18:
            continue
        if info["type"] == "adult" and age < 18:
            continue

        # Считаем сколько врачей мониторится в этой клинике
        count = sum(1 for doc in p_monitoring.values() if doc.get("clinic_id") == c_id)
        label = f"{info['name']} ({count})" if count > 0 else info["name"]
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
