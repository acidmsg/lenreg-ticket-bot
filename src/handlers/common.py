import asyncio
import contextlib
import time as time_module

import aiofiles.os
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
from src.database.types import (
    BookingEntry,
    DoctorEntry,
    MonitoringEntry,
    PatientInfo,
    UserData,
)
from src.filters.admin import IsAdmin
from src.handlers.callback_parser import create_callback_filter
from src.handlers.callbacks import (
    CB_BACK_TO_MAIN,
    CB_EXPORT_CSV,
    CB_EXPORT_JSON,
    CB_MY_BOOKINGS,
    CB_NOOP,
    CB_STOP_ALL,
    BackToCities,
    BackToClinics,
    BookCancel,
    BookConfirm,
    BookConfirmLegacy,
    BookSlot,
    BookSlotLegacy,
    CitySelect,
    ClinicSelect,
    CloseSection,
    DeletePatientAsk,
    DeletePatientConfirm,
    DoctorSection,
    PatientSelect,
    SelectPatientForBooking,
    StartMonitoring,
    StopClinicMonitoring,
    StopPatientMonitoring,
    ToggleDoctor,
)
from src.i18n import _
from src.keyboards.inline import (
    build_slot_booking_keyboard,
    get_booking_confirmation_keyboard,
    get_booking_section_confirm_keyboard,
    get_city_selection,
    get_clinic_selection,
    get_confirm_deletion,
    get_doctor_section_keyboard,
    get_doctor_selection,
    get_main_menu_keyboard,
    get_patient_select_keyboard,
    get_patient_selection,
    get_slot_grid_keyboard,
)
from src.services.doctor_discovery import _get_clinic_type_from_db, fetch_specialties
from src.services.export import export_monitoring_csv, export_monitoring_json
from src.services.healthcheck import format_status_report
from src.utils.cache import delete_cache_keys_by_prefix, is_spam, swap_cache_key
from src.utils.helpers import (
    extract_msg_id,
    format_booking_confirmation,
    format_booking_result,
    format_error_message,
    format_notification_text,
    format_slots,
    shorten_fio,
    shorten_specialty,
)
from src.utils.telegram_utils import send_or_update_message

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
    if selected_city is None:
        city_label = _("all-clinics")
    else:
        city_label = _("clinic-prefix").format(city=selected_city)
    return selected_city, city_label


def _build_clinic_selection_kb(
    p_id: str,
    birthday: str,
    selected_city: str | None,
    monitoring: dict | None,
    clinic_names: dict,
    clinics_data: list,
    city_idx: str,
):
    """Хелпер: собирает клавиатуру выбора клиники через get_clinic_selection."""
    return get_clinic_selection(
        p_id,
        birthday,
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
        with contextlib.suppress(TelegramAPIError):
            await bot.delete_message(uid, msg_id)
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
                return await send_or_update_message(
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
        with contextlib.suppress(Exception):
            await msg.delete()

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


def build_monitoring_summary(
    patients: dict[str, PatientInfo],
    monitoring: dict[str, dict[str, MonitoringEntry]],
) -> str:
    """Формирует текстовую сводку активного мониторинга."""
    if not monitoring:
        return ""

    lines = [_("monitoring-summary-header")]

    for p_id, doctors in monitoring.items():
        raw = patients.get(p_id)
        if raw is None:
            continue
        p_info: PatientInfo = raw
        p_name = p_info.get("alias") or p_info.get("fio", _("patient-fallback-name"))
        lines.append(f"\n👤 {p_name}")

        if not doctors:
            continue

        sorted_docs = sorted(
            doctors.items(),
            key=lambda x: x[1].get("name", "") if isinstance(x[1], dict) else str(x[1]),
        )
        for i, (_d_id, d_info) in enumerate(sorted_docs):
            is_last = i == len(sorted_docs) - 1
            prefix = "  ┗" if is_last else "  ┣"
            if isinstance(d_info, dict):
                d_name = shorten_fio(d_info.get("name", _("doctor-fallback-name")))
                doctor_specialty = shorten_specialty(d_info.get("specialty", ""))
            else:
                d_name = str(d_info)
                doctor_specialty = ""
            spec_part = f" ({doctor_specialty})" if doctor_specialty else ""
            lines.append(f"{prefix} 🧑‍⚕️ {d_name}{spec_part}")

    return "\n".join(lines)


# ── Хендлеры ──────────────────────────────────────────────────


@router.message(Command("status"), IsAdmin())
async def cmd_status(message: Message, db: DatabaseManager) -> None:
    """Команда /status — отчёт о состоянии бота (только для администраторов)."""
    if not message.from_user:
        return

    report = await format_status_report(db)
    await message.answer(report, parse_mode="Markdown")


@router.message(Command("start"))
async def cmd_start(message: Message, db: DatabaseManager, bot: Bot) -> None:
    """Команда /start — приветствие с изображением-заголовком patient_select."""
    uid = str(message.from_user.id) if message.from_user else "unknown"
    user_data = await db.get_user_data(uid)

    # Удаляем все ключи пользователя из кэша city_idx
    for k in list(_user_clinic_city_idx):
        if k.startswith(f"{uid}_"):
            del _user_clinic_city_idx[k]

    # Удаляем все предыдущие сообщения бота из чата
    await _delete_cleanup_msg_entries(bot, uid, "", user_data["last_messages"])
    await db.update_user(uid, {"last_messages": {}})

    if not user_data.get("patients"):
        text = _("no-patients-welcome")
        reply_markup = get_patient_selection({}, {})
        parse_mode = None
    else:
        summary = build_monitoring_summary(
            user_data["patients"], user_data["monitoring"]
        )
        text = _("patient-list-header") + summary
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

    # Отправляем reply-клавиатуру с кнопкой Mini App (если включено)
    if settings.MINI_APP_ENABLED and settings.MINI_APP_URL:
        reply_kb = get_main_menu_keyboard(settings.MINI_APP_URL)
        if reply_kb:
            await message.answer(
                "👇 Или используйте веб-интерфейс:", reply_markup=reply_kb
            )


@router.callback_query(F.data == CB_BACK_TO_MAIN)
async def back_to_main(call: CallbackQuery, db: DatabaseManager) -> None:
    """Возврат в главное меню с изображением-заголовком patient_select."""
    if not call.from_user or not call.message or not isinstance(call.message, Message):
        return
    uid = str(call.from_user.id)

    # Удаляем все ключи пользователя из кэша city_idx
    for k in list(_user_clinic_city_idx):
        if k.startswith(f"{uid}_"):
            del _user_clinic_city_idx[k]

    user_data = await db.get_user_data(uid)

    if not user_data.get("patients"):
        text = _("no-patients-welcome")
        reply_markup = get_patient_selection({}, {})
    else:
        summary = build_monitoring_summary(
            user_data["patients"], user_data["monitoring"]
        )
        text = _("patient-list-header") + summary
        reply_markup = get_patient_selection(
            user_data["patients"], user_data["monitoring"]
        )

    await _send_nav_photo(call.bot, call.message, "patient", text, reply_markup, db=db)

    # Отправляем reply-клавиатуру с кнопкой Mini App (если включено)
    if settings.MINI_APP_ENABLED and settings.MINI_APP_URL:
        reply_kb = get_main_menu_keyboard(settings.MINI_APP_URL)
        if reply_kb:
            await call.message.answer(
                "👇 Или используйте веб-интерфейс:", reply_markup=reply_kb
            )


async def _show_city_selection(
    call: CallbackQuery,
    db: DatabaseManager,
    p_id: str,
    user_data: UserData,
) -> None:
    """Показывает список городов с изображением clinic_select.

    Используется из фабрики ``_create_selection_handler("city")``.
    """
    if not isinstance(call.message, Message):
        return
    cities = await db._db.get_distinct_cities()
    clinics_data = await db._db.get_active_clinics()

    await _send_nav_photo(
        call.bot,
        call.message,
        "clinic",
        _("select-city-prompt"),
        get_city_selection(
            p_id,
            cities=cities,
            monitoring=user_data.get("monitoring"),
            clinics_data=clinics_data,
        ),
        db=db,
    )


async def _show_clinic_selection(
    call: CallbackQuery,
    db: DatabaseManager,
    p_id: str,
    city_idx: str,
    user_data: UserData,
) -> None:
    """Показывает список клиник для выбранного города с изображением clinic_select.

    Используется из фабрики ``_create_selection_handler("clinic")``.
    """
    if not isinstance(call.message, Message):
        return
    raw_p = user_data["patients"].get(p_id)
    if raw_p is None:
        return
    p_info: PatientInfo = raw_p

    clinic_names = await db.get_all_clinic_names()
    clinics_data = await db._db.get_active_clinics()
    cities = await db._db.get_distinct_cities()

    selected_city, city_label = _decode_city_from_idx(str(city_idx), cities)

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


# ── Фабрика хендлеров выбора городов/клиник ─────────────────


def _create_selection_handler(view_type: str):
    """Фабрика хендлеров выбора города или клиники.

    Унифицирует 4 ранее отдельных хендлера (select_patient, back_to_cities,
    select_city, back_to_clinics), которые различались только типом
    отображаемого списка и атрибутом callback_data для city_idx.

    Args:
        view_type: ``"city"`` — список городов, ``"clinic"`` — список клиник.

    Returns:
        Асинхронный обработчик callback_query.
    """

    async def handler(call: CallbackQuery, db: DatabaseManager, callback_data) -> None:
        if not call.message or not call.from_user:
            return

        p_id: str = callback_data.p_id
        uid = str(call.from_user.id)
        user_data = await db.get_user_data(uid)

        if view_type == "city":
            await _show_city_selection(call, db, p_id, user_data)
        else:
            # CitySelect использует .idx, BackToClinics использует .city_idx
            city_idx: str
            city_idx_raw = getattr(callback_data, "city_idx", None)
            if city_idx_raw is not None:
                city_idx = city_idx_raw
            else:
                city_idx = getattr(callback_data, "idx", "all")
            await _show_clinic_selection(call, db, p_id, city_idx, user_data)

    return handler


# Регистрация хендлеров выбора городов/клиник через фабрику
router.callback_query.register(
    _create_selection_handler("city"),
    create_callback_filter(PatientSelect),
)
router.callback_query.register(
    _create_selection_handler("clinic"),
    create_callback_filter(CitySelect),
)
router.callback_query.register(
    _create_selection_handler("city"),
    create_callback_filter(BackToCities),
)
router.callback_query.register(
    _create_selection_handler("clinic"),
    create_callback_filter(BackToClinics),
)


@router.callback_query(create_callback_filter(ClinicSelect))
async def select_clinic(
    call: CallbackQuery,
    db: DatabaseManager,
    api: ZdravClient,
    callback_data: ClinicSelect,
) -> None:
    """Выбор клиники → список врачей с изображением doctor_*_select."""
    if not call.message or not call.from_user:
        return
    p_id = callback_data.p_id
    clinic_id = callback_data.clinic_id
    city_idx = callback_data.city_idx
    uid = str(call.from_user.id)
    user_data = await db.get_user_data(uid)
    raw_p = user_data["patients"].get(p_id)
    if raw_p is None:
        return
    p_info: PatientInfo = raw_p
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
        await call.answer(_("loading-doctors"), show_alert=False)
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
            _("select-doctors-prompt").format(clinic_line=clinic_line),
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


async def _guard_toggle_doctor(
    call: CallbackQuery,
    db: DatabaseManager,
    callback_data: ToggleDoctor,
) -> tuple[str, str, str, str, UserData, dict[str, DoctorEntry], DoctorEntry] | None:
    """Проверяет контекст и права для toggle_doctor.

    Проверяет: наличие message/from_user, spam-защиту, наличие данных
    пользователя, существование врача в списке клиники.

    Returns:
        Кортеж (uid, p_id, clinic_id, d_id, user_data, doctors_list, doc_info)
        или None если проверка не пройдена.
    """
    if not call.message or not call.from_user:
        return None

    if await is_spam(str(call.from_user.id)):
        return None

    p_id = callback_data.p_id
    clinic_id = callback_data.clinic_id
    d_id = callback_data.d_id
    uid = str(call.from_user.id)

    user_data = await db.get_user_data(uid)
    doctors_list = await db.get_doctors_for_clinic(clinic_id)
    raw_doc = doctors_list.get(d_id)
    if raw_doc is None:
        return None

    doc_info: DoctorEntry = raw_doc
    return uid, p_id, clinic_id, d_id, user_data, doctors_list, doc_info


async def _handle_untoggle_doctor(
    bot: Bot,
    call: CallbackQuery,
    db: DatabaseManager,
    uid: str,
    p_id: str,
    clinic_id: str,
    d_id: str,
    user_data: UserData,
    doctors_list: dict[str, DoctorEntry],
    p_info: PatientInfo,
    d_name_display: str,
) -> None:
    """Обрабатывает снятие врача с мониторинга: очистка кэша, удаление сообщений,
    перестроение клавиатуры.
    """
    user_data = await db.get_user_data(uid)
    monitored = user_data["monitoring"].get(p_id, {})

    # Удаляем связанное сообщение из чата
    msg_key = f"{p_id}_{d_id}"
    await _delete_cleanup_msg_entry(bot, uid, msg_key, user_data["last_messages"])
    await db.update_user(uid, {"last_messages": user_data["last_messages"]})

    cache_key = f"{uid}_{p_id}_{d_id}"
    await delete_cache_keys_by_prefix(cache_key)

    city_idx = _user_clinic_city_idx.get(f"{uid}_{p_id}_{clinic_id}", "all")
    clinic_type = await _get_clinic_type_from_db(db._db, clinic_id)
    nav_type = _CLINIC_NAV_TYPE_MAP.get(clinic_type, "doctor_adult")

    if isinstance(call.message, Message):
        await _send_nav_photo(
            bot,
            call.message,
            nav_type,
            _("monitoring-disabled-for").format(name=d_name_display),
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


async def _handle_toggle_on_doctor(
    api: ZdravClient,
    bot: Bot,
    call: CallbackQuery,
    db: DatabaseManager,
    uid: str,
    p_id: str,
    clinic_id: str,
    d_id: str,
    doc_info: DoctorEntry,
    doctors_list: dict[str, DoctorEntry],
    p_info: PatientInfo,
    d_name_display: str,
) -> None:
    """Обрабатывает включение мониторинга врача: проверка слотов, отправка результата,
    обновление клавиатуры.
    """
    message = call.message
    if message is None:
        return

    patient_label = p_info.get("alias") or p_info.get("fio", _("patient-fallback-name"))
    d_spec_display = shorten_specialty(doc_info.get("specialty", ""))
    spec_text = f"[{d_spec_display}]\n" if d_spec_display else ""

    # Отправляем «загрузочное» сообщение
    loading_msg = await message.answer(
        f"{spec_text}🧑‍⚕️ {d_name_display}\n👤 {patient_label}\n{_('checking-slots')}"
    )

    await call.answer()
    slots_result = await api.check_slots(d_id, p_id, clinic_id)

    # Сохраняем в кэш мониторинга
    if slots_result is not None:
        cache_key = f"{uid}_{p_id}_{d_id}"
        await swap_cache_key(
            cache_key, slots_result.formatted if slots_result.formatted else "NONE"
        )

    slots = slots_result.formatted if slots_result else None
    user_data = await db.get_user_data(uid)
    monitored = user_data["monitoring"].get(p_id, {})

    has_slots = bool(slots)
    status_text = _("slots-available-status") if has_slots else _("slots-empty-status")

    if has_slots and slots:
        slot_lines = format_slots(
            slots,
            detail_threshold=settings.SLOT_DETAIL_THRESHOLD,
            compact_threshold=settings.SLOT_COMPACT_THRESHOLD,
        )
        slots_display = "\n".join(slot_lines)
    else:
        slots_display = _("slots-will-notify")

    # Текст уведомления (без ссылки SIGNUP_URL — заменена на инлайн-кнопки)
    text = format_notification_text(
        patient_label, d_name_display, spec_text, status_text, slots_display
    )

    # Удаляем загрузочное сообщение
    with contextlib.suppress(Exception):
        await loading_msg.delete()

    # Клавиатура с кнопками «Записаться» для каждого слота
    reply_markup = None
    if has_slots and slots_result is not None:
        reply_markup = build_slot_booking_keyboard(p_id, clinic_id, d_id, slots_result)

    # Отправляем финальный результат
    notify_type = "available" if has_slots else "empty"
    photo_path = get_notify_image_path(notify_type)
    try:
        if photo_path is not None:
            photo = FSInputFile(photo_path)
            result_msg = await message.answer_photo(
                photo, caption=text, reply_markup=reply_markup, parse_mode="Markdown"
            )
        else:
            result_msg = await message.answer(text, reply_markup=reply_markup)
    except Exception:
        result_msg = await message.answer(text, reply_markup=reply_markup)

    await db.set_last_message_id(uid, p_id, d_id, result_msg.message_id)

    # Обновляем клавиатуру выбора врачей
    city_idx = _user_clinic_city_idx.get(f"{uid}_{p_id}_{clinic_id}", "all")
    clinic_type = await _get_clinic_type_from_db(db._db, clinic_id)
    nav_type = _CLINIC_NAV_TYPE_MAP.get(clinic_type, "doctor_adult")

    if isinstance(message, Message):
        await _send_nav_photo(
            bot,
            message,
            nav_type,
            _("monitoring-enabled-for").format(name=d_name_display),
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

    await call.answer(_("done-toast"))


@router.callback_query(create_callback_filter(ToggleDoctor))
async def toggle_doctor(
    call: CallbackQuery,
    db: DatabaseManager,
    api: ZdravClient,
    bot: Bot,
    callback_data: ToggleDoctor,
) -> None:
    """Переключает мониторинг врача: включает или выключает.

    Декомпозирован на три этапа:
    1. :func:`_guard_toggle_doctor` — проверка контекста и прав.
    2. :func:`_handle_untoggle_doctor` — снятие с мониторинга.
    3. :func:`_handle_toggle_on_doctor` — включение мониторинга.
    """
    # --- Этап 1: проверка прав и контекста ---
    guard_result = await _guard_toggle_doctor(call, db, callback_data)
    if guard_result is None:
        return

    uid, p_id, clinic_id, d_id, user_data, doctors_list, doc_info = guard_result
    d_name = doc_info.get("name", _("doctor-fallback-name"))
    doctor_specialty = doc_info.get("specialty", "")
    d_name_display = shorten_fio(d_name)

    already_monitored = d_id in user_data["monitoring"].get(p_id, {})

    # --- Этап 2: работа с БД (toggle) ---
    await db.toggle_monitoring(
        uid, p_id, d_id, d_name, clinic_id, doctor_specialty, date=""
    )

    raw_p = user_data.get("patients", {}).get(p_id)
    if raw_p is None:
        return
    p_info: PatientInfo = raw_p

    # --- Этап 3: ответ пользователю (снятие или включение) ---
    if already_monitored:
        await _handle_untoggle_doctor(
            bot,
            call,
            db,
            uid,
            p_id,
            clinic_id,
            d_id,
            user_data,
            doctors_list,
            p_info,
            d_name_display,
        )
    else:
        await _handle_toggle_on_doctor(
            api,
            bot,
            call,
            db,
            uid,
            p_id,
            clinic_id,
            d_id,
            doc_info,
            doctors_list,
            p_info,
            d_name_display,
        )


@router.callback_query(create_callback_filter(StopPatientMonitoring))
async def stop_patient_monitoring(
    call: CallbackQuery,
    db: DatabaseManager,
    bot: Bot,
    callback_data: StopPatientMonitoring,
) -> None:
    """
    Сброс мониторинга для конкретного пациента.
    После сброса остаётся на том же контексте (города или клиники).
    """
    if not call.from_user or not call.message:
        return
    p_id = callback_data.p_id
    origin = callback_data.origin  # city или clinic
    city_idx = callback_data.city_idx

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
        if origin == "clinic":
            # Остаёмся на списке клиник
            clinic_names = await db.get_all_clinic_names()
            clinics_data = await db._db.get_active_clinics()
            cities = await db._db.get_distinct_cities()
            raw_p = user_data.get("patients", {}).get(p_id)
            if raw_p is None:
                return
            p_info: PatientInfo = raw_p

            selected_city, __ = _decode_city_from_idx(str(city_idx), cities)

            await _send_nav_photo(
                bot,
                call.message,
                "clinic",
                _("monitoring-reset-patient"),
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
                _("monitoring-reset-patient"),
                get_city_selection(
                    p_id,
                    cities=cities,
                    monitoring=user_data.get("monitoring"),
                    clinics_data=clinics_data,
                ),
                db=db,
            )


@router.callback_query(create_callback_filter(StopClinicMonitoring))
async def stop_clinic_monitoring(
    call: CallbackQuery,
    db: DatabaseManager,
    bot: Bot,
    callback_data: StopClinicMonitoring,
) -> None:
    """Сброс мониторинга для конкретной клиники пациента."""
    if not call.from_user or not call.message:
        return
    p_id = callback_data.p_id
    clinic_id = callback_data.clinic_id
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
        raw_p = user_data.get("patients", {}).get(p_id)
        if raw_p is None:
            return
        p_info: PatientInfo = raw_p
        city_idx = _user_clinic_city_idx.get(f"{uid}_{p_id}_{clinic_id}", "all")

        # Определяем тип клиники для изображения врача
        clinic_type = await _get_clinic_type_from_db(db._db, clinic_id)
        nav_type = _CLINIC_NAV_TYPE_MAP.get(clinic_type, "doctor_adult")

        await _send_nav_photo(
            bot,
            call.message,
            nav_type,
            _("monitoring-reset-clinic"),
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


@router.callback_query(F.data == CB_STOP_ALL)
async def stop_all_monitoring(
    call: CallbackQuery, db: DatabaseManager, bot: Bot
) -> None:
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
            _("monitoring-stopped-all"),
            get_patient_selection(user_data["patients"], user_data["monitoring"]),
            db=db,
        )


@router.callback_query(F.data == CB_NOOP)
async def handle_noop(call: CallbackQuery) -> None:
    """Заглушка для кнопки-разделителя."""
    await call.answer()


@router.callback_query(create_callback_filter(DeletePatientAsk))
async def handle_delete_patient_ask(
    call: CallbackQuery, db: DatabaseManager, callback_data: DeletePatientAsk
) -> None:
    """Запрос подтверждения удаления пациента."""
    if not call.message or not call.from_user:
        return
    p_id = callback_data.p_id
    if isinstance(call.message, Message):
        with contextlib.suppress(Exception):
            await call.message.delete()
        await call.message.answer(
            _("confirm-delete-patient"),
            reply_markup=get_confirm_deletion(p_id),
        )


@router.callback_query(create_callback_filter(DeletePatientConfirm))
async def handle_delete_patient_confirm(
    call: CallbackQuery, db: DatabaseManager, callback_data: DeletePatientConfirm
) -> None:
    """Подтверждение удаления пациента."""
    if not call.message or not call.from_user:
        return
    p_id = callback_data.p_id
    uid = str(call.from_user.id)

    # Удаляем сообщения из чата, связанные с пациентом
    user_data = await db.get_user_data(uid)
    # Гарантируем, что бот доступен (type narrowing для mypy/pylance)
    assert call.bot is not None, "Bot must be available in callback"
    await _delete_cleanup_msg_entries(
        bot=call.bot,
        uid=uid,
        prefix_key=f"{p_id}_",
        last_messages=user_data.get("last_messages", {}),
    )
    await db.delete_patient(uid, p_id)
    if not user_data.get("patients"):
        text = _("no-patients-welcome")
        reply_markup = get_patient_selection({}, {})
    else:
        text = _("patient-list-after-delete")
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
async def cmd_export(message: Message, db: DatabaseManager) -> None:
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
        await message.answer(_("export-no-data"))
        return

    # Inline-клавиатура выбора формата
    builder = InlineKeyboardBuilder()
    builder.button(text=_("btn-csv"), callback_data=CB_EXPORT_CSV)
    builder.button(text=_("btn-json"), callback_data=CB_EXPORT_JSON)
    builder.adjust(2)

    await message.answer(
        _("export-format-prompt"),
        reply_markup=builder.as_markup(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.in_({CB_EXPORT_CSV, CB_EXPORT_JSON}))
async def process_export(call: CallbackQuery, db: DatabaseManager, bot: Bot) -> None:
    """Генерация и отправка файла экспорта."""
    if not call.from_user or not isinstance(call.message, Message):
        return

    # Ограничиваем команду только для администраторов
    if not await IsAdmin()(call.message):
        await call.answer(_("admin-only-export"), show_alert=True)
        return

    uid = str(call.from_user.id)
    chat_id = call.message.chat.id
    is_csv = call.data == CB_EXPORT_CSV

    await call.answer(_("export-generating"))

    filepath: str | None = None
    try:
        if is_csv:
            filepath = await export_monitoring_csv(db, int(uid))
            caption = _("export-csv-caption")
        else:
            filepath = await export_monitoring_json(db, int(uid))
            caption = _("export-json-caption")

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
        await bot.send_message(chat_id, _("export-error"))
        return
    finally:
        # Удаляем временный файл
        try:
            if filepath:
                await aiofiles.os.unlink(str(filepath))
        except Exception as e:
            logger.debug(f"Не удалось удалить временный файл {filepath}: {e}")

    # Удаляем сообщение с выбором формата
    try:
        if isinstance(call.message, Message):
            await call.message.delete()
    except Exception:
        logger.debug("Не удалось удалить сообщение с выбором формата экспорта")


# ── Хендлеры бронирования (Legacy — из уведомлений мониторинга) ──


@router.callback_query(create_callback_filter(BookSlotLegacy))
async def book_slot(
    call: CallbackQuery,
    db: DatabaseManager,
    bot: Bot,
    callback_data: BookSlotLegacy,
) -> None:
    """Обработка нажатия кнопки «Записаться» (старый flow — из уведомлений):
    проверка безопасности, редактирование сообщения в подтверждение.
    """
    if not call.from_user or not call.message:
        return

    p_id = callback_data.p_id
    clinic_id = callback_data.clinic_id
    d_id = callback_data.d_id
    appointment_id = callback_data.appointment_id
    slot_date = callback_data.slot_date
    slot_time = callback_data.slot_time
    uid = str(call.from_user.id)

    # --- Проверка безопасности ---
    if await is_spam(uid):
        await call.answer(_("rate-limit-toast"))
        return

    user_data = await db.get_user_data(uid)

    # Пациент должен принадлежать пользователю
    if p_id not in user_data.get("patients", {}):
        logger.warning("book_slot: пациент %s не принадлежит uid=%s", p_id, uid)
        await call.answer("⛔ Пациент не найден", show_alert=True)
        return

    # Врач должен быть в мониторинге пользователя
    p_monitoring = user_data.get("monitoring", {}).get(p_id, {})
    if d_id not in p_monitoring:
        logger.warning("book_slot: врач %s не в мониторинге uid=%s", d_id, uid)
        await call.answer("⛔ Врач не в мониторинге", show_alert=True)
        return

    # clinic_id должен совпадать с clinic_id в мониторинге врача
    d_info = p_monitoring[d_id]
    expected_clinic = d_info.get("clinic_id", "") if isinstance(d_info, dict) else ""
    if expected_clinic and expected_clinic != clinic_id:
        logger.warning(
            "book_slot: clinic_id не совпадает (callback=%s, monitoring=%s)",
            clinic_id,
            expected_clinic,
        )
        await call.answer("⛔ Неверная клиника", show_alert=True)
        return

    # --- Формирование подтверждения ---
    d_name = ""
    if isinstance(d_info, dict):
        d_name = shorten_fio(d_info.get("name", _("doctor-fallback-name")))

    clinic_name = await db.get_clinic_name(clinic_id) or ""

    confirm_text = format_booking_confirmation(
        d_name, slot_date, slot_time, clinic_name
    )
    confirm_kb = get_booking_confirmation_keyboard(
        p_id, clinic_id, d_id, appointment_id
    )

    # Редактируем сообщение со слотами → подтверждение
    try:
        msg = call.message
        if isinstance(msg, Message):
            try:
                await msg.edit_caption(
                    caption=confirm_text,
                    reply_markup=confirm_kb,
                    parse_mode="Markdown",
                )
            except Exception:
                await msg.edit_text(
                    confirm_text,
                    reply_markup=confirm_kb,
                    parse_mode="Markdown",
                )
    except Exception:
        logger.debug("Не удалось отредактировать сообщение в book_slot")

    await call.answer()


@router.callback_query(create_callback_filter(BookConfirmLegacy))
async def book_confirm(
    call: CallbackQuery,
    db: DatabaseManager,
    api: ZdravClient,
    bot: Bot,
    callback_data: BookConfirmLegacy,
) -> None:
    """Подтверждение записи (старый flow): book_appointment() и показ результата."""
    if not call.from_user or not call.message:
        return

    p_id = callback_data.p_id
    clinic_id = callback_data.clinic_id
    d_id = callback_data.d_id
    appointment_id = callback_data.appointment_id
    uid = str(call.from_user.id)

    # --- Повторная проверка безопасности ---
    if await is_spam(uid):
        await call.answer(_("rate-limit-toast"))
        return

    user_data = await db.get_user_data(uid)
    if p_id not in user_data.get("patients", {}):
        await call.answer("⛔ Пациент не найден", show_alert=True)
        return

    p_monitoring = user_data.get("monitoring", {}).get(p_id, {})
    if d_id not in p_monitoring:
        await call.answer("⛔ Врач не в мониторинге", show_alert=True)
        return

    # --- Имя врача и клиника для отображения ---
    d_info = p_monitoring[d_id]
    d_name = (
        shorten_fio(d_info.get("name", _("doctor-fallback-name")))
        if isinstance(d_info, dict)
        else d_id
    )
    clinic_name = await db.get_clinic_name(clinic_id) or ""

    # --- Показываем статус «выполняется» ---
    try:
        if isinstance(call.message, Message):
            await call.message.edit_caption(
                caption=_("booking-in-progress"),
                parse_mode="Markdown",
            )
        else:
            # aiogram-стабы не включают edit_text для InaccessibleMessage,
            # но метод существует в Bot API (editMessageText) и работает
            # для любых сообщений, доступных через callback_query.
            await call.message.edit_text(  # type: ignore[attr-defined]
                _("booking-in-progress"),
                parse_mode="Markdown",
            )
    except Exception:
        pass

    await call.answer()

    # --- Вызов API бронирования ---
    result = await api.book_appointment(
        clinic_id=clinic_id,
        patient_id=p_id,
        appointment_id=appointment_id,
    )

    # --- Формирование и показ результата ---
    result_text = format_booking_result(
        result,
        d_name=d_name,
        date="",  # Реальная дата неизвестна из ответа API
        time="",
        clinic_name=clinic_name,
    )

    try:
        if isinstance(call.message, Message):
            await call.message.edit_caption(
                caption=result_text,
                parse_mode="Markdown",
            )
        else:
            await call.message.edit_text(  # type: ignore[attr-defined]
                result_text,
                parse_mode="Markdown",
            )
    except Exception:
        logger.debug("Не удалось отредактировать сообщение в book_confirm")


@router.callback_query(create_callback_filter(BookCancel))
async def book_cancel(
    call: CallbackQuery,
    db: DatabaseManager,
    api: ZdravClient,
    bot: Bot,
    callback_data: BookCancel,
) -> None:
    """Отмена записи: re-query check_slots() и восстановление списка слотов."""
    if not call.from_user or not call.message:
        return

    p_id = callback_data.p_id
    clinic_id = callback_data.clinic_id
    d_id = callback_data.d_id
    uid = str(call.from_user.id)

    # --- Re-query слотов ---
    slots_result = await api.check_slots(d_id, p_id, clinic_id)

    if slots_result is None:
        await call.answer("⚠️ Не удалось проверить слоты", show_alert=True)
        return

    # --- Формирование обновлённого списка ---
    user_data = await db.get_user_data(uid)
    p_info = user_data.get("patients", {}).get(p_id)
    patient_label = (p_info.get("alias") or p_info.get("fio", "")) if p_info else ""
    d_name_display = ""

    p_monitoring = user_data.get("monitoring", {}).get(p_id, {})
    # TypedDict не является подтипом dict по мнению mypy, но в runtime это dict.
    d_info: dict = p_monitoring.get(d_id, {})  # type: ignore[assignment]
    if isinstance(d_info, dict):
        d_name_display = shorten_fio(d_info.get("name", _("doctor-fallback-name")))

    slots = slots_result.formatted
    has_slots = bool(slots)
    status_text = _("slots-available-status") if has_slots else _("slots-empty-status")

    if has_slots and slots:
        slot_lines = format_slots(
            slots,
            detail_threshold=settings.SLOT_DETAIL_THRESHOLD,
            compact_threshold=settings.SLOT_COMPACT_THRESHOLD,
        )
        slots_display = "\n".join(slot_lines)
    else:
        slots_display = _("slots-will-notify")

    # Спек-текст
    d_spec = d_info.get("specialty", "") if isinstance(d_info, dict) else ""
    d_spec_display = shorten_specialty(d_spec)
    spec_text = f"[{d_spec_display}]\n" if d_spec_display else ""

    text = format_notification_text(
        patient_label, d_name_display, spec_text, status_text, slots_display
    )

    # Клавиатура с кнопками «Записаться»
    reply_markup = None
    if has_slots:
        reply_markup = build_slot_booking_keyboard(p_id, clinic_id, d_id, slots_result)

    # Редактируем сообщение обратно в список слотов
    try:
        if isinstance(call.message, Message):
            await call.message.edit_caption(
                caption=text,
                reply_markup=reply_markup,
                parse_mode="Markdown",
            )
        else:
            await call.message.edit_text(  # type: ignore[attr-defined]
                text,
                reply_markup=reply_markup,
                parse_mode="Markdown",
            )
    except Exception:
        logger.debug("Не удалось отредактировать сообщение в book_cancel")

    await call.answer()


# ═══════════════════════════════════════════════════════════════
# ── Новые хендлеры PopupSection (Фаза 1 рефакторинга UX) ──────
# ═══════════════════════════════════════════════════════════════


@router.callback_query(create_callback_filter(DoctorSection))
async def doctor_section(
    call: CallbackQuery,
    db: DatabaseManager,
    api: ZdravClient,
    callback_data: DoctorSection,
) -> None:
    """Открытие всплывающей секции врача (PopupSection).

    Сценарии:
    - A: Есть слоты → сетка слотов + кнопка [В отслеживание]
    - C: Нет слотов / API ошибка → заглушка + кнопка [В отслеживание]
    """
    if not call.from_user or not call.message:
        return
    uid = str(call.from_user.id)
    p_id = callback_data.p_id
    clinic_id = callback_data.clinic_id
    d_id = callback_data.d_id

    user_data = await db.get_user_data(uid)

    # ── Выбор пациента (T-10) ──
    # Проверяем, есть ли для этого врача несколько пациентов в мониторинге
    monitoring_patients = user_data.get("monitoring", {})
    candidate_patients: list[dict] = []

    # Если врач уже в мониторинге для нескольких пациентов — показываем выбор
    for mp_id, doctors in monitoring_patients.items():
        for md_id in doctors:
            if md_id == d_id:
                mp_info = user_data["patients"].get(mp_id)
                if mp_info:
                    candidate_patients.append(
                        {
                            "p_id": mp_id,
                            "name": mp_info.get("alias") or mp_info.get("fio", mp_id),
                        }
                    )

    # Если более одного кандидата — показываем выбор пациента (T-10)
    if len(candidate_patients) > 1:
        await call.answer()
        try:
            if isinstance(call.message, Message):
                await call.message.edit_text(
                    _("select-patient-for-booking").format(doctor=""),
                    reply_markup=get_patient_select_keyboard(
                        candidate_patients, clinic_id, d_id
                    ),
                )
        except Exception:
            logger.debug("Не удалось показать выбор пациента в doctor_section")
        return

    # Определяем p_id для использования
    if candidate_patients:
        # Один пациент — используем его
        p_id = candidate_patients[0]["p_id"]
    # Иначе используем p_id из callback (текущий пациент из контекста клиники)

    # ── Получение данных врача ──
    doctors_list = await db.get_doctors_for_clinic(clinic_id)
    doc_raw = doctors_list.get(d_id)
    if doc_raw is None:
        await call.answer("Врач не найден", show_alert=True)
        return

    doc_info: DoctorEntry = doc_raw
    doctor_name = shorten_fio(doc_info.get("name", _("doctor-fallback-name")))
    doctor_specialty = shorten_specialty(doc_info.get("specialty", ""))
    clinic_name = await db.get_clinic_name(clinic_id) or ""

    # Получаем имя пациента
    raw_p = user_data["patients"].get(p_id)
    patient_name = ""
    if raw_p:
        p_info: PatientInfo = raw_p
        patient_name = p_info.get("alias") or p_info.get(
            "fio", _("patient-fallback-name")
        )

    # ── Проверка слотов ──
    await call.answer()
    slots_result = None
    try:
        slots_result = await api.check_slots(d_id, p_id, clinic_id)
    except Exception as e:
        logger.error(f"Ошибка check_slots в doctor_section: {e}")

    # ── Формирование текста секции ──
    header_lines = [
        f"👨‍⚕️ {doctor_name}",
        f"📋 {doctor_specialty}" if doctor_specialty else "",
        f"🏥 {clinic_name}",
        f"👤 Пациент: {patient_name}",
    ]
    header = "\n".join(line for line in header_lines if line)

    if slots_result and slots_result.has_slots:
        # Сценарий A: слоты есть
        text = header + "\n\n✅ Есть доступные талоны:"

        slot_kb = get_slot_grid_keyboard(slots_result, p_id, clinic_id, d_id)
        # Добавляем кнопки [В отслеживание] + [Закрыть] под сеткой слотов
        builder = InlineKeyboardBuilder()
        # Копируем кнопки слотов
        if hasattr(slot_kb, "inline_keyboard"):
            for row in slot_kb.inline_keyboard:
                for btn in row:
                    builder.button(text=btn.text, callback_data=btn.callback_data)
        builder.adjust(1)
        # Добавляем row с [Отслеживание] и [Закрыть]
        builder.button(
            text=_("btn-start-monitoring"),
            callback_data=StartMonitoring(
                p_id=p_id, clinic_id=clinic_id, d_id=d_id
            ).pack(),
        )
        builder.button(
            text=_("btn-close-section"),
            callback_data=CloseSection(p_id=p_id).pack(),
        )
        reply_markup = builder.as_markup()
    else:
        # Сценарий C: нет талонов / API ошибка
        text = header + f"\n\n📭 {_('no-slots-placeholder')}"
        reply_markup = get_doctor_section_keyboard(p_id, clinic_id, d_id)

    # ── Отправка/редактирование сообщения ──
    try:
        msg = call.message
        if isinstance(msg, Message):
            await msg.edit_text(
                text,
                reply_markup=reply_markup,
                parse_mode="Markdown",
            )
    except Exception:
        logger.debug("Не удалось отредактировать сообщение в doctor_section")


@router.callback_query(create_callback_filter(SelectPatientForBooking))
async def select_patient_for_booking(
    call: CallbackQuery,
    db: DatabaseManager,
    api: ZdravClient,
    callback_data: SelectPatientForBooking,
) -> None:
    """Выбор пациента для записи (T-10): переоткрывает DoctorSection с пациентом."""
    if not call.from_user or not call.message:
        return

    p_id = callback_data.p_id
    clinic_id = callback_data.clinic_id
    d_id = callback_data.d_id

    # Переоткрываем DoctorSection с выбранным пациентом
    # Создаём фейковый callback_data для повторного вызова doctor_section
    fake_cb = DoctorSection(p_id=p_id, clinic_id=clinic_id, d_id=d_id)
    await doctor_section(call, db, api, fake_cb)


@router.callback_query(create_callback_filter(BookSlot))
async def book_slot_section(
    call: CallbackQuery,
    db: DatabaseManager,
    callback_data: BookSlot,
) -> None:
    """Выбор слота для записи (новый flow — из PopupSection):
    показывает сообщение подтверждения.
    """
    if not call.from_user or not call.message:
        return

    p_id = callback_data.p_id
    clinic_id = callback_data.clinic_id
    d_id = callback_data.d_id
    appointment_id = callback_data.appointment_id
    date = callback_data.date
    time = callback_data.time
    uid = str(call.from_user.id)

    # --- Проверка безопасности ---
    if await is_spam(uid):
        await call.answer(_("rate-limit-toast"))
        return

    user_data = await db.get_user_data(uid)
    if p_id not in user_data.get("patients", {}):
        await call.answer("⛔ Пациент не найден", show_alert=True)
        return

    # --- Получение данных врача ---
    doctors_list = await db.get_doctors_for_clinic(clinic_id)
    doc_raw = doctors_list.get(d_id)
    doctor_name = d_id
    if doc_raw:
        doc_info: DoctorEntry = doc_raw
        doctor_name = shorten_fio(doc_info.get("name", _("doctor-fallback-name")))

    # --- Формирование подтверждения ---
    confirm_text = (
        f"📋 {_('booking-confirm-title')}\n\n"
        f"{_('booking-confirm-text').format(doctor=doctor_name, date=date, time=time)}"
    )
    confirm_kb = get_booking_section_confirm_keyboard(
        p_id, clinic_id, d_id, appointment_id, date, time
    )

    # Редактируем сообщение → подтверждение
    try:
        msg = call.message
        if isinstance(msg, Message):
            with contextlib.suppress(Exception):
                await msg.edit_text(
                    confirm_text,
                    reply_markup=confirm_kb,
                    parse_mode="Markdown",
                )
    except Exception:
        logger.debug("Не удалось отредактировать сообщение в book_slot_section")

    await call.answer()


@router.callback_query(create_callback_filter(BookConfirm))
async def book_confirm_section(
    call: CallbackQuery,
    db: DatabaseManager,
    api: ZdravClient,
    bot: Bot,
    callback_data: BookConfirm,
) -> None:
    """Подтверждение записи (новый flow — из PopupSection):
    вызов book_appointment(), три исхода: успех / слот занят / ошибка API.
    """
    if not call.from_user or not call.message:
        return

    p_id = callback_data.p_id
    clinic_id = callback_data.clinic_id
    d_id = callback_data.d_id
    appointment_id = callback_data.appointment_id
    date = callback_data.date
    time = callback_data.time
    uid = str(call.from_user.id)

    # --- Повторная проверка безопасности ---
    if await is_spam(uid):
        await call.answer(_("rate-limit-toast"))
        return

    user_data = await db.get_user_data(uid)
    if p_id not in user_data.get("patients", {}):
        await call.answer("⛔ Пациент не найден", show_alert=True)
        return

    # --- Получение данных врача и пациента ---
    doctors_list = await db.get_doctors_for_clinic(clinic_id)
    doc_raw = doctors_list.get(d_id)
    doctor_name = d_id
    doctor_specialty = ""
    if doc_raw:
        doc_info: DoctorEntry = doc_raw
        doctor_name = doc_info.get("name", _("doctor-fallback-name"))
        doctor_specialty = doc_info.get("specialty", "")

    clinic_name = await db.get_clinic_name(clinic_id) or ""

    raw_p = user_data["patients"].get(p_id)
    patient_name = ""
    if raw_p:
        p_info: PatientInfo = raw_p
        patient_name = p_info.get("alias") or p_info.get("fio", "")

    # --- Показываем статус «выполняется» ---
    try:
        if isinstance(call.message, Message):
            await call.message.edit_text(
                _("booking-in-progress"),
                parse_mode="Markdown",
            )
        else:
            await call.message.edit_text(  # type: ignore[attr-defined]
                _("booking-in-progress"),
                parse_mode="Markdown",
            )
    except Exception:
        pass

    await call.answer()

    # --- Вызов API бронирования ---
    result = await api.book_appointment(
        clinic_id=clinic_id,
        patient_id=p_id,
        appointment_id=appointment_id,
    )

    # --- Три исхода ---
    if result.success:
        # Успех
        d_name_display = shorten_fio(doctor_name)
        success_text = _("booking-success").format(
            doctor=d_name_display,
            date=date,
            time=time,
            clinic=clinic_name,
        )

        # Сохраняем запись в БД (T-17)
        try:
            booking = BookingEntry(
                booking_id=f"{p_id}_{d_id}_{appointment_id}",
                uid=uid,
                p_id=p_id,
                d_id=d_id,
                doctor_name=doctor_name,
                patient_name=patient_name,
                specialty=doctor_specialty,
                clinic_id=clinic_id,
                clinic_name=clinic_name,
                slot_date=date,
                slot_time=time,
                appointment_id=appointment_id,
                created_at=time_module.time(),
                is_archived=0,
            )
            await db.save_booking(booking)
        except Exception as e:
            logger.error(f"Ошибка сохранения booking: {e}")

        # Кнопка «На главную»
        builder = InlineKeyboardBuilder()
        builder.button(
            text=_("btn-back-to-main"),
            callback_data=CB_BACK_TO_MAIN,
        )
        reply_markup = builder.as_markup()

        try:
            if isinstance(call.message, Message):
                await call.message.edit_text(
                    success_text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown",
                )
        except Exception:
            logger.debug("Не удалось показать успех записи")

    elif result.error and result.error.IdError == 39:
        # Слот занят — кнопка «Назад к слотам»
        error_text = format_error_message("slot_taken")

        builder = InlineKeyboardBuilder()
        builder.button(
            text=_("btn-booking-back"),
            callback_data=DoctorSection(
                p_id=p_id, clinic_id=clinic_id, d_id=d_id
            ).pack(),
        )
        reply_markup = builder.as_markup()

        try:
            if isinstance(call.message, Message):
                await call.message.edit_text(
                    error_text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown",
                )
        except Exception:
            logger.debug("Не удалось показать ошибку «слот занят»")

    else:
        # Классификация ошибки по detail из result.error (T-14)
        error_code = "unknown"
        error_detail = ""
        if result.error:
            error_detail = result.error.ErrorDescription or result.error.detail or ""
            detail_lower = error_detail.lower()

            if "таймаут" in detail_lower or "timeout" in detail_lower:
                error_code = "api_timeout"
            elif "сетевая" in detail_lower or "network" in detail_lower:
                error_code = "api_unavailable"
            elif "403" in detail_lower or "заблокировало" in detail_lower:
                error_code = "forbidden"

        error_text = format_error_message(error_code, error_detail)

        # Для slot_taken — «Назад к слотам», для остальных — «На главную»
        builder = InlineKeyboardBuilder()
        builder.button(
            text=_("btn-back-to-main"),
            callback_data=CB_BACK_TO_MAIN,
        )
        reply_markup = builder.as_markup()

        try:
            if isinstance(call.message, Message):
                await call.message.edit_text(
                    error_text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown",
                )
        except Exception:
            logger.debug("Не удалось показать ошибку записи")


@router.callback_query(create_callback_filter(StartMonitoring))
async def start_monitoring(
    call: CallbackQuery,
    db: DatabaseManager,
    callback_data: StartMonitoring,
) -> None:
    """Добавление врача в отслеживание (T-04) — без фильтра."""
    if not call.from_user or not call.message:
        return

    p_id = callback_data.p_id
    clinic_id = callback_data.clinic_id
    d_id = callback_data.d_id
    uid = str(call.from_user.id)

    # --- Получение данных врача ---
    doctors_list = await db.get_doctors_for_clinic(clinic_id)
    doc_raw = doctors_list.get(d_id)
    d_name = d_id
    doctor_specialty = ""
    if doc_raw:
        doc_info: DoctorEntry = doc_raw
        d_name = doc_info.get("name", _("doctor-fallback-name"))
        doctor_specialty = doc_info.get("specialty", "")

    # --- Toggle мониторинга ---
    await db.toggle_monitoring(
        uid, p_id, d_id, d_name, clinic_id, doctor_specialty, date=""
    )

    # --- Показ результата ---
    await call.answer()
    try:
        if isinstance(call.message, Message):
            await call.message.edit_text(
                _("monitoring-added"),
                reply_markup=InlineKeyboardBuilder()
                .button(
                    text=_("btn-back-to-main"),
                    callback_data=CB_BACK_TO_MAIN,
                )
                .as_markup(),
                parse_mode="Markdown",
            )
    except Exception:
        logger.debug("Не удалось показать результат start_monitoring")


@router.callback_query(create_callback_filter(CloseSection))
async def close_section(
    call: CallbackQuery,
    db: DatabaseManager,
    callback_data: CloseSection,
) -> None:
    """Закрытие секции врача (T-06) → возврат на главную (back_to_main)."""
    if not call.from_user:
        return

    # Просто делегируем в back_to_main
    await back_to_main(call, db)


# ── Мои записи (Фаза 3 рефакторинга UX) ──────────────────


async def _handle_my_bookings(
    message: Message,
    db: DatabaseManager,
) -> None:
    """Показывает список активных записей пользователя (T-11)."""
    if not message.from_user:
        return
    uid = str(message.from_user.id)

    # Автоархивация прошедших записей
    try:
        await db.archive_past_bookings(uid)
    except Exception:
        logger.exception("Ошибка автоархивации в _handle_my_bookings для uid={}", uid)

    bookings = await db.get_user_bookings(uid)

    if not bookings:
        text = "📋 Мои записи к врачам\n\nУ вас пока нет записей к врачам."
    else:
        lines = ["📋 Мои записи к врачам", ""]
        for i, b in enumerate(bookings, start=1):
            doctor = b.get("doctor_name", "—")
            specialty = b.get("specialty", "")
            clinic = b.get("clinic_name", "—")
            date = b.get("slot_date", "")
            time = b.get("slot_time", "")
            patient = b.get("patient_name", "")

            spec_str = f" — {specialty}" if specialty else ""
            lines.append(f"{i}. 👨‍⚕️ {doctor}{spec_str}")
            lines.append(f"   🏥 {clinic}")
            lines.append(f"   📅 {date} в {time}")
            if patient:
                lines.append(f"   👤 Пациент: {patient}")
            lines.append("")
        text = "\n".join(lines)

    builder = InlineKeyboardBuilder()
    builder.button(text="На главную", callback_data=CB_BACK_TO_MAIN)
    reply_markup = builder.as_markup()

    await message.answer(text, reply_markup=reply_markup, parse_mode="Markdown")


@router.message(F.text == "📋 Мои записи")
async def my_bookings_message(
    message: Message,
    db: DatabaseManager,
) -> None:
    """Обработчик кнопки «📋 Мои записи» из reply-клавиатуры."""
    await _handle_my_bookings(message, db)


@router.callback_query(F.data == CB_MY_BOOKINGS)
async def my_bookings_callback(
    call: CallbackQuery,
    db: DatabaseManager,
) -> None:
    """Обработчик inline-кнопки «📋 Мои записи» (альтернативный вход)."""
    if not isinstance(call.message, Message):
        return
    await call.answer()
    await _handle_my_bookings(call.message, db)
