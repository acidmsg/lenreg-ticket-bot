import contextlib
from datetime import datetime

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from loguru import logger

from src.api.zdrav_client import ZdravClient
from src.config import settings
from src.database.manager import DatabaseManager
from src.database.types import PatientInfo
from src.handlers.callback_parser import cb_filter
from src.handlers.callbacks import AddPatient, CancelRegistration, SkipAlias
from src.i18n import _
from src.keyboards.inline import get_patient_selection, get_registration_keyboard

router = Router()


class Registration(StatesGroup):
    wait_fio = State()
    wait_bday = State()
    wait_alias = State()


@router.callback_query(cb_filter(AddPatient))
async def start_add_patient(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Registration.wait_fio)
    if isinstance(call.message, Message):
        with contextlib.suppress(Exception):
            await call.message.delete()
        await call.message.answer(
            _("enter-full-name"),
            reply_markup=get_registration_keyboard(step="fio"),
        )


@router.message(Registration.wait_fio)
async def process_fio(message: Message, state: FSMContext, db: DatabaseManager) -> None:
    if not message.text:
        return

    parts = message.text.split()
    if len(parts) != 3:
        await message.answer(
            _("fio-3-words-error"),
            reply_markup=get_registration_keyboard(step="fio"),
        )
        return

    await state.update_data(fio=message.text)
    await state.set_state(Registration.wait_bday)

    await message.answer(
        _("enter-birthday"),
        reply_markup=get_registration_keyboard(step="bday"),
    )


@router.message(Registration.wait_bday)
async def process_bday(
    message: Message, state: FSMContext, api: ZdravClient, db: DatabaseManager
) -> None:
    date_str = message.text or ""
    try:
        date = datetime.strptime(date_str, "%d.%m.%Y")
        if not (datetime(1900, 1, 1) <= date <= datetime.now()):
            raise ValueError("Вне диапазона")
    except ValueError:
        await message.answer(
            _("invalid-date"),
            reply_markup=get_registration_keyboard(step="bday"),
        )
        return

    data = await state.get_data()
    fio = data["fio"]

    # Двухэтапный поиск пациента по всем доступным clinic_id
    clinic_ids_to_try: list[str] = []

    # Этап 1: клиника по умолчанию
    clinic_ids_to_try.append(settings.DEFAULT_CLINIC_ID)

    # Этап 2: пустая строка (глобальный поиск, если API поддерживает)
    clinic_ids_to_try.append("")

    # Этап 3: все активные clinic_id из БД
    try:
        active_ids = await db._db.get_active_clinic_ids()
        for cid in active_ids:
            if cid not in clinic_ids_to_try:
                clinic_ids_to_try.append(cid)
    except Exception:
        logger.warning("Не удалось получить список активных clinic_id")

    p_id: str | None = None
    last_err: str | None = None

    for clinic_id in clinic_ids_to_try:
        p_id, err = await api.fetch_patient_id(fio, date, clinic_id)
        if p_id is not None:
            logger.info(
                "Пациент {} найден в clinic_id={} (попытка {}/{})",
                fio,
                clinic_id,
                clinic_ids_to_try.index(clinic_id) + 1,
                len(clinic_ids_to_try),
            )
            break
        last_err = err

    if p_id:
        await state.update_data(p_id=p_id, bday=str(date.date()))
        await state.set_state(Registration.wait_alias)
        await message.answer(
            _("patient-found-in-db"),
            reply_markup=get_registration_keyboard(step="alias"),
        )
    else:
        await message.answer(
            f"❌ {last_err or 'Пациент не найден.'}",
            reply_markup=get_registration_keyboard(step="fio"),
        )
        await state.clear()


async def _show_patient_selection(
    call: CallbackQuery,
    uid: str,
    db: DatabaseManager,
    text: str,
) -> None:
    """Показывает список пациентов после операции (добавление/отмена)."""
    user_data = await db.get_user_data(uid)
    if isinstance(call.message, Message):
        await call.message.edit_text(
            text,
            reply_markup=get_patient_selection(
                user_data["patients"], user_data["monitoring"]
            ),
            parse_mode="Markdown",
        )


@router.message(Registration.wait_alias)
async def process_alias(
    message: Message, state: FSMContext, db: DatabaseManager
) -> None:
    if message.text and len(message.text) > 25:
        await message.answer(
            _("alias-too-long"),
            reply_markup=get_registration_keyboard(step="alias"),
        )
        return

    data = await state.get_data()
    uid = str(message.from_user.id) if message.from_user else "unknown"
    p_id = data["p_id"]

    # Если псевдоним не введён — оставляем None (отобразится ФИО)
    alias = message.text if message.text else None
    if alias:
        p_info = PatientInfo(fio=data["fio"], bday=data["bday"], alias=alias)
    else:
        p_info = PatientInfo(fio=data["fio"], bday=data["bday"])
    try:
        await db.add_patient(uid, p_id, p_info)
        await state.clear()

        user_data = await db.get_user_data(uid)
        await message.answer(
            _("patient-added-success"),
            reply_markup=get_patient_selection(
                user_data["patients"], user_data["monitoring"]
            ),
            parse_mode="Markdown",
        )
    except Exception:
        logger.exception("Ошибка при добавлении пациента {} для uid={}", p_id, uid)
        await state.clear()
        await message.answer(
            _("patient-save-error"),
            reply_markup=get_registration_keyboard(step="fio"),
        )


@router.callback_query(cb_filter(SkipAlias), Registration.wait_alias)
async def skip_alias(
    call: CallbackQuery, state: FSMContext, db: DatabaseManager
) -> None:
    """Пропустить ввод псевдонима — alias остаётся None, отобразится ФИО."""
    if not call.from_user or not call.message:
        return
    data = await state.get_data()
    uid = str(call.from_user.id)
    p_id = data["p_id"]

    # При пропуске псевдоним не сохраняем (None) — отобразится ФИО через fallback
    p_info = PatientInfo(fio=data["fio"], bday=data["bday"])
    try:
        await db.add_patient(uid, p_id, p_info)
        await state.clear()
        await _show_patient_selection(call, uid, db, _("patient-added-success"))
    except Exception:
        logger.exception("Ошибка при пропуске alias для p_id={} uid={}", p_id, uid)
        await state.clear()
        if isinstance(call.message, Message):
            await call.message.edit_text(
                _("patient-save-error-short"),
                reply_markup=get_registration_keyboard(step="fio"),
            )


@router.callback_query(cb_filter(CancelRegistration))
async def cancel_registration(
    call: CallbackQuery, state: FSMContext, db: DatabaseManager
) -> None:
    await state.clear()
    uid = str(call.from_user.id) if call.from_user else "unknown"
    await _show_patient_selection(call, uid, db, _("your-patients-header"))
