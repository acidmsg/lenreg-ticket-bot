import asyncio
import json
import logging
import os

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from api.zdrav_client import ZdravClient
from config import CLINICS_REGISTRY, settings
from database.manager import DatabaseManager
from keyboards.inline import (
    get_clinic_selection,
    get_confirm_deletion,
    get_doctor_selection,
    get_main_menu,
    get_patient_selection,
)
from utils.cache import delete_cache_keys_by_prefix, spam_cache
from utils.helpers import is_child, shorten_fio, shorten_specialty

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("start"))
async def cmd_start(message: Message, db: DatabaseManager):
    uid = str(message.from_user.id) if message.from_user else "unknown"
    user_data = db.get_user_data(uid)

    if not user_data.get("patients"):
        await message.answer(
            "👋 Привет! Я помогу тебе мониторить наличие талонов к врачам.\n\n"
            "У тебя пока нет добавленных пациентов. Давай добавим первого!",
            reply_markup=get_patient_selection({}, {}),
        )
    else:
        await message.answer(
            "📋 **Ваши пациенты:**\n---\nВыберите пациента для настройки мониторинга",
            reply_markup=get_patient_selection(
                user_data["patients"], user_data["monitoring"]
            ),
            parse_mode="Markdown",
        )


@router.callback_query(F.data == "back_to_main")
async def back_to_main(call: CallbackQuery, db: DatabaseManager):
    if not call.from_user or not call.message:
        return
    uid = str(call.from_user.id)
    user_data = db.get_user_data(uid)
    if isinstance(call.message, Message):
        await call.message.edit_text(
            "📋 **Ваши пациенты:**\n---\nВыберите пациента для настройки мониторинга",
            reply_markup=get_patient_selection(
                user_data["patients"], user_data["monitoring"]
            ),
            parse_mode="Markdown",
        )


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
                "🏥 Выберите поликлинику:",
                reply_markup=get_clinic_selection(
                    p_id,
                    p_info.get("bday", settings.DEFAULT_BIRTHDAY),
                    monitoring=user_data.get("monitoring"),
                ),
            )
    except Exception:
        pass


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
            await call.answer(
                "❌ Вы не прикреплены к этой поликлинике. Пожалуйста, выберите другое отделение.",
                show_alert=True,
            )
            return
        await db.add_confirmed_clinic(uid, p_id, int(clinic_id))

    doctors_list = await db.get_doctors_for_clinic(clinic_id)
    monitored = user_data["monitoring"].get(p_id, {})

    try:
        if isinstance(call.message, Message):
            await call.message.edit_text(
                "⚙️ Выберите врачей для мониторинга:",
                reply_markup=get_doctor_selection(
                    p_id, clinic_id, doctors_list, monitored, p_info.get("bday", "")
                ),
            )
    except Exception:
        pass


@router.callback_query(F.data.startswith("tgl_"))
async def toggle_doctor(
    call: CallbackQuery, db: DatabaseManager, api: ZdravClient, bot: Bot
):
    if not call.message or not call.from_user or not call.data:
        return

    # Защита от спама -- тихо игнорируем повторные нажатия
    if call.from_user.id in spam_cache:
        return
    spam_cache[call.from_user.id] = True

    _, p_id, clinic_id, d_id = call.data.split("_")
    uid = str(call.from_user.id)

    user_data = db.get_user_data(uid)
    doctors_list = await db.get_doctors_for_clinic(clinic_id)
    doc_info = doctors_list.get(d_id, {})
    d_name = doc_info.get("name", "Врач")
    d_spec = doc_info.get("specialty", "")

    # Применяем псевдонимы для отображения
    d_name_display = shorten_fio(d_name)
    d_spec_display = shorten_specialty(d_spec)

    already_monitored = d_id in user_data["monitoring"].get(p_id, {})

    display_name = (
        f"[{d_spec_display}] {d_name_display}" if d_spec_display else d_name_display
    )
    await db.toggle_monitoring(uid, p_id, d_id, d_name, clinic_id, d_spec)

    p_info = user_data.get("patients", {}).get(p_id, {})

    if already_monitored:
        user_data = db.get_user_data(uid)
        monitored = user_data["monitoring"].get(p_id, {})

        # Удаляем связанное сообщение из чата
        msg_key = f"{p_id}_{d_id}"
        msg_id = user_data["last_messages"].get(msg_key)
        if msg_id:
            try:
                await bot.delete_message(uid, msg_id)
            except Exception:
                pass
            del user_data["last_messages"][msg_key]
            await db.update_user(uid, {"last_messages": user_data["last_messages"]})

        cache_key = f"{uid}_{p_id}_{d_id}"
        if os.path.exists(settings.CACHE_PATH):
            try:
                with open(settings.CACHE_PATH, "r", encoding="utf-8") as f:
                    last_seen_cache = json.load(f)
                if cache_key in last_seen_cache:
                    del last_seen_cache[cache_key]
                    with open(settings.CACHE_PATH, "w", encoding="utf-8") as f:
                        json.dump(last_seen_cache, f, ensure_ascii=False, indent=4)
            except Exception:
                pass

        try:
            if isinstance(call.message, Message):
                await call.message.edit_text(
                    f"⚙️ Мониторинг для {d_name_display} отключен.",
                    reply_markup=get_doctor_selection(
                        p_id, clinic_id, doctors_list, monitored, p_info.get("bday", "")
                    ),
                )
        except Exception:
            pass
        return

    await call.answer("⏳ Ищу номерки...")
    slots = await api.check_slots(d_id, p_id, clinic_id)

    # Сохраняем в кэш мониторинга, чтобы избежать дублирующих уведомлений
    if slots is not None:
        cache_key = f"{uid}_{p_id}_{d_id}"
        try:
            current_cache = {}
            if os.path.exists(settings.CACHE_PATH):
                with open(settings.CACHE_PATH, "r", encoding="utf-8") as f:
                    current_cache = json.load(f)

            current_cache[cache_key] = slots if slots else "NONE"

            with open(settings.CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(current_cache, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Ошибка обновления кэша при включении: {e}")

    user_data = db.get_user_data(uid)
    monitored = user_data["monitoring"].get(p_id, {})

    # Отправляем новое сообщение вместо редактирования текущего
    p_label = p_info.get("alias") or p_info.get("fio", "Пациент")
    d_spec_display = shorten_specialty(doc_info.get("specialty", ""))
    spec_text = f"[{d_spec_display}]\n" if d_spec_display else ""

    has_slots = bool(slots)
    status_text = "есть номерки!" if has_slots else "пока номерков нет 🤷‍♂️"
    slots_display = (
        "\n".join(slots) if has_slots else "Как только они появятся, я сразу дам знать!"
    )
    link = (
        f"\n\n🔗 [Записаться](https://zdrav.lenreg.ru/signup/free/)"
        if has_slots
        else ""
    )

    text = f"{spec_text}🧑‍⚕️{d_name_display}:\n👤 {p_label}\n{status_text}\n\n{slots_display}{link}"

    # Новое сообщение
    new_msg = await call.message.answer(text)

    # Сохраняем message_id в базу для будущих обновлений
    await db.set_last_message_id(uid, p_id, d_id, new_msg.message_id)

    # Ответ на callback
    await call.answer("Готово!")


async def _delete_monitoring_messages(
    bot: Bot, uid: str, prefix_key: str, last_messages: dict
):
    """Удаляет сообщения из чата по префиксу ключа last_messages (p_id_d_id или p_id)."""
    to_delete = []
    for key, msg_id in last_messages.items():
        if key.startswith(prefix_key):
            to_delete.append((key, msg_id))
    for key, msg_id in to_delete:
        try:
            await bot.delete_message(uid, msg_id)
        except Exception:
            pass  # сообщение могло быть уже удалено
        del last_messages[key]


@router.callback_query(F.data.startswith("stop_patient_"))
async def stop_patient_monitoring(call: CallbackQuery, db: DatabaseManager, bot: Bot):
    """Сброс мониторинга для конкретного пациента (все клиники)."""
    if not call.data or not call.from_user or not call.message:
        return
    p_id = call.data.replace("stop_patient_", "")
    uid = str(call.from_user.id)
    user_data = db.get_user_data(uid)

    # Удаляем сообщения для этого пациента
    await _delete_monitoring_messages(bot, uid, f"{p_id}_", user_data["last_messages"])

    if p_id in user_data["monitoring"]:
        del user_data["monitoring"][p_id]
        await db.update_user(
            uid,
            {
                "monitoring": user_data["monitoring"],
                "last_messages": user_data["last_messages"],
            },
        )

    # Очищаем кэш слотов для этого пациента
    await delete_cache_keys_by_prefix(f"{uid}_{p_id}_")

    if isinstance(call.message, Message):
        await call.message.edit_text(
            "✅ Мониторинг для пациента сброшен.",
            reply_markup=get_clinic_selection(
                p_id,
                user_data["patients"]
                .get(p_id, {})
                .get("bday", settings.DEFAULT_BIRTHDAY),
                monitoring=user_data.get("monitoring"),
            ),
        )


@router.callback_query(F.data.startswith("stop_clinic_"))
async def stop_clinic_monitoring(call: CallbackQuery, db: DatabaseManager, bot: Bot):
    """Сброс мониторинга для конкретной клиники пациента."""
    if not call.data or not call.from_user or not call.message:
        return
    parts = call.data.split("_")
    if len(parts) < 4:
        return
    p_id, clinic_id = parts[2], parts[3]
    uid = str(call.from_user.id)
    user_data = db.get_user_data(uid)

    p_monitoring = user_data["monitoring"].get(p_id, {})
    # Удаляем всех врачей, принадлежащих этой клинике
    to_remove = [
        d_id
        for d_id, d_info in p_monitoring.items()
        if isinstance(d_info, dict) and d_info.get("clinic_id") == clinic_id
    ]
    for d_id in to_remove:
        del p_monitoring[d_id]

    if to_remove:
        # Удаляем сообщения для каждого отключаемого врача
        for d_id in to_remove:
            await _delete_monitoring_messages(
                bot, uid, f"{p_id}_{d_id}", user_data["last_messages"]
            )
        await db.update_user(
            uid,
            {
                "monitoring": user_data["monitoring"],
                "last_messages": user_data["last_messages"],
            },
        )
        # Очищаем кэш слотов для удалённых докторов этой клиники
        for d_id in to_remove:
            await delete_cache_keys_by_prefix(f"{uid}_{p_id}_{d_id}")

    if isinstance(call.message, Message):
        doctors_list = await db.get_doctors_for_clinic(clinic_id)
        p_info = user_data.get("patients", {}).get(p_id, {})
        await call.message.edit_text(
            "✅ Мониторинг для клиники сброшен.",
            reply_markup=get_doctor_selection(
                p_id,
                clinic_id,
                doctors_list,
                p_monitoring,
                p_info.get("bday", settings.DEFAULT_BIRTHDAY),
            ),
        )


@router.callback_query(F.data == "stop_all")
async def stop_all_monitoring(call: CallbackQuery, db: DatabaseManager, bot: Bot):
    """Сброс всего мониторинга для пользователя."""
    if not call.from_user or not call.message:
        return
    uid = str(call.from_user.id)
    user_data = db.get_user_data(uid)

    # Удаляем все сообщения мониторинга
    for key in list(user_data["last_messages"].keys()):
        msg_id = user_data["last_messages"][key]
        try:
            await bot.delete_message(uid, msg_id)
        except Exception:
            pass
        del user_data["last_messages"][key]

    await db.stop_all_monitoring(uid)
    await db.update_user(uid, {"last_messages": user_data["last_messages"]})

    # Очищаем кэш слотов для этого пользователя
    await delete_cache_keys_by_prefix(f"{uid}_")

    user_data = db.get_user_data(uid)

    if isinstance(call.message, Message):
        await call.message.edit_text(
            "✅ Весь мониторинг остановлен.",
            reply_markup=get_patient_selection(
                user_data["patients"], user_data["monitoring"]
            ),
        )


@router.callback_query(F.data == "noop")
async def handle_noop(call: CallbackQuery):
    """Заглушка для кнопки-разделителя."""
    await call.answer()


@router.callback_query(F.data.startswith("del_p_"))
async def handle_delete_patient(call: CallbackQuery, db: DatabaseManager):
    if not call.message or not call.from_user or not call.data:
        return
    parts = call.data.split("_")
    action, p_id = parts[2], parts[3]
    uid = str(call.from_user.id)

    if action == "ask" and isinstance(call.message, Message):
        await call.message.edit_text(
            "Вы уверены, что хотите удалить этого пациента?",
            reply_markup=get_confirm_deletion(p_id),
        )
    elif action == "yes" and isinstance(call.message, Message):
        await db.delete_patient(uid, p_id)
        user_data = db.get_user_data(uid)
        await call.message.edit_text(
            "📋 **Список пациентов:**\n---\nВыберите пациента\nдля настройки мониторинга",
            reply_markup=get_patient_selection(
                user_data["patients"], user_data["monitoring"]
            ),
            parse_mode="Markdown",
        )
