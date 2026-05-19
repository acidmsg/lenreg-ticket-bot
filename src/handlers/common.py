import asyncio
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, FSInputFile, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger

from src.api.zdrav_client import ZdravClient
from src.assets.utils import get_nav_image_path, get_notify_image_path
from src.config import settings
from src.database.manager import DatabaseManager
from src.filters.admin import IsAdmin
from src.keyboards.inline import (
    get_city_selection,
    get_clinic_selection,
    get_confirm_deletion,
    get_doctor_selection,
    get_patient_selection,
)
from src.services.doctor_discovery import _get_clinic_type_from_db, fetch_specialties
from src.services.export import export_monitoring_csv, export_monitoring_json
from src.services.healthcheck import format_status_report
from src.utils.cache import delete_cache_keys_by_prefix, is_spam, swap_cache_key
from src.utils.helpers import (
    extract_msg_id,
    format_notification_text,
    format_slots,
    shorten_fio,
    shorten_specialty,
)

router = Router()
# Хранит city_idx последнего выбора клиники для каждого пользователя
# (нужен для кнопки "Назад к клиникам" в списке врачей)
_user_clinic_city_idx: dict[str, str] = {}  # key: f"{uid}_{p_id}_{clinic_id}"

# Словарь соответствия типа клиники → ключ изображения навигации
_CLINIC_NAV_TYPE_MAP: dict[str, str] = {
    "adult": "doctor_adult",
    "child": "doctor_child",
    "all": "doctor_dentist",
}


def _decode_city_from_idx(idx_or_all: str, cities: list[str]) -> tuple[str | None, str]:
    """Декодирует city_idx в название города и текстовую метку."""
    selected_city: str | None = None
    if idx_or_all != "all":
        try:
            idx = int(idx_or_all)
            if 1 <= idx <= len(cities):
                selected_city = cities[idx - 1]
        except (ValueError, IndexError):
            pass
    city_label = "Все клиники" if selected_city is None else f"🏥 {selected_city}"
    return selected_city, city_label


def _build_clinic_selection_kb(
    p_id: str,
    bday: str,
    selected_city: str | None,
    monitoring: dict | None,
    clinic_names: dict,
    clinics_data: list,
    city_idx: str,
):
    """Хелпер: собирает клавиатуру выбора клиники через get_clinic_selection."""
    return get_clinic_selection(
        p_id,
        bday,
        selected_city=selected_city,
        monitoring=monitoring,
        clinic_names=clinic_names,
        clinics_data=clinics_data,
        city_idx=city_idx,
    )


# ── On-demand discovery врачей (когда БД пуста для этой клиники) ──


async def _discover_doctors_on_demand(
    api: ZdravClient,
    db: DatabaseManager,
    clinic_id: str,
    p_id: str,
) -> dict:
    """
    Загружает врачей из API, сохраняет и возвращает словарь.
    Сначала пробует patient_id пользователя (он прикреплён к этой клинике),
    если не сработало — fallback на хардкодных discovery-пациентов.
    """
    try:
        clinic_type = await _get_clinic_type_from_db(db._db, clinic_id)
        patient_id_adult = settings.DISCOVERY_PATIENT_ID_ADULT
        patient_id_child = settings.DISCOVERY_PATIENT_ID_CHILD

        # Приоритет: patient_id пользователя > типовой discovery
        patient_candidates = [p_id]
        if clinic_type == "child":
            patient_candidates.append(patient_id_child)
        elif clinic_type == "all":
            patient_candidates.extend([patient_id_adult, patient_id_child])
        else:
            patient_candidates.append(patient_id_adult)

        all_doctors = []
        tried_patients = set()

        for current_patient_id in patient_candidates:
            if current_patient_id in tried_patients:
                continue
            tried_patients.add(current_patient_id)

            specialties_data = await fetch_specialties(
                api, current_patient_id, clinic_id
            )
            if not specialties_data:
                continue  # пробуем следующего пациента

            for spec_info in specialties_data:
                spec_id = spec_info.specialty_id
                spec_name = spec_info.specialty_name
                doctors = await api.fetch_all_doctors(
                    specialty_id=spec_id,
                    patient_id=current_patient_id,
                    clinic_id=clinic_id,
                )
                if doctors:
                    for doc in doctors:
                        doc["SpesialityName"] = spec_name
                    all_doctors.extend(doctors)
                await asyncio.sleep(0.3)

            # Если нашли хотя бы одного врача — хватит
            if all_doctors:
                break

        if all_doctors:
            await db.merge_doctors(clinic_id, all_doctors)
            logger.info(
                f"On-demand discovery для {clinic_id}: {len(all_doctors)} врачей "
                f"(patient={patient_candidates[0]})"
            )

        return await db.get_doctors_for_clinic(clinic_id)
    except Exception as e:
        logger.error(f"Ошибка on-demand discovery для {clinic_id}: {e}")
        return {}


# ── Единый механизм удаления сообщений из last_messages ─────


async def _delete_cleanup_msg_entry(
    bot: Bot,
    uid: str,
    key: str,
    last_messages: dict,
) -> bool:
    """
    Удаляет одно сообщение из чата и из словаря last_messages.
    Возвращает True, если сообщение было удалено.
    """
    value = last_messages.get(key)
    if value is None:
        return False

    msg_id = extract_msg_id(value)
    if msg_id:
        try:
            await bot.delete_message(uid, msg_id)
        except TelegramAPIError:
            pass
    del last_messages[key]
    return True


async def _delete_cleanup_msg_entries(
    bot: Bot,
    uid: str,
    prefix_key: str,
    last_messages: dict,
) -> bool:
    """
    Удаляет все сообщения из чата, чьи ключи начинаются с prefix_key.
    Возвращает True, если хотя бы одно сообщение было удалено.
    """
    changed = False
    for key in list(last_messages.keys()):
        if key.startswith(prefix_key):
            changed |= await _delete_cleanup_msg_entry(bot, uid, key, last_messages)
    return changed


async def _send_or_update_message(
    bot: Bot,
    chat_id: int,
    db: DatabaseManager,
    cache_key1: str,
    cache_key2: str,
    text: str,
    photo_path: Path | None = None,
    reply_markup=None,
    old_message: Message | None = None,
) -> Message | None:
    """Низкоуровневый хелпер: удалить старое → отправить новое → сохранить msg_id.

    Общий паттерн для _send_nav_photo и _send_notification:
    1. Получить last_msg_id из БД и удалить предыдущее сообщение.
    2. Опционально удалить old_message (call.message).
    3. Отправить новое сообщение (с фото или без).
    4. Сохранить message_id в БД.
    """
    uid = str(chat_id)

    last_msg_id = await db.get_last_message_id(uid, cache_key1, cache_key2)
    if last_msg_id:
        try:
            await bot.delete_message(chat_id, last_msg_id)
        except TelegramAPIError:
            pass

    if old_message is not None:
        try:
            await old_message.delete()
        except Exception:
            pass

    if photo_path is not None:
        photo = FSInputFile(photo_path)
        new_msg = await bot.send_photo(
            chat_id,
            photo,
            caption=text,
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )
    else:
        new_msg = await bot.send_message(
            chat_id,
            text,
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )

    await db.set_last_message_id(uid, cache_key1, cache_key2, new_msg.message_id)
    return new_msg


# ── Хелпер для отправки навигационных сообщений с изображением-заголовком ──


async def _send_nav_photo(
    bot: Bot | None,
    msg: Message,
    nav_type: str,
    text: str,
    reply_markup,
    db: DatabaseManager | None = None,
) -> Message | None:
    """Отправляет навигационное сообщение с изображением-заголовком.

    При наличии БД и бота: удаляет предыдущее навигационное сообщение
    (хранится в last_messages["__nav__"]), отправляет новое и сохраняет
    его message_id. Без БД — поведение как раньше (edit_text fallback).
    """
    photo_path = get_nav_image_path(nav_type)
    uid = str(msg.chat.id)
    result: Message | None = None

    if bot is not None:
        if db is not None:
            # Основной путь: используют хелпер для удаления/отправки/сохранения
            try:
                return await _send_or_update_message(
                    bot,
                    msg.chat.id,
                    db,
                    "__nav__",
                    "__nav__",
                    text,
                    photo_path=photo_path,
                    reply_markup=reply_markup,
                    old_message=msg,
                )
            except Exception:
                logger.debug(
                    "Не удалось отправить/обновить навигационное сообщение "
                    "для chat_id={}",
                    msg.chat.id,
                )

        # Путь без БД или fallback при ошибке хелпера:
        # удаляем call.message вручную и отправляем без кэширования
        try:
            await msg.delete()
        except Exception:
            pass

        try:
            if photo_path is not None:
                photo = FSInputFile(photo_path)
                result = await bot.send_photo(
                    msg.chat.id,
                    photo,
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown",
                )
            else:
                raise ValueError("no photo")
        except Exception:
            result = await bot.send_message(
                msg.chat.id,
                text,
                reply_markup=reply_markup,
                parse_mode="Markdown",
            )

        if db is not None and result is not None:
            try:
                await db.set_last_message_id(
                    uid, "__nav__", "__nav__", result.message_id
                )
            except Exception:
                logger.debug(
                    "Не удалось сохранить last_message_id для uid={} (nav)", uid
                )

        return result

    # Бот недоступен (тестовый режим или call.message без bot) —
    # используем edit_text на том же сообщении
    try:
        await msg.edit_text(
            text,
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )
        return msg
    except Exception:
        logger.debug(
            "Не удалось отредактировать сообщение (edit_text) для chat_id={}",
            msg.chat.id,
        )
        return None


# ── Сводка активного мониторинга ──────────────────────────────


def build_monitoring_summary(patients: dict, monitoring: dict) -> str:
    """Формирует текстовую сводку активного мониторинга."""
    if not monitoring:
        return ""

    lines = ["\n📊 **Активный мониторинг:**"]

    for p_id, doctors in monitoring.items():
        p_info = patients.get(p_id, {})
        p_name = p_info.get("alias") or p_info.get("fio", "Пациент")
        lines.append(f"\n👤 {p_name}")

        if not doctors:
            continue

        sorted_docs = sorted(
            doctors.items(),
            key=lambda x: x[1].get("name", "") if isinstance(x[1], dict) else str(x[1]),
        )
        for i, (d_id, d_info) in enumerate(sorted_docs):
            is_last = i == len(sorted_docs) - 1
            prefix = "  ┗" if is_last else "  ┣"
            if isinstance(d_info, dict):
                d_name = shorten_fio(d_info.get("name", "Врач"))
                d_spec = shorten_specialty(d_info.get("specialty", ""))
            else:
                d_name = str(d_info)
                d_spec = ""
            spec_part = f" ({d_spec})" if d_spec else ""
            lines.append(f"{prefix} 🧑‍⚕️ {d_name}{spec_part}")

    return "\n".join(lines)


# ── Хендлеры ──────────────────────────────────────────────────


@router.message(Command("status"), IsAdmin())
async def cmd_status(message: Message, db: DatabaseManager):
    """Команда /status — отчёт о состоянии бота (только для администраторов)."""
    if not message.from_user:
        return

    report = await format_status_report(db)
    await message.answer(report, parse_mode="Markdown")


@router.message(Command("start"))
async def cmd_start(message: Message, db: DatabaseManager, bot: Bot):
    """Команда /start — приветствие с изображением-заголовком patient_select."""
    uid = str(message.from_user.id) if message.from_user else "unknown"
    user_data = await db.get_user_data(uid)

    # Удаляем все предыдущие сообщения бота из чата
    await _delete_cleanup_msg_entries(bot, uid, "", user_data["last_messages"])
    await db.update_user(uid, {"last_messages": {}})

    if not user_data.get("patients"):
        text = (
            "👋 Привет! Я помогу тебе мониторить наличие талонов к врачам.\n\n"
            "У тебя пока нет добавленных пациентов. Давай добавим первого!"
        )
        reply_markup = get_patient_selection({}, {})
        parse_mode = None
    else:
        summary = build_monitoring_summary(
            user_data["patients"], user_data["monitoring"]
        )
        text = (
            "📋 **Ваши пациенты:**\n---\n"
            "Выберите пациента для настройки мониторинга" + summary
        )
        reply_markup = get_patient_selection(
            user_data["patients"], user_data["monitoring"]
        )
        parse_mode = "Markdown"

    photo_path = get_nav_image_path("patient")
    result_msg: Message | None = None
    try:
        if photo_path is not None:
            photo = FSInputFile(photo_path)
            result_msg = await message.answer_photo(
                photo, caption=text, reply_markup=reply_markup, parse_mode=parse_mode
            )
        else:
            result_msg = await message.answer(
                text, reply_markup=reply_markup, parse_mode=parse_mode
            )
    except Exception:
        result_msg = await message.answer(
            text, reply_markup=reply_markup, parse_mode=parse_mode
        )

    # Сохраняем ID нового навигационного сообщения
    if result_msg is not None:
        await db.set_last_message_id(uid, "__nav__", "__nav__", result_msg.message_id)


@router.callback_query(F.data == "back_to_main")
async def back_to_main(call: CallbackQuery, db: DatabaseManager):
    """Возврат в главное меню с изображением-заголовком patient_select."""
    if not call.from_user or not call.message or not isinstance(call.message, Message):
        return
    uid = str(call.from_user.id)
    user_data = await db.get_user_data(uid)

    if not user_data.get("patients"):
        text = (
            "👋 Привет! Я помогу тебе мониторить наличие талонов к врачам.\n\n"
            "У тебя пока нет добавленных пациентов. Давай добавим первого!"
        )
        reply_markup = get_patient_selection({}, {})
    else:
        summary = build_monitoring_summary(
            user_data["patients"], user_data["monitoring"]
        )
        text = (
            "📋 **Ваши пациенты:**\n---\n"
            "Выберите пациента для настройки мониторинга" + summary
        )
        reply_markup = get_patient_selection(
            user_data["patients"], user_data["monitoring"]
        )

    await _send_nav_photo(call.bot, call.message, "patient", text, reply_markup, db=db)


@router.callback_query(F.data.startswith("sel_p_"))
async def select_patient(call: CallbackQuery, db: DatabaseManager):
    """Выбор пациента → список городов с изображением clinic_select."""
    if not call.message or not call.from_user or not call.data:
        return
    p_id = call.data.replace("sel_p_", "")
    uid = str(call.from_user.id)
    user_data = await db.get_user_data(uid)
    user_data["patients"].get(p_id, {})

    # Получаем города активных клиник
    cities = await db._db.get_distinct_cities()
    clinics_data = await db._db.get_active_clinics()
    monitoring = user_data.get("monitoring")

    if isinstance(call.message, Message):
        await _send_nav_photo(
            call.bot,
            call.message,
            "clinic",
            "📍 Сначала выберите город/район:",
            get_city_selection(
                p_id,
                cities=cities,
                monitoring=monitoring,
                clinics_data=clinics_data,
            ),
            db=db,
        )


@router.callback_query(F.data.startswith("sel_cty_"))
async def select_city(call: CallbackQuery, db: DatabaseManager):
    """Выбор города → список клиник с изображением clinic_select."""
    if not call.message or not call.from_user or not call.data:
        return
    # Формат: sel_cty_{p_id}_{idx} где idx — 1-based индекс города или "all"
    parts = call.data.split("_", 3)
    if len(parts) < 4:
        return
    p_id = parts[2]
    idx_or_all = parts[3]
    uid = str(call.from_user.id)
    user_data = await db.get_user_data(uid)
    p_info = user_data["patients"].get(p_id, {})

    clinic_names = await db.get_all_clinic_names()
    clinics_data = await db._db.get_active_clinics()
    cities = await db._db.get_distinct_cities()

    selected_city, city_label = _decode_city_from_idx(idx_or_all, cities)

    if isinstance(call.message, Message):
        await _send_nav_photo(
            call.bot,
            call.message,
            "clinic",
            city_label,
            _build_clinic_selection_kb(
                p_id,
                p_info.get("bday", settings.DEFAULT_BIRTHDAY),
                selected_city=selected_city,
                monitoring=user_data.get("monitoring"),
                clinic_names=clinic_names,
                clinics_data=clinics_data,
                city_idx=idx_or_all,
            ),
            db=db,
        )


@router.callback_query(F.data.startswith("back_to_cities_"))
async def back_to_cities(call: CallbackQuery, db: DatabaseManager):
    """Возвращает к выбору города с изображением clinic_select."""
    if not call.message or not call.from_user or not call.data:
        return
    p_id = call.data.replace("back_to_cities_", "")
    uid = str(call.from_user.id)
    user_data = await db.get_user_data(uid)
    cities = await db._db.get_distinct_cities()
    clinics_data = await db._db.get_active_clinics()

    if isinstance(call.message, Message):
        await _send_nav_photo(
            call.bot,
            call.message,
            "clinic",
            "📍 Сначала выберите город/район:",
            get_city_selection(
                p_id,
                cities=cities,
                monitoring=user_data.get("monitoring"),
                clinics_data=clinics_data,
            ),
            db=db,
        )


@router.callback_query(F.data.startswith("back_to_clinics_"))
async def back_to_clinics(call: CallbackQuery, db: DatabaseManager):
    """Возвращает к списку клиник (того же города или всех).

    Используется изображение-заголовок clinic_select.
    """
    if not call.message or not call.from_user or not call.data:
        return
    # Формат: back_to_clinics_{p_id}_{city_idx}
    parts = call.data.split("_")
    if len(parts) < 5:
        return
    p_id = parts[3]
    city_idx = parts[4]  # всегда есть, т.к. len >= 5
    uid = str(call.from_user.id)
    user_data = await db.get_user_data(uid)
    p_info = user_data["patients"].get(p_id, {})

    clinic_names = await db.get_all_clinic_names()
    clinics_data = await db._db.get_active_clinics()
    cities = await db._db.get_distinct_cities()

    selected_city, city_label = _decode_city_from_idx(str(city_idx), cities)

    if isinstance(call.message, Message):
        await _send_nav_photo(
            call.bot,
            call.message,
            "clinic",
            city_label,
            _build_clinic_selection_kb(
                p_id,
                p_info.get("bday", settings.DEFAULT_BIRTHDAY),
                selected_city=selected_city,
                monitoring=user_data.get("monitoring"),
                clinic_names=clinic_names,
                clinics_data=clinics_data,
                city_idx=city_idx,
            ),
            db=db,
        )


@router.callback_query(F.data.startswith("sel_c_"))
async def select_clinic(call: CallbackQuery, db: DatabaseManager, api: ZdravClient):
    """Выбор клиники → список врачей с изображением doctor_*_select."""
    if not call.message or not call.from_user or not call.data:
        return
    parts = call.data.split("_")
    if len(parts) < 4:
        logger.error(f"Неверный формат callback_data: {call.data}")
        return

    p_id, clinic_id = parts[2], parts[3]
    # Формат: sel_c_{p_id}_{clinic_id}_{city_idx}
    city_idx = parts[4] if len(parts) >= 5 else "all"
    uid = str(call.from_user.id)
    user_data = await db.get_user_data(uid)
    p_info = user_data["patients"].get(p_id, {})
    confirmed = p_info.get("confirmed_clinics", [])

    # Добавляем клинику в confirmed, если её там ещё нет
    if int(clinic_id) not in confirmed:
        await db.add_confirmed_clinic(uid, p_id, int(clinic_id))

    doctors_list = await db.get_doctors_for_clinic(clinic_id)
    monitored = user_data["monitoring"].get(p_id, {})
    clinic_name = await db.get_clinic_name(clinic_id)

    # Сохраняем city_idx для кнопки "назад" в списке врачей
    _user_clinic_city_idx[f"{uid}_{p_id}_{clinic_id}"] = city_idx

    # Если врачей нет — делаем on-demand discovery
    if not doctors_list:
        await call.answer("⏳ Загружаю список врачей...", show_alert=False)
        doctors_list = await _discover_doctors_on_demand(api, db, clinic_id, p_id)

    # Определяем тип клиники для выбора изображения врача
    clinic_type = await _get_clinic_type_from_db(db._db, clinic_id)
    nav_type = _CLINIC_NAV_TYPE_MAP.get(clinic_type, "doctor_adult")

    clinic_line = f"\n{clinic_name}" if clinic_name else ""

    if isinstance(call.message, Message):
        await _send_nav_photo(
            call.bot,
            call.message,
            nav_type,
            f"⚙️ Выберите врачей для мониторинга:{clinic_line}",
            get_doctor_selection(
                p_id,
                clinic_id,
                doctors_list,
                monitored,
                p_info.get("bday", ""),
                city_idx,
            ),
            db=db,
        )


@router.callback_query(F.data.startswith("tgl_"))
async def toggle_doctor(
    call: CallbackQuery, db: DatabaseManager, api: ZdravClient, bot: Bot
):
    if not call.message or not call.from_user or not call.data:
        return

    # Защита от спама -- тихо игнорируем повторные нажатия
    if await is_spam(str(call.from_user.id)):
        return

    _, p_id, clinic_id, d_id = call.data.split("_")
    uid = str(call.from_user.id)

    user_data = await db.get_user_data(uid)
    doctors_list = await db.get_doctors_for_clinic(clinic_id)
    doc_info = doctors_list.get(d_id, {})
    d_name = doc_info.get("name", "Врач")
    d_spec = doc_info.get("specialty", "")

    # Применяем псевдонимы для отображения
    d_name_display = shorten_fio(d_name)
    d_spec_display = shorten_specialty(d_spec)

    already_monitored = d_id in user_data["monitoring"].get(p_id, {})

    await db.toggle_monitoring(uid, p_id, d_id, d_name, clinic_id, d_spec)

    p_info = user_data.get("patients", {}).get(p_id, {})

    if already_monitored:
        user_data = await db.get_user_data(uid)
        monitored = user_data["monitoring"].get(p_id, {})

        # Удаляем связанное сообщение из чата
        msg_key = f"{p_id}_{d_id}"
        await _delete_cleanup_msg_entry(bot, uid, msg_key, user_data["last_messages"])
        await db.update_user(uid, {"last_messages": user_data["last_messages"]})

        cache_key = f"{uid}_{p_id}_{d_id}"
        await delete_cache_keys_by_prefix(cache_key)

        # Получаем city_idx для кнопки "назад" (если есть)
        city_idx = _user_clinic_city_idx.get(f"{uid}_{p_id}_{clinic_id}", "all")

        # Определяем nav_type для изображения врача
        clinic_type = await _get_clinic_type_from_db(db._db, clinic_id)
        nav_type = _CLINIC_NAV_TYPE_MAP.get(clinic_type, "doctor_adult")

        if isinstance(call.message, Message):
            await _send_nav_photo(
                bot,
                call.message,
                nav_type,
                f"⚙️ Мониторинг для {d_name_display} отключен.",
                get_doctor_selection(
                    p_id,
                    clinic_id,
                    doctors_list,
                    monitored,
                    p_info.get("bday", ""),
                    city_idx,
                ),
                db=db,
            )
        return

    # Сразу отправляем "загрузочное" сообщение — пользователь видит, что бот работает
    p_label = p_info.get("alias") or p_info.get("fio", "Пациент")
    d_spec_display = shorten_specialty(doc_info.get("specialty", ""))
    spec_text = f"[{d_spec_display}]\n" if d_spec_display else ""

    loading_msg = await call.message.answer(
        f"{spec_text}🧑‍⚕️ {d_name_display}\n"
        f"👤 {p_label}\n⏳ Проверяю наличие номерков..."
    )

    await call.answer()
    slots = await api.check_slots(d_id, p_id, clinic_id)

    # Сохраняем в кэш мониторинга, чтобы избежать дублирующих уведомлений
    if slots is not None:
        cache_key = f"{uid}_{p_id}_{d_id}"
        await swap_cache_key(cache_key, slots if slots else "NONE")

    user_data = await db.get_user_data(uid)
    monitored = user_data["monitoring"].get(p_id, {})

    has_slots = bool(slots)
    status_text = "✅ есть номерки!" if has_slots else "Пока номерков нет 🤷‍♂️"

    if has_slots and slots:
        slot_lines = format_slots(
            slots,
            detail_threshold=settings.SLOT_DETAIL_THRESHOLD,
            compact_threshold=settings.SLOT_COMPACT_THRESHOLD,
        )
        slots_display = "\n".join(slot_lines)
    else:
        slots_display = "Как только появятся, я сразу дам знать!"

    link = f"\n\n🔗 [Записаться]({settings.SIGNUP_URL})" if has_slots else ""

    text = format_notification_text(
        p_label, d_name_display, spec_text, status_text, slots_display, link
    )

    # Удаляем загрузочное сообщение
    try:
        await loading_msg.delete()
    except Exception:
        pass

    # Отправляем финальный результат с изображением-заголовком
    notify_type = "available" if has_slots else "empty"
    photo_path = get_notify_image_path(notify_type)
    try:
        if photo_path is not None:
            photo = FSInputFile(photo_path)
            result_msg = await call.message.answer_photo(
                photo, caption=text, parse_mode="Markdown"
            )
        else:
            result_msg = await call.message.answer(text)
    except Exception:
        result_msg = await call.message.answer(text)

    # Сохраняем message_id в базу для будущих обновлений
    await db.set_last_message_id(uid, p_id, d_id, result_msg.message_id)

    # Обновляем клавиатуру выбора врачей (галочка + кнопка сброса клиники)
    city_idx = _user_clinic_city_idx.get(f"{uid}_{p_id}_{clinic_id}", "all")
    clinic_type = await _get_clinic_type_from_db(db._db, clinic_id)
    nav_type = _CLINIC_NAV_TYPE_MAP.get(clinic_type, "doctor_adult")

    if isinstance(call.message, Message):
        await _send_nav_photo(
            bot,
            call.message,
            nav_type,
            f"⚙️ Мониторинг для {d_name_display} включен.",
            get_doctor_selection(
                p_id,
                clinic_id,
                doctors_list,
                monitored,
                p_info.get("bday", ""),
                city_idx,
            ),
            db=db,
        )

    await call.answer("Готово!")


@router.callback_query(F.data.startswith("stop_patient_"))
async def stop_patient_monitoring(call: CallbackQuery, db: DatabaseManager, bot: Bot):
    """
    Сброс мониторинга для конкретного пациента.
    Формат: stop_patient_{p_id}_city или stop_patient_{p_id}_clinic_{city_idx}
    После сброса остаётся на том же контексте (города или клиники).
    """
    if not call.data or not call.from_user or not call.message:
        return
    parts = call.data.split("_")
    if len(parts) < 4:
        return
    p_id = parts[2]
    context = parts[3] if len(parts) >= 4 else "city"  # city или clinic
    city_idx = parts[4] if len(parts) >= 5 else "all"

    uid = str(call.from_user.id)
    user_data = await db.get_user_data(uid)

    # Удаляем сообщения для этого пациента
    await _delete_cleanup_msg_entries(bot, uid, f"{p_id}_", user_data["last_messages"])

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

    if isinstance(call.message, Message) and bot is not None:
        if context == "clinic":
            # Остаёмся на списке клиник
            clinic_names = await db.get_all_clinic_names()
            clinics_data = await db._db.get_active_clinics()
            cities = await db._db.get_distinct_cities()
            p_info = user_data.get("patients", {}).get(p_id, {})

            selected_city, _ = _decode_city_from_idx(str(city_idx), cities)

            await _send_nav_photo(
                bot,
                call.message,
                "clinic",
                "✅ Мониторинг для пациента сброшен.",
                get_clinic_selection(
                    p_id,
                    p_info.get("bday", settings.DEFAULT_BIRTHDAY),
                    selected_city=selected_city,
                    monitoring=user_data.get("monitoring"),
                    clinic_names=clinic_names,
                    clinics_data=clinics_data,
                    city_idx=city_idx,
                ),
                db=db,
            )
        else:
            # Остаёмся на списке городов
            cities = await db._db.get_distinct_cities()
            clinics_data = await db._db.get_active_clinics()
            await _send_nav_photo(
                bot,
                call.message,
                "clinic",
                "✅ Мониторинг для пациента сброшен.",
                get_city_selection(
                    p_id,
                    cities=cities,
                    monitoring=user_data.get("monitoring"),
                    clinics_data=clinics_data,
                ),
                db=db,
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
    user_data = await db.get_user_data(uid)

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
            await _delete_cleanup_msg_entries(
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

    if isinstance(call.message, Message) and bot is not None:
        doctors_list = await db.get_doctors_for_clinic(clinic_id)
        p_info = user_data.get("patients", {}).get(p_id, {})
        city_idx = _user_clinic_city_idx.get(f"{uid}_{p_id}_{clinic_id}", "all")

        # Определяем тип клиники для изображения врача
        clinic_type = await _get_clinic_type_from_db(db._db, clinic_id)
        nav_type = _CLINIC_NAV_TYPE_MAP.get(clinic_type, "doctor_adult")

        await _send_nav_photo(
            bot,
            call.message,
            nav_type,
            "✅ Мониторинг для клиники сброшен.",
            get_doctor_selection(
                p_id,
                clinic_id,
                doctors_list,
                p_monitoring,
                p_info.get("bday", settings.DEFAULT_BIRTHDAY),
                city_idx,
            ),
            db=db,
        )


@router.callback_query(F.data == "stop_all")
async def stop_all_monitoring(call: CallbackQuery, db: DatabaseManager, bot: Bot):
    """Сброс всего мониторинга для пользователя."""
    if not call.from_user or not call.message:
        return
    uid = str(call.from_user.id)
    user_data = await db.get_user_data(uid)

    # Удаляем все сообщения мониторинга
    await _delete_cleanup_msg_entries(bot, uid, "", user_data["last_messages"])

    await db.stop_all_monitoring(uid)
    await db.update_user(uid, {"last_messages": user_data["last_messages"]})

    # Очищаем кэш слотов для этого пользователя
    await delete_cache_keys_by_prefix(f"{uid}_")

    user_data = await db.get_user_data(uid)

    if isinstance(call.message, Message) and bot is not None:
        await _send_nav_photo(
            bot,
            call.message,
            "patient",
            "✅ Весь мониторинг остановлен.",
            get_patient_selection(user_data["patients"], user_data["monitoring"]),
            db=db,
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
        if call.bot is None:
            return
        # Удаляем сообщения из чата, связанные с пациентом
        user_data = await db.get_user_data(uid)
        await _delete_cleanup_msg_entries(
            bot=call.bot,
            uid=uid,
            prefix_key=f"{p_id}_",
            last_messages=user_data.get("last_messages", {}),
        )
        await db.delete_patient(uid, p_id)
        if not user_data.get("patients"):
            text = (
                "👋 Привет! Я помогу тебе мониторить наличие талонов к врачам.\n\n"
                "У тебя пока нет добавленных пациентов. Давай добавим первого!"
            )
            reply_markup = get_patient_selection({}, {})
        else:
            text = (
                "📋 **Список пациентов:**\n---\n"
                "Выберите пациента\nдля настройки мониторинга"
            )
            reply_markup = get_patient_selection(
                user_data["patients"], user_data["monitoring"]
            )

        if call.bot and isinstance(call.message, Message):
            await _send_nav_photo(
                call.bot,
                call.message,
                "patient",
                text,
                reply_markup,
                db=db,
            )


# ── Экспорт данных мониторинга ──────────────────────────────


@router.message(Command("export"), IsAdmin())
async def cmd_export(message: Message, db: DatabaseManager):
    """Экспорт данных мониторинга в CSV или JSON.

    Показывает пользователю inline-клавиатуру с выбором формата.
    После выбора генерирует файл и отправляет его.
    """
    if not message.from_user:
        return

    uid = str(message.from_user.id)
    user_data = await db.get_user_data(uid)

    # Проверяем, есть ли данные для экспорта
    patients = user_data.get("patients", {})
    monitoring = user_data.get("monitoring", {})

    if not patients and not monitoring:
        await message.answer(
            "📭 Нет данных для экспорта.\n\n"
            "Добавьте пациентов и настройте мониторинг, "
            "чтобы появилась информация для выгрузки."
        )
        return

    # Inline-клавиатура выбора формата
    builder = InlineKeyboardBuilder()
    builder.button(text="📄 CSV", callback_data="export_csv")
    builder.button(text="📋 JSON", callback_data="export_json")
    builder.adjust(2)

    await message.answer(
        "📊 **Выберите формат экспорта:**\n\n"
        "Будут выгружены данные по всем пациентам и истории мониторинга.",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.in_({"export_csv", "export_json"}))
async def process_export(call: CallbackQuery, db: DatabaseManager, bot: Bot):
    """Генерация и отправка файла экспорта."""
    if not call.from_user or not isinstance(call.message, Message):
        return

    # Ограничиваем команду только для администраторов
    if not await IsAdmin()(call.message):
        await call.answer(
            "Эта команда доступна только администраторам.", show_alert=True
        )
        return

    uid = str(call.from_user.id)
    chat_id = call.message.chat.id
    is_csv = call.data == "export_csv"

    await call.answer("⏳ Генерирую файл...")

    filepath: str | None = None
    try:
        if is_csv:
            filepath = await export_monitoring_csv(db, int(uid))
            caption = "📄 **Экспорт данных мониторинга (CSV)**"
        else:
            filepath = await export_monitoring_json(db, int(uid))
            caption = "📋 **Экспорт данных мониторинга (JSON)**"

        # Отправляем файл
        document = FSInputFile(filepath)
        await bot.send_document(
            chat_id,
            document,
            caption=caption,
            parse_mode="Markdown",
        )

    except ValueError as e:
        await bot.send_message(chat_id, f"❌ {e}")
        return
    except Exception as e:
        logger.error(f"Ошибка экспорта для uid={uid}: {e}")
        await bot.send_message(chat_id, "❌ Произошла ошибка при генерации файла.")
        return
    finally:
        # Удаляем временный файл
        try:
            if filepath:
                Path(filepath).unlink(missing_ok=True)  # noqa: ASYNC240
        except Exception as e:
            logger.debug(f"Не удалось удалить временный файл {filepath}: {e}")

    # Удаляем сообщение с выбором формата
    try:
        if isinstance(call.message, Message):
            await call.message.delete()
    except Exception:
        pass
