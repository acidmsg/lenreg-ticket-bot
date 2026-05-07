import logging
import asyncio
import json
import aiofiles
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from keyboards.inline import get_main_menu, get_patient_selection, get_doctor_selection, get_confirm_deletion, get_clinic_selection
from database.manager import DatabaseManager
from api.zdrav_client import ZdravClient
from config import settings
from utils.cache import spam_cache, load_monitoring_cache, save_monitoring_cache, update_cache_key, delete_cache_key

router = Router()
logger = logging.getLogger(__name__)


async def get_doctors_for_clinic(clinic_id: str) -> dict:
    """Загружает справочник врачей для клиники (async)."""
    import os
    if not os.path.exists(settings.DOCTORS_PATH):
        return {}
    try:
        async with aiofiles.open(settings.DOCTORS_PATH, "r", encoding="utf-8") as f:
            content = await f.read()
            data = json.loads(content)
            return data.get(str(clinic_id), {}).get("doctors", {})
    except Exception as e:
        logger.error(f"Ошибка чтения справочника врачей: {e}")
        return {}


@router.message(Command("start"))
async def cmd_start(message: Message, db: DatabaseManager):
    uid = str(message.from_user.id) if message.from_user else "unknown"
    user_data = db.get_user_data(uid)

    if not user_data.get("patients"):
        await message.answer(
            "Привет! Я помогу тебе мониторить наличие талонов к врачам.\n\n"
            "У тебя пока нет добавленных пациентов. Давай добавим первого!",
            reply_markup=get_patient_selection({}, {})
        )
    else:
        await message.answer(
            "**Ваши пациенты:**\n---\nВыберите пациента для настройки мониторинга",
            reply_markup=get_patient_selection(user_data["patients"], user_data["monitoring"]),
            parse_mode="Markdown"
        )

@router.callback_query(F.data == "back_to_main")
async def back_to_main(call: CallbackQuery, db: DatabaseManager):
    if not call.from_user or not call.message:
        return
    uid = str(call.from_user.id)
    user_data = db.get_user_data(uid)
    if isinstance(call.message, Message):
        try:
            await call.message.edit_text(
                "**Ваши пациенты:**\n---\nВыберите пациента для настройки мониторинга",
                reply_markup=get_patient_selection(user_data["patients"], user_data["monitoring"]),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Не удалось обновить сообщение (back_to_main): {e}")


@router.callback_query(F.data.startswith("sel_p_"))
async def select_patient(call: CallbackQuery, db: DatabaseManager):
    if not call.message or not call.from_user or not call.data:
        return
    p_id = call.data.replace("sel_p_", "")
    uid = str(call.from_user.id)
    user_data = db.get_user_data(uid)
    p_info = user_data["patients"].get(p_id, {})

    try:
        if isinstance(call.message, Message):
            await call.message.edit_text(
                "Выберите поликлинику:",
                reply_markup=get_clinic_selection(p_id, p_info.get("bday", "1990-01-01"))
            )
    except Exception as e:
        logger.warning(f"Не удалось обновить сообщение (select_patient): {e}")

@router.callback_query(F.data.startswith("sel_c_"))
async def select_clinic(call: CallbackQuery, db: DatabaseManager, api: ZdravClient):
    if not call.message or not call.from_user or not call.data:
        return
    parts = call.data.split("_")
    if len(parts) < 4:
        logger.error(f"Неверный формат callback_data: {call.data}")
        return

    p_id, clinic_id = parts[2], parts[3]
    uid = str(call.from_user.id)
    user_data = db.get_user_data(uid)
    p_info = user_data["patients"].get(p_id, {})
    confirmed = p_info.get("confirmed_clinics", [])

    if int(clinic_id) not in confirmed:
        is_affiliated = await api.check_affiliation(p_id, clinic_id)
        if not is_affiliated:
            await call.answer("Вы не прикреплены к этой поликлинике. Пожалуйста, выберите другое отделение.", show_alert=True)
            return
        await db.add_confirmed_clinic(uid, p_id, int(clinic_id))

    doctors_list = await get_doctors_for_clinic(clinic_id)
    monitored = user_data["monitoring"].get(p_id, {})

    try:
        if isinstance(call.message, Message):
            await call.message.edit_text(
                "Выберите врачей для мониторинга:",
                reply_markup=get_doctor_selection(p_id, clinic_id, doctors_list, monitored)
            )
    except Exception as e:
        logger.warning(f"Не удалось обновить сообщение (select_clinic): {e}")

@router.callback_query(F.data.startswith("tgl_"))
async def toggle_doctor(call: CallbackQuery, db: DatabaseManager, api: ZdravClient):
    if not call.message or not call.from_user or not call.data:
        return

    if call.from_user.id in spam_cache:
        await call.answer("Подождите немного...", show_alert=True)
        return
    spam_cache[call.from_user.id] = True

    # Валидация формата callback_data
    parts = call.data.split("_")
    if len(parts) != 4:
        logger.error(f"Неверный формат tgl callback_data: {call.data}")
        await call.answer("Ошибка формата данных", show_alert=True)
        return

    _, p_id, clinic_id, d_id = parts
    uid = str(call.from_user.id)

    user_data = db.get_user_data(uid)
    doctors_list = await get_doctors_for_clinic(clinic_id)
    doc_info = doctors_list.get(d_id, {})
    d_name = doc_info.get("name", "Врач")
    d_spec = doc_info.get("specialty", "")

    already_monitored = d_id in user_data["monitoring"].get(p_id, {})

    await db.toggle_monitoring(uid, p_id, d_id, d_name, clinic_id, d_spec)

    if already_monitored:
        user_data = db.get_user_data(uid)
        monitored = user_data["monitoring"].get(p_id, {})

        cache_key = f"{uid}_{p_id}_{d_id}"
        await delete_cache_key(cache_key)

        try:
            if isinstance(call.message, Message):
                await call.message.edit_text(
                    f"Мониторинг для {d_name} отключен.",
                    reply_markup=get_doctor_selection(p_id, clinic_id, doctors_list, monitored)
                )
        except Exception as e:
            logger.warning(f"Не удалось обновить сообщение (toggle off): {e}")
        return

    await call.answer("Ищу номерки...")
    slots = await api.check_slots(d_id, p_id, clinic_id)

    # Сохраняем в кэш мониторинга, чтобы избежать дублирующих уведомлений
    if slots is not None:
        cache_key = f"{uid}_{p_id}_{d_id}"
        await update_cache_key(cache_key, slots if slots else "NONE")

    user_data = db.get_user_data(uid)
    monitored = user_data["monitoring"].get(p_id, {})

    # Отправляем новое сообщение вместо редактирования текущего
    p_info = user_data.get("patients", {}).get(p_id, {})
    p_label = p_info.get("alias") or p_info.get("fio", "Пациент")
    d_spec = doc_info.get("specialty", "")
    spec_text = f"[{d_spec}]\n" if d_spec else ""

    has_slots = bool(slots)
    status_text = "есть номерки!" if has_slots else "пока номерков нет"
    slots_display = "\n".join(slots) if has_slots else "Как только они появятся, я сразу дам знать!"
    link = f"\n\n[Записаться](https://zdrav.lenreg.ru/signup/free/)" if has_slots else ""

    text = f"{spec_text}{d_name}:\n{p_label}\n{status_text}\n\n{slots_display}{link}"

    # Новое сообщение
    new_msg = await call.message.answer(text)

    # Сохраняем message_id в базу для будущих обновлений
    await db.set_last_message_id(uid, p_id, d_id, new_msg.message_id)

    # Ответ на callback
    await call.answer("Готово!")


@router.callback_query(F.data.startswith("del_p_"))
async def handle_delete_patient(call: CallbackQuery, db: DatabaseManager):
    if not call.message or not call.from_user or not call.data:
        return
    parts = call.data.split("_")
    if len(parts) < 4:
        logger.error(f"Неверный формат del_p callback_data: {call.data}")
        return

    action, p_id = parts[2], parts[3]
    uid = str(call.from_user.id)

    if action == "ask" and isinstance(call.message, Message):
        await call.message.edit_text(
            "Вы уверены, что хотите удалить этого пациента?",
            reply_markup=get_confirm_deletion(p_id)
        )
    elif action == "yes" and isinstance(call.message, Message):
        await db.delete_patient(uid, p_id)
        user_data = db.get_user_data(uid)
        await call.message.edit_text(
            "**Список пациентов:**\n---\nВыберите пациента\nдля настройки мониторинга",
            reply_markup=get_patient_selection(user_data["patients"], user_data["monitoring"]),
            parse_mode="Markdown"
        )
