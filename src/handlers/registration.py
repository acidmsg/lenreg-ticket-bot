import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.api.zdrav_client import ZdravClient
from src.config import settings
from src.database.manager import DatabaseManager
from src.keyboards.inline import get_patient_selection, get_registration_keyboard

logger = logging.getLogger(__name__)

router = Router()


class Registration(StatesGroup):
    wait_fio = State()
    wait_bday = State()
    wait_alias = State()


@router.callback_query(F.data == "start_add_p")
async def start_add_patient(call: CallbackQuery, state: FSMContext):
    await state.set_state(Registration.wait_fio)
    if isinstance(call.message, Message):
        await call.message.edit_text(
            "Введите ФИО (Фамилия Имя Отчество):",
            reply_markup=get_registration_keyboard(step="fio"),
        )


@router.message(Registration.wait_fio)
async def process_fio(message: Message, state: FSMContext, db: DatabaseManager):
    if not message.text:
        return

    parts = message.text.split()
    if len(parts) != 3:
        await message.answer(
            "Ошибка! ФИО должно состоять строго из 3 слов (Фамилия Имя Отчество).",
            reply_markup=get_registration_keyboard(step="fio"),
        )
        return

    await state.update_data(fio=message.text)
    await state.set_state(Registration.wait_bday)

    await message.answer(
        "Введите дату рождения (дд.мм.гггг):",
        reply_markup=get_registration_keyboard(step="bday"),
    )


@router.message(Registration.wait_bday)
async def process_bday(
    message: Message, state: FSMContext, api: ZdravClient, db: DatabaseManager
):
    date_str = message.text or ""
    try:
        date = datetime.strptime(date_str, "%d.%m.%Y")
        if not (datetime(1900, 1, 1) <= date <= datetime.now()):
            raise ValueError("Вне диапазона")
    except ValueError:
        await message.answer(
            "Неверная дата. Введите корректную дату "
            "в формате дд.мм.гггг (с 01.01.1900 по сегодня).",
            reply_markup=get_registration_keyboard(step="bday"),
        )
        return

    data = await state.get_data()
    fio = data["fio"]

    # Для проверки пациента используем клинику по умолчанию из настроек
    clinic_id = settings.DEFAULT_CLINIC_ID
    p_id, err = await api.fetch_patient_id(fio, date, clinic_id)

    if p_id:
        await state.update_data(p_id=p_id, bday=str(date.date()))
        await state.set_state(Registration.wait_alias)
        await message.answer(
            "✅ Нашли в базе! Введите псевдоним "
            "(например, 'Мама', до 25 симв.) или пропустите:",
            reply_markup=get_registration_keyboard(step="alias"),
        )
    else:
        await message.answer(
            f"❌ {err}", reply_markup=get_registration_keyboard(step="fio")
        )
        await state.clear()


@router.message(Registration.wait_alias)
async def process_alias(message: Message, state: FSMContext, db: DatabaseManager):
    if message.text and len(message.text) > 25:
        await message.answer(
            "Ошибка! Псевдоним не должен превышать 25 символов.",
            reply_markup=get_registration_keyboard(step="alias"),
        )
        return

    data = await state.get_data()
    uid = str(message.from_user.id) if message.from_user else "unknown"
    p_id = data["p_id"]

    # Если псевдоним не введён — оставляем None (отобразится ФИО)
    alias = message.text if message.text else None
    p_info = {"fio": data["fio"], "bday": data["bday"], "alias": alias}
    try:
        await db.add_patient(uid, p_id, p_info)
        await state.clear()

        user_data = await db.get_user_data(uid)
        await message.answer(
            "✅ Пациент успешно добавлен!\n\n"
            "📋 **Список пациентов:**\n---\n"
            "Выберите пациента\nдля настройки мониторинга",
            reply_markup=get_patient_selection(
                user_data["patients"], user_data["monitoring"]
            ),
            parse_mode="Markdown",
        )
    except Exception:
        logger.exception("Ошибка при добавлении пациента %s для uid=%s", p_id, uid)
        await state.clear()
        await message.answer(
            "⚠️ Произошла ошибка при сохранении пациента. Попробуйте снова.",
            reply_markup=get_registration_keyboard(step="fio"),
        )


@router.callback_query(F.data == "skip_alias", Registration.wait_alias)
async def skip_alias(call: CallbackQuery, state: FSMContext, db: DatabaseManager):
    """Пропустить ввод псевдонима — alias остаётся None, отобразится ФИО."""
    if not call.from_user or not call.message:
        return
    data = await state.get_data()
    uid = str(call.from_user.id)
    p_id = data["p_id"]

    # При пропуске псевдоним не сохраняем (None) — отобразится ФИО через fallback
    p_info = {"fio": data["fio"], "bday": data["bday"], "alias": None}
    try:
        await db.add_patient(uid, p_id, p_info)
        await state.clear()

        user_data = await db.get_user_data(uid)
        if isinstance(call.message, Message):
            await call.message.edit_text(
                "✅ Пациент успешно добавлен!\n\n"
                "📋 **Список пациентов:**\n---\n"
                "Выберите пациента\nдля настройки мониторинга",
                reply_markup=get_patient_selection(
                    user_data["patients"], user_data["monitoring"]
                ),
                parse_mode="Markdown",
            )
    except Exception:
        logger.exception("Ошибка при пропуске alias для p_id=%s uid=%s", p_id, uid)
        await state.clear()
        if isinstance(call.message, Message):
            await call.message.edit_text(
                "⚠️ Произошла ошибка при сохранении. Попробуйте снова.",
                reply_markup=get_registration_keyboard(step="fio"),
            )


@router.callback_query(F.data == "cancel_registration")
async def cancel_registration(
    call: CallbackQuery, state: FSMContext, db: DatabaseManager
):
    await state.clear()
    uid = str(call.from_user.id) if call.from_user else "unknown"
    user_data = await db.get_user_data(uid)
    if isinstance(call.message, Message):
        await call.message.edit_text(
            "📋 **Ваши пациенты:**\n---\nВыберите пациента для настройки мониторинга",
            reply_markup=get_patient_selection(
                user_data["patients"], user_data["monitoring"]
            ),
            parse_mode="Markdown",
        )
