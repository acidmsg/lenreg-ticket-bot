from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime
from keyboards.inline import get_skip_alias_keyboard, get_patient_selection
from database.manager import DatabaseManager
from api.zdrav_client import ZdravClient

router = Router()

class Registration(StatesGroup):
    wait_fio = State()
    wait_bday = State()
    wait_alias = State()

@router.callback_query(F.data == "start_add_p")
async def start_add_patient(call: CallbackQuery, state: FSMContext):
    await state.set_state(Registration.wait_fio)
    if isinstance(call.message, Message):
        await call.message.edit_text("╨Т╨▓╨╡╨┤╨╕╤В╨╡ ╨д╨Ш╨Ю (╨д╨░╨╝╨╕╨╗╨╕╤П ╨Ш╨╝╤П ╨Ю╤В╤З╨╡╤Б╤В╨▓╨╛):")

@router.message(Registration.wait_fio)
async def process_fio(message: Message, state: FSMContext):
    if not message.text:
        return

    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("╨Ю╤И╨╕╨▒╨║╨░! ╨д╨Ш╨Ю ╨┤╨╛╨╗╨╢╨╜╨╛ ╤Б╨╛╤Б╤В╨╛╤П╤В╤М ╤Б╤В╤А╨╛╨│╨╛ ╨╕╨╖ 3 ╤Б╨╗╨╛╨▓ (╨д╨░╨╝╨╕╨╗╨╕╤П ╨Ш╨╝╤П ╨Ю╤В╤З╨╡╤Б╤В╨▓╨╛).")
        return

    await state.update_data(fio=message.text)
    await state.set_state(Registration.wait_bday)
    await message.answer("╨Т╨▓╨╡╨┤╨╕╤В╨╡ ╨┤╨░╤В╤Г ╤А╨╛╨╢╨┤╨╡╨╜╨╕╤П (╨┤╨┤.╨╝╨╝.╨│╨│╨│╨│):")

@router.message(Registration.wait_bday)
async def process_bday(message: Message, state: FSMContext, api: ZdravClient):
    date_str = message.text or ""
    try:
        date = datetime.strptime(date_str, "%d.%m.%Y")
        if not (datetime(1900, 1, 1) <= date <= datetime.now()):
            raise ValueError("╨Т╨╜╨╡ ╨┤╨╕╨░╨┐╨░╨╖╨╛╨╜╨░")
    except ValueError:
        await message.answer("╨Э╨╡╨▓╨╡╤А╨╜╨░╤П ╨┤╨░╤В╨░. ╨Т╨▓╨╡╨┤╨╕╤В╨╡ ╨║╨╛╤А╤А╨╡╨║╤В╨╜╤Г╤О ╨┤╨░╤В╤Г ╨▓ ╤Д╨╛╤А╨╝╨░╤В╨╡ ╨┤╨┤.╨╝╨╝.╨│╨│╨│╨│ (╤Б 01.01.1900 ╨┐╨╛ ╤Б╨╡╨│╨╛╨┤╨╜╤П).")
        return

    data = await state.get_data()
    fio = data['fio']

    # ╨Ф╨╗╤П ╨┐╤А╨╛╨▓╨╡╤А╨║╨╕ ╨┐╨░╤Ж╨╕╨╡╨╜╤В╨░ ╨▒╨╡╤А╨╡╨╝ ╤В╨╡╤Б╤В╨╛╨▓╤Г╤О ╨║╨╗╨╕╨╜╨╕╨║╤Г 272 (╨╕╨╗╨╕ ╨╗╤О╨▒╤Г╤О ╨┤╤А╤Г╨│╤Г╤О)
    clinic_id = "272"
    p_id, err = await api.fetch_patient_id(fio, date, clinic_id)

    if p_id:
        await state.update_data(p_id=p_id, bday=str(date.date()))
        await state.set_state(Registration.wait_alias)
        await message.answer(
            f"тЬЕ ╨Э╨░╤И╨╗╨╕ ╨▓ ╨▒╨░╨╖╨╡! ╨Т╨▓╨╡╨┤╨╕╤В╨╡ ╨┐╤Б╨╡╨▓╨┤╨╛╨╜╨╕╨╝ (╨╜╨░╨┐╤А╨╕╨╝╨╡╤А, '╨Ь╨░╨╝╨░', ╨┤╨╛ 25 ╤Б╨╕╨╝╨▓.) ╨╕╨╗╨╕ ╨┐╤А╨╛╨┐╤Г╤Б╤В╨╕╤В╨╡:",
            reply_markup=get_skip_alias_keyboard()
        )
    else:
        await message.answer(f"тЭМ {err}")
        await state.clear()

@router.message(Registration.wait_alias)
async def process_alias(message: Message, state: FSMContext, db: DatabaseManager):
    if message.text and len(message.text) > 25:
        await message.answer("╨Ю╤И╨╕╨▒╨║╨░! ╨Я╤Б╨╡╨▓╨┤╨╛╨╜╨╕╨╝ ╨╜╨╡ ╨┤╨╛╨╗╨╢╨╡╨╜ ╨┐╤А╨╡╨▓╤Л╤И╨░╤В╤М 25 ╤Б╨╕╨╝╨▓╨╛╨╗╨╛╨▓.")
        return

    data = await state.get_data()
    uid = str(message.from_user.id) if message.from_user else "unknown"
    p_id = data['p_id']

    p_info = {
        "fio": data['fio'],
        "bday": data['bday'],
        "alias": message.text
    }
    await db.add_patient(uid, p_id, p_info)
    await state.clear()

    user_data = db.get_user_data(uid)
    await message.answer(
        "тЬЕ ╨Я╨░╤Ж╨╕╨╡╨╜╤В ╤Г╤Б╨┐╨╡╤И╨╜╨╛ ╨┤╨╛╨▒╨░╨▓╨╗╨╡╨╜!\n\nЁЯУЛ **╨б╨┐╨╕╤Б╨╛╨║ ╨┐╨░╤Ж╨╕╨╡╨╜╤В╨╛╨▓:**\n---\n╨Т╤Л╨▒╨╡╤А╨╕╤В╨╡ ╨┐╨░╤Ж╨╕╨╡╨╜╤В╨░\n╨┤╨╗╤П ╨╜╨░╤Б╤В╤А╨╛╨╣╨║╨╕ ╨╝╨╛╨╜╨╕╤В╨╛╤А╨╕╨╜╨│╨░",
        reply_markup=get_patient_selection(user_data["patients"], user_data["monitoring"]),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "skip_alias", Registration.wait_alias)
async def skip_alias(call: CallbackQuery, state: FSMContext, db: DatabaseManager):
    data = await state.get_data()
    uid = str(call.from_user.id) if call.from_user else "unknown"
    p_id = data['p_id']

    p_info = {
        "fio": data['fio'],
        "bday": data['bday'],
        "alias": None
    }
    await db.add_patient(uid, p_id, p_info)
    await state.clear()

    user_data = db.get_user_data(uid)
    if isinstance(call.message, Message):
        await call.message.edit_text(
            "ЁЯУЛ **╨Т╨░╤И╨╕ ╨┐╨░╤Ж╨╕╨╡╨╜╤В╤Л:**",
            reply_markup=get_patient_selection(user_data["patients"], user_data["monitoring"]),
            parse_mode="Markdown"
        )
