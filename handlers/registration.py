from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from api.zdrav_client import ZdravClient
from config import settings
from database.manager import DatabaseManager
from keyboards.inline import get_patient_selection, get_skip_alias_keyboard

router = Router()


class Registration(StatesGroup):
    wait_fio = State()
    wait_bday = State()
    wait_alias = State()


@router.callback_query(F.data == "start_add_p")
async def start_add_patient(call: CallbackQuery, state: FSMContext):
    await state.set_state(Registration.wait_fio)
    if isinstance(call.message, Message):
        await call.message.edit_text("Введите ФИО (Фамилия Имя Отчество):")


@router.message(Registration.wait_fio)
async def process_fio(message: Message, state: FSMContext):
    if not message.text:
        return

    parts = message.text.split()
    if len(parts) != 3:
        await message.answer(
            "Ошибка! ФИО должно состоять строго из 3 слов (Фамилия Имя Отчество)."
        )
        return

    await state.update_data(fio=message.text)
    await state.set_state(Registration.wait_bday)
    await message.answer("Введите дату рождения (дд.мм.гггг):")


@router.message(Registration.wait_bday)
async def process_bday(message: Message, state: FSMContext, api: ZdravClient):
    date_str = message.text or ""
    try:
        date = datetime.strptime(date_str, "%d.%m.%Y")
        if not (datetime(1900, 1, 1) <= date <= datetime.now()):
            raise ValueError("Вне диапазона")
    except ValueError:
        await message.answer(
            "Неверная дата. Введите корректную дату в формате дд.мм.гггг (с 01.01.1900 по сегодня)."
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
            f"✅ Нашли в базе! Введите псевдоним (например, 'Мама', до 25 симв.) или пропустите:",
            reply_markup=get_skip_alias_keyboard(),
        )
    else:
        await message.answer(f"❌ {err}")
        await state.clear()


@router.message(Registration.wait_alias)
async def process_alias(message: Message, state: FSMContext, db: DatabaseManager):
    if message.text and len(message.text) > 25:
        await message.answer("Ошибка! Псевдоним не должен превышать 25 символов.")
        return

    data = await state.get_data()
    uid = str(message.from_user.id) if message.from_user else "unknown"
    p_id = data["p_id"]

    p_info = {"fio": data["fio"], "bday": data["bday"], "alias": message.text}
    await db.add_patient(uid, p_id, p_info)
    await state.clear()

    user_data = db.get_user_data(uid)
    await message.answer(
        "✅ Пациент успешно добавлен!\n\n📋 **Список пациентов:**\n---\nВыберите пациента\nдля настройки мониторинга",
        reply_markup=get_patient_selection(
            user_data["patients"], user_data["monitoring"]
        ),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "skip_alias", Registration.wait_alias)
async def skip_alias(call: CallbackQuery, state: FSMContext, db: DatabaseManager):
    data = await state.get_data()
    uid = str(call.from_user.id) if call.from_user else "unknown"
    p_id = data["p_id"]

    p_info = {"fio": data["fio"], "bday": data["bday"], "alias": None}
    await db.add_patient(uid, p_id, p_info)
    await state.clear()

    user_data = db.get_user_data(uid)
    if isinstance(call.message, Message):
        await call.message.edit_text(
            "📋 **Ваши пациенты:**",
            reply_markup=get_patient_selection(
                user_data["patients"], user_data["monitoring"]
            ),
            parse_mode="Markdown",
        )
