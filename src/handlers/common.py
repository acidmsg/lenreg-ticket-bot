import asyncio
import contextlib
import time as time_module

import aiofiles.os
from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger

from src.api.models import CheckSlotsResult
from src.api.zdrav_client import ZdravClient
from src.assets.utils import get_nav_image_path
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
from src.handlers import filter_setup
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
    UnsubscribeMonitoring,
)
from src.i18n import _
from src.keyboards.inline import (
    get_booking_section_confirm_keyboard,
    get_city_selection,
    get_clinic_selection,
    get_confirm_deletion,
    get_doctor_section_keyboard,
    get_doctor_selection,
    get_main_menu_keyboard,
    get_monitoring_action,
    get_patient_select_keyboard,
    get_patient_selection,
    get_slot_grid_keyboard,
)
from src.services.doctor_discovery import _get_clinic_type_from_db, fetch_specialties
from src.services.export import (
    _build_ticket_payload,
    export_booking_barcode_png,
    export_monitoring_csv,
    export_monitoring_json,
)
from src.services.healthcheck import format_status_report
from src.utils.cache import delete_cache_keys_by_prefix, is_spam
from src.utils.helpers import (
    SlotDateTime,
    extract_msg_id,
    format_booking_card,
    format_error_message,
    resolve_slot_datetime,
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
async def cmd_start(
    message: Message,
    db: DatabaseManager,
    bot: Bot,
    state: FSMContext | None = None,
) -> None:
    """Команда /start — приветствие с изображением-заголовком patient_select.

    Прерывает любой незавершённый FSM-сценарий, в том числе мастер фильтра (§9.3.6).
    """
    if state is not None:
        await state.clear()

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


@router.callback_query(create_callback_filter(UnsubscribeMonitoring))
async def unsubscribe_monitoring(
    call: CallbackQuery,
    db: DatabaseManager,
    callback_data: UnsubscribeMonitoring,
) -> None:
    """Отписка от мониторинга врача прямо из уведомления о номерках.

    Снимает наблюдение только за парой (пациент + врач), очищает кэш слотов
    и подтверждает действие, убирая кнопки из самого уведомления.
    """
    if not call.from_user:
        return
    uid = str(call.from_user.id)
    p_id = callback_data.p_id
    d_id = callback_data.d_id

    user_data = await db.get_user_data(uid)
    d_info = user_data.get("monitoring", {}).get(p_id, {}).get(d_id)

    if not isinstance(d_info, dict):
        # Мониторинг уже снят (повторный тап или снятие из Mini App).
        await call.answer(_("unsubscribe-already"), show_alert=False)
        await _replace_notification_markup(call, _("unsubscribe-already"))
        return

    await db.toggle_monitoring(
        uid=uid,
        p_id=p_id,
        d_id=d_id,
        d_name=d_info.get("name", ""),
        clinic_id=d_info.get("clinic_id", ""),
        doctor_specialty=d_info.get("specialty", ""),
    )
    await delete_cache_keys_by_prefix(f"{uid}_{p_id}_{d_id}")
    logger.info(
        "Unsubscribe from notification: uid={}, p_id={}, d_id={}",
        uid,
        p_id,
        d_id,
    )

    await call.answer(_("unsubscribe-confirmed"), show_alert=False)
    await _replace_notification_markup(call, _("unsubscribe-confirmed"))


async def _replace_notification_markup(call: CallbackQuery, confirmation: str) -> None:
    """Переписывает уведомление после отписки: текст + подтверждение, без кнопок.

    Уведомление приходит фото-сообщением (с картинкой) либо текстом —
    правится соответствующим методом. Ошибки правки не критичны: подтверждение
    уже показано всплывающей подсказкой ``call.answer``.
    """
    message = call.message
    if not isinstance(message, Message):
        return
    base = message.caption or message.text or ""
    new_text = f"{base}\n\n{confirmation}" if base else confirmation
    with contextlib.suppress(TelegramBadRequest, TelegramAPIError):
        if message.photo:
            await message.edit_caption(
                caption=new_text, parse_mode="Markdown", reply_markup=None
            )
        else:
            await message.edit_text(new_text, parse_mode="Markdown", reply_markup=None)


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

    # Состояние отслеживания пары пациент + врач переключает кнопку (§9.3.1)
    is_monitored = d_id in monitoring_patients.get(p_id, {})

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
        # Добавляем row с кнопкой мониторинга/фильтра и [Закрыть]
        action_text, action_callback = get_monitoring_action(
            p_id, clinic_id, d_id, is_monitored
        )
        builder.button(text=action_text, callback_data=action_callback)
        builder.button(
            text=_("btn-close-section"),
            callback_data=CloseSection(p_id=p_id).pack(),
        )
        reply_markup = builder.as_markup()
    else:
        # Сценарий C: нет талонов / API ошибка
        text = header + f"\n\n📭 {_('no-slots-placeholder')}"
        reply_markup = get_doctor_section_keyboard(p_id, clinic_id, d_id, is_monitored)

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


async def _resolve_fresh_slot(
    api: ZdravClient,
    d_id: str,
    p_id: str,
    clinic_id: str,
    appointment_id: str,
) -> tuple[CheckSlotsResult | None, SlotDateTime | None]:
    """Резолвит выбранный талон в свежем ответе check_slots() (§11.1.1, §11.1.5).

    Дата и время не передаются через ``callback_data`` (§11.1.2): производные
    значения берутся из того же ответа, по которому построена сетка слотов.
    ``check_slots()`` самостоятельно обрабатывает сетевые сбои и ошибки API,
    возвращая ``None``, поэтому повторная обработка ошибок не дублируется.

    Args:
        api: Клиент zdrav API.
        d_id: ID врача.
        p_id: ID пациента.
        clinic_id: ID клиники.
        appointment_id: Идентификатор слота из callback.

    Returns:
        Кортеж (свежий результат ``check_slots()`` либо ``None`` при сбое API,
        нормализованные дата и время либо ``None``, если слот исчез).
    """
    slots_result = await api.check_slots(d_id, p_id, clinic_id)
    slot_dt = (
        resolve_slot_datetime(slots_result.slots, appointment_id)
        if slots_result
        else None
    )
    return slots_result, slot_dt


async def _show_slot_unavailable(
    call: CallbackQuery,
    slots_result: CheckSlotsResult | None,
    p_id: str,
    clinic_id: str,
    d_id: str,
    is_monitored: bool,
) -> None:
    """Показывает «талон больше недоступен» с актуальной клавиатурой (§11.1.4).

    Если в свежем ответе остались слоты — выводится их сетка; при пустом
    ответе или сбое API — возврат в секцию врача. Карточка подтверждения
    не показывается, запись не выполняется.

    Args:
        call: Callback кнопки слота или подтверждения.
        slots_result: Свежий результат ``check_slots()`` либо ``None``.
        p_id: ID пациента.
        clinic_id: ID клиники.
        d_id: ID врача.
        is_monitored: Врач отслеживается (для кнопки секции врача).
    """
    if slots_result and slots_result.has_slots:
        reply_markup = get_slot_grid_keyboard(slots_result, p_id, clinic_id, d_id)
    else:
        reply_markup = get_doctor_section_keyboard(p_id, clinic_id, d_id, is_monitored)

    msg = call.message
    if isinstance(msg, Message):
        try:
            await msg.edit_text(
                _("booking-slot-unavailable"),
                reply_markup=reply_markup,
                parse_mode="Markdown",
            )
        except TelegramBadRequest as e:
            logger.debug(f"Не удалось показать «талон недоступен»: {e}")

    await call.answer()


@router.callback_query(create_callback_filter(BookSlot))
async def book_slot_section(
    call: CallbackQuery,
    db: DatabaseManager,
    api: ZdravClient,
    callback_data: BookSlot,
) -> None:
    """Выбор слота для записи (новый flow — из PopupSection):
    показывает карточку подтверждения.

    Дата и время не приходят в callback (§11.1.2): слот резолвится по
    ``appointment_id`` в свежем ответе ``check_slots()`` (§11.1.1).
    Если слот исчез — карточка не показывается, запись не выполняется (§11.1.4).
    """
    if not call.from_user or not call.message:
        return

    p_id = callback_data.p_id
    clinic_id = callback_data.clinic_id
    d_id = callback_data.d_id
    appointment_id = callback_data.appointment_id
    uid = str(call.from_user.id)

    # --- Проверка безопасности ---
    if await is_spam(uid):
        await call.answer(_("rate-limit-toast"))
        return

    user_data = await db.get_user_data(uid)
    raw_patient = user_data.get("patients", {}).get(p_id)
    if raw_patient is None:
        await call.answer("⛔ Пациент не найден", show_alert=True)
        return

    # --- Резолв слота в свежем ответе (§11.1.1, §11.1.4) ---
    slots_result, slot_dt = await _resolve_fresh_slot(
        api, d_id, p_id, clinic_id, appointment_id
    )
    if slot_dt is None:
        is_monitored = d_id in user_data.get("monitoring", {}).get(p_id, {})
        await _show_slot_unavailable(
            call, slots_result, p_id, clinic_id, d_id, is_monitored
        )
        return

    # --- Получение данных врача и специальности (§11.1.1) ---
    doctors_list = await db.get_doctors_for_clinic(clinic_id)
    doc_raw = doctors_list.get(d_id)
    doctor_name = d_id
    doctor_specialty = ""
    if doc_raw:
        doc_info: DoctorEntry = doc_raw
        doctor_name = shorten_fio(doc_info.get("name", _("doctor-fallback-name")))
        doctor_specialty = shorten_specialty(doc_info.get("specialty", ""))

    # --- Пациент и клиника для карточки (§11.1.1) ---
    p_info: PatientInfo = raw_patient
    patient_name = p_info.get("alias") or p_info.get("fio", "")
    clinic_name = await db.get_clinic_name(clinic_id) or ""

    # --- Формирование карточки подтверждения (§11.2) ---
    confirm_text = format_booking_card(
        doctor_name=doctor_name,
        specialty=doctor_specialty,
        date=slot_dt.date,
        time=slot_dt.time,
        patient_name=patient_name,
        clinic_name=clinic_name,
    )
    confirm_kb = get_booking_section_confirm_keyboard(
        p_id, clinic_id, d_id, appointment_id
    )

    # Редактируем сообщение → подтверждение
    msg = call.message
    if isinstance(msg, Message):
        try:
            await msg.edit_text(
                confirm_text,
                reply_markup=confirm_kb,
                parse_mode="Markdown",
            )
        except TelegramBadRequest as e:
            logger.debug(f"Не удалось показать карточку записи: {e}")

    await call.answer()


_CAPTION_MAX_LENGTH = 1024


async def _show_barcode_fallback(
    message: Message,
    fallback_text: str,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    """Best-effort показывает текстовый талон вместо фото со штрих-кодом."""
    with contextlib.suppress(Exception):
        await message.edit_text(
            fallback_text,
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )


async def _deliver_booking_ticket(
    message: Message,
    booking: BookingEntry,
    caption: str,
    fallback_text: str,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    """Отправляет фото талона со штрих-кодом; при любом сбое — текстовый фолбэк.

    Сценарий записи не должен падать из-за талона: ошибка генерации,
    превышение лимита подписи или сбой Telegram API приводят к текстовому
    сообщению с номером талона.
    """
    try:
        png = await asyncio.to_thread(export_booking_barcode_png, booking)
    except ImportError:
        logger.warning("python-barcode недоступен — показываем текстовый талон")
        await _show_barcode_fallback(message, fallback_text, reply_markup)
        return
    except Exception as e:
        # Граница отказоустойчивости: сбой генерации → текстовый талон
        logger.warning(f"Ошибка генерации штрих-кода талона: {e}")
        await _show_barcode_fallback(message, fallback_text, reply_markup)
        return

    if len(caption) > _CAPTION_MAX_LENGTH:
        logger.warning("Подпись талона превышает лимит Telegram (1024) — фолбэк")
        await _show_barcode_fallback(message, fallback_text, reply_markup)
        return

    try:
        await message.answer_photo(
            BufferedInputFile(png, filename="ticket.png"),
            caption=caption,
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )
    except TelegramRetryAfter as e:
        logger.error(
            f"Telegram rate limit при отправке талона: retry_after={e.retry_after}"
        )
        await asyncio.sleep(e.retry_after)
        try:
            await message.answer_photo(
                BufferedInputFile(png, filename="ticket.png"),
                caption=caption,
                reply_markup=reply_markup,
                parse_mode="Markdown",
            )
        except TelegramAPIError as retry_error:
            logger.error(f"Повторная отправка талона не удалась: {retry_error}")
            await _show_barcode_fallback(message, fallback_text, reply_markup)
            return
    except TelegramAPIError as e:
        logger.error(f"Ошибка отправки талона в Telegram: {e}")
        await _show_barcode_fallback(message, fallback_text, reply_markup)
        return

    # Best-effort удаление статусного сообщения «⏳ Выполняется запись...»
    try:
        await message.delete()
    except Exception as e:
        logger.debug(f"Не удалось удалить статусное сообщение записи: {e}")


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
    uid = str(call.from_user.id)

    # --- Повторная проверка безопасности ---
    if await is_spam(uid):
        await call.answer(_("rate-limit-toast"))
        return

    user_data = await db.get_user_data(uid)
    if p_id not in user_data.get("patients", {}):
        await call.answer("⛔ Пациент не найден", show_alert=True)
        return

    # --- Резолв слота в свежем ответе (§11.1.5) ---
    slots_result, slot_dt = await _resolve_fresh_slot(
        api, d_id, p_id, clinic_id, appointment_id
    )
    if slot_dt is None:
        is_monitored = d_id in user_data.get("monitoring", {}).get(p_id, {})
        await _show_slot_unavailable(
            call, slots_result, p_id, clinic_id, d_id, is_monitored
        )
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
            date=slot_dt.date,
            time=slot_dt.time,
            clinic=clinic_name,
        )

        # Сохраняем запись в БД (T-17) до отправки талона
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
            slot_date=slot_dt.date,
            slot_time=slot_dt.time,
            appointment_id=appointment_id,
            created_at=time_module.time(),
            is_archived=0,
        )
        try:
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

        # Талон: подпись с номером и текстовый фолбэк (T-22)
        ticket = _build_ticket_payload(booking)
        caption = (
            f"{success_text}\n{_('booking-ticket-code-label').format(ticket=ticket)}"
        )
        fallback_text = (
            f"{success_text}\n"
            f"{_('booking-ticket-barcode-unavailable').format(ticket=ticket)}"
        )

        if isinstance(call.message, Message):
            await _deliver_booking_ticket(
                call.message,
                booking,
                caption,
                fallback_text,
                reply_markup,
            )
        else:
            with contextlib.suppress(Exception):
                await call.message.edit_text(  # type: ignore[attr-defined]
                    fallback_text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown",
                )

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
    state: FSMContext,
    callback_data: StartMonitoring,
) -> None:
    """Добавление врача в отслеживание (T-04) и запуск мастера фильтра (T-21).

    Идемпотентность: повторное нажатие не снимает мониторинг, а сразу открывает
    мастер настройки существующего фильтра (§9.3.1).
    """
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

    # --- Идемпотентное добавление: toggle только для новой пары ---
    user_data = await db.get_user_data(uid)
    created = d_id not in user_data.get("monitoring", {}).get(p_id, {})
    if created:
        await db.toggle_monitoring(
            uid, p_id, d_id, d_name, clinic_id, doctor_specialty, date=""
        )

    # --- Запуск мастера фильтра (§9.3) ---
    await filter_setup.begin_filter_wizard(
        call,
        state,
        db,
        p_id,
        clinic_id,
        d_id,
        doctor_name=d_name,
        doctor_specialty=doctor_specialty,
        created=created,
    )


@router.callback_query(create_callback_filter(FilterSetup))
async def filter_setup_entry(
    call: CallbackQuery,
    db: DatabaseManager,
    state: FSMContext,
    callback_data: FilterSetup,
) -> None:
    """Вход в мастер фильтра по кнопке [🔎 Настроить фильтр] (T-21, §9.3.1)."""
    await filter_setup.begin_filter_wizard(
        call,
        state,
        db,
        callback_data.p_id,
        callback_data.clinic_id,
        callback_data.d_id,
    )


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
