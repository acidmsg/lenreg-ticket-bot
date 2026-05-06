from datetime import datetime
from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

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
    adjustments = [2] * len(patients) + [1]
    builder.adjust(*adjustments)
    return builder.as_markup()

def get_doctor_selection(p_id: str, clinic_id: str, doctors_list: dict, monitored: dict):
    builder = InlineKeyboardBuilder()

    docs_to_sort = []
    for d_id, info in doctors_list.items():
        if isinstance(info, dict):
            docs_to_sort.append({
                "id": d_id,
                "name": info.get("name", "Unknown"),
                "specialty": info.get("specialty", "Врач")
            })
        else:
            docs_to_sort.append({
                "id": info,
                "name": d_id,
                "specialty": "Врач"
            })

    docs_to_sort.sort(key=lambda x: x["specialty"])

    for doc in docs_to_sort:
        d_id = doc["id"]
        status = "✅ " if d_id in monitored else "▫️ "
        label = f"{status}[{doc['specialty']}] {doc['name']}"
        builder.button(text=label, callback_data=f"tgl_{p_id}_{clinic_id}_{d_id}")

    builder.button(text="⬅️ Назад к списку", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_confirm_deletion(p_id: str):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить", callback_data=f"del_p_yes_{p_id}")
    builder.button(text="❌ Нет", callback_data=f"sel_p_{p_id}")
    builder.adjust(2)
    return builder.as_markup()

def get_clinic_selection(p_id: str, bday_str: str):
    builder = InlineKeyboardBuilder()

    # Расчет возраста
    try:
        bday = datetime.strptime(bday_str, "%Y-%m-%d")
        age = (datetime.now() - bday).days // 365
    except:
        age = 18

    clinics = {
        "272": {"name": "Стоматологическая", "type": "all"},
        "271": {"name": "Взрослая", "type": "adult"},
        "161": {"name": "Детская", "type": "child"}
    }

    for c_id, info in clinics.items():
        if info["type"] == "child" and age >= 18:
            continue
        if info["type"] == "adult" and age < 18:
            continue

        builder.button(text=info["name"], callback_data=f"sel_c_{p_id}_{c_id}")

    builder.button(text="⬅️ Назад к списку", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_skip_alias_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Пропустить", callback_data="skip_alias")
    return builder.as_markup()
