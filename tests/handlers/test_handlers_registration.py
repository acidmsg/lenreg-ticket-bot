# type: ignore
"""
Интеграционные тесты для handlers/registration.py — T1.1.

Тестирует FSM-сценарий регистрации пациента:
- start_add_patient → wait_fio
- process_fio (валидация 3 слов) → wait_bday
- process_bday (валидация даты + поиск в API) → wait_alias
- process_alias (сохранение с псевдонимом) → готово
- skip_alias (сохранение без псевдонима) → готово
- cancel_registration (отмена) → возврат к списку
"""

from datetime import datetime
from unittest.mock import AsyncMock

from aiogram.types import CallbackQuery, Chat, Message, User
from src.handlers.registration import Registration

# ── Fake FSMContext (без RedisStorage) ─────────────────────────────────


class FakeFSMContext:
    """Имитирует FSMContext aiogram для тестирования без RedisStorage."""

    def __init__(self) -> None:
        self._data: dict = {}
        self._state = None

    async def set_state(self, state) -> None:
        self._state = state

    async def update_data(self, **kwargs) -> None:
        self._data.update(kwargs)

    async def get_data(self) -> dict:
        return dict(self._data)

    async def clear(self) -> None:
        self._data.clear()
        self._state = None

    async def get_state(self):
        return self._state


# ── Фабрики объектов aiogram ──────────────────────────────────────────

TEST_USER_ID = 123456789


def _make_user(user_id: int = TEST_USER_ID) -> User:
    return User(id=user_id, is_bot=False, first_name="Test")


def make_message(text: str | None, user_id: int = TEST_USER_ID) -> Message:
    """
    Создаёт объект Message с замоканными answer/edit_text.

    Модели aiogram — frozen (pydantic), поэтому методы присоединяются
    через object.__setattr__, обходящий валидацию pydantic.
    """
    msg = Message(
        message_id=1,
        date=datetime.now(),
        chat=Chat(id=user_id, type="private"),
        from_user=_make_user(user_id),
        text=text,
    )
    object.__setattr__(msg, "answer", AsyncMock())
    object.__setattr__(msg, "edit_text", AsyncMock())
    return msg


def make_callback(
    data: str,
    user_id: int = TEST_USER_ID,
    message: Message | None = None,
) -> CallbackQuery:
    """
    Создаёт CallbackQuery с замоканными answer и message.answer/edit_text.

    Модель frozen — используем object.__setattr__ для мок-методов.
    Если message не передан, создаётся тестовый Message.
    """
    if message is None:
        message = make_message("dummy", user_id)

    call = CallbackQuery(
        id="cb_test_001",
        from_user=_make_user(user_id),
        message=message,
        data=data,
        chat_instance="test",
    )
    object.__setattr__(call, "answer", AsyncMock())
    return call


def make_mock_api() -> AsyncMock:
    """ZdravClient с замоканным fetch_patient_id."""
    api = AsyncMock()
    api.fetch_patient_id = AsyncMock()
    return api


# ── T1.1.1: start_add_patient ─────────────────────────────────────────


class TestStartAddPatient:
    """Начало FSM-сценария: переход в состояние wait_fio."""

    async def test_sets_wait_fio_state(self):
        """Корректный callback — состояние wait_fio, сообщение отредактировано."""
        from src.handlers.registration import start_add_patient

        call = make_callback("start_add_p")
        fsm = FakeFSMContext()

        await start_add_patient(call, state=fsm)

        assert fsm._state == Registration.wait_fio
        call.message.edit_text.assert_called_once()

    async def test_edit_text_called_with_correct_text(self):
        """Проверяем, что edit_text вызван с корректным текстом."""
        from src.handlers.registration import start_add_patient

        call = make_callback("start_add_p")
        fsm = FakeFSMContext()

        await start_add_patient(call, state=fsm)

        call.message.edit_text.assert_called_once()
        args = call.message.edit_text.call_args[0]
        assert "ФИО" in args[0]


# ── T1.1.2: process_fio ───────────────────────────────────────────────


class TestProcessFio:
    """Валидация ФИО: 3 слова, переход в wait_bday."""

    async def test_valid_fio_transitions_to_bday(self, db_manager):
        """Валидное ФИО (3 слова) → wait_bday, данные сохранены в FSM."""
        from src.handlers.registration import process_fio

        msg = make_message("Иванов Иван Иванович")
        fsm = FakeFSMContext()
        await fsm.set_state(Registration.wait_fio)

        await process_fio(msg, state=fsm, db=db_manager)

        assert fsm._state == Registration.wait_bday
        data = await fsm.get_data()
        assert data["fio"] == "Иванов Иван Иванович"
        msg.answer.assert_called_once()

    async def test_invalid_fio_two_words(self, db_manager):
        """ФИО из 2 слов — ошибка, состояние не меняется."""
        from src.handlers.registration import process_fio

        msg = make_message("Иванов Иван")
        fsm = FakeFSMContext()
        await fsm.set_state(Registration.wait_fio)

        await process_fio(msg, state=fsm, db=db_manager)

        assert fsm._state == Registration.wait_fio
        msg.answer.assert_called_once()
        call_args = msg.answer.call_args[0]
        assert "Ошибка" in call_args[0]
        assert "3 слов" in call_args[0]

    async def test_invalid_fio_four_words(self, db_manager):
        """ФИО из 4 слов — ошибка, состояние не меняется."""
        from src.handlers.registration import process_fio

        msg = make_message("Иванов Иван Иванович Младший")
        fsm = FakeFSMContext()
        await fsm.set_state(Registration.wait_fio)

        await process_fio(msg, state=fsm, db=db_manager)

        assert fsm._state == Registration.wait_fio
        msg.answer.assert_called_once()

    async def test_empty_text_returns_early(self, db_manager):
        """Пустой текст сообщения — handler выходит, answer не вызывается."""
        from src.handlers.registration import process_fio

        msg = make_message(None)
        fsm = FakeFSMContext()
        await fsm.set_state(Registration.wait_fio)

        await process_fio(msg, state=fsm, db=db_manager)

        msg.answer.assert_not_called()

    async def test_fio_with_extra_spaces(self, db_manager):
        """Лишние пробелы — split() обрабатывает, 3 слова проходят."""
        from src.handlers.registration import process_fio

        msg = make_message("  Иванов   Иван   Иванович  ")
        fsm = FakeFSMContext()
        await fsm.set_state(Registration.wait_fio)

        await process_fio(msg, state=fsm, db=db_manager)

        assert fsm._state == Registration.wait_bday
        data = await fsm.get_data()
        assert data["fio"] == "  Иванов   Иван   Иванович  "


# ── T1.1.3: process_bday ──────────────────────────────────────────────


class TestProcessBday:
    """Валидация даты рождения и поиск пациента в API."""

    async def test_valid_date_patient_found(self, db_manager):
        """Валидная дата + пациент найден → wait_alias, данные в FSM."""
        from src.handlers.registration import process_bday

        api = make_mock_api()
        api.fetch_patient_id.return_value = ("12345", None)

        msg = make_message("01.01.1990")
        fsm = FakeFSMContext()
        await fsm.set_state(Registration.wait_bday)
        await fsm.update_data(fio="Иванов Иван Иванович")

        await process_bday(msg, state=fsm, api=api, db=db_manager)

        assert fsm._state == Registration.wait_alias
        data = await fsm.get_data()
        assert data["p_id"] == "12345"
        assert data["bday"] == "1990-01-01"
        msg.answer.assert_called_once()
        assert "Нашли" in msg.answer.call_args[0][0]

    async def test_invalid_date_format(self, db_manager):
        """Неверный формат (дефисы вместо точек) — ошибка, состояние не меняется."""
        from src.handlers.registration import process_bday

        api = make_mock_api()
        msg = make_message("31-12-1990")
        fsm = FakeFSMContext()
        await fsm.set_state(Registration.wait_bday)
        await fsm.update_data(fio="Иванов Иван Иванович")

        await process_bday(msg, state=fsm, api=api, db=db_manager)

        assert fsm._state == Registration.wait_bday
        api.fetch_patient_id.assert_not_called()
        msg.answer.assert_called_once()
        assert "Неверная дата" in msg.answer.call_args[0][0]

    async def test_date_before_1900(self, db_manager):
        """Дата раньше 01.01.1900 — ошибка, состояние не меняется."""
        from src.handlers.registration import process_bday

        api = make_mock_api()
        msg = make_message("01.01.1899")
        fsm = FakeFSMContext()
        await fsm.set_state(Registration.wait_bday)
        await fsm.update_data(fio="Иванов Иван Иванович")

        await process_bday(msg, state=fsm, api=api, db=db_manager)

        assert fsm._state == Registration.wait_bday
        api.fetch_patient_id.assert_not_called()

    async def test_future_date(self, db_manager):
        """Дата в будущем — ошибка, состояние не меняется."""
        from src.handlers.registration import process_bday

        api = make_mock_api()
        msg = make_message("01.01.2099")
        fsm = FakeFSMContext()
        await fsm.set_state(Registration.wait_bday)
        await fsm.update_data(fio="Иванов Иван Иванович")

        await process_bday(msg, state=fsm, api=api, db=db_manager)

        assert fsm._state == Registration.wait_bday
        api.fetch_patient_id.assert_not_called()

    async def test_patient_not_found_in_api(self, db_manager):
        """API не нашёл пациента — FSM очищается, возврат к wait_fio."""
        from src.handlers.registration import process_bday

        api = make_mock_api()
        api.fetch_patient_id.return_value = (None, "Пациент не найден в базе")

        msg = make_message("01.01.1990")
        fsm = FakeFSMContext()
        await fsm.set_state(Registration.wait_bday)
        await fsm.update_data(fio="Иванов Иван Иванович")

        await process_bday(msg, state=fsm, api=api, db=db_manager)

        # state.clear() вызывается — FSM сброшен
        assert fsm._state is None
        assert fsm._data == {}
        msg.answer.assert_called_once()
        assert "❌" in msg.answer.call_args[0][0]


# ── T1.1.4: process_alias ─────────────────────────────────────────────


class TestProcessAlias:
    """Ввод псевдонима и сохранение пациента."""

    async def test_valid_alias_saves_patient(self, db_manager):
        """Корректный псевдоним — пациент сохранён в БД, FSM очищен."""
        from src.handlers.registration import process_alias

        msg = make_message("Мама")
        fsm = FakeFSMContext()
        await fsm.set_state(Registration.wait_alias)
        await fsm.update_data(
            fio="Иванова Анна Петровна",
            bday="1985-05-15",
            p_id="12345",
        )

        await process_alias(msg, state=fsm, db=db_manager)

        # Пациент сохранён
        user_data = await db_manager.get_user_data(str(TEST_USER_ID))
        assert "12345" in user_data["patients"]
        assert user_data["patients"]["12345"]["alias"] == "Мама"
        assert user_data["patients"]["12345"]["fio"] == "Иванова Анна Петровна"
        assert user_data["patients"]["12345"]["bday"] == "1985-05-15"

        # FSM очищен
        assert fsm._state is None
        msg.answer.assert_called_once()
        assert "✅" in msg.answer.call_args[0][0]

    async def test_alias_exact_25_chars(self, db_manager):
        """Псевдоним ровно 25 символов — проходит."""
        from src.handlers.registration import process_alias

        alias = "A" * 25  # ровно 25 символов
        msg = make_message(alias)
        fsm = FakeFSMContext()
        await fsm.set_state(Registration.wait_alias)
        await fsm.update_data(
            fio="Иванова Анна Петровна",
            bday="1985-05-15",
            p_id="12345",
        )

        await process_alias(msg, state=fsm, db=db_manager)

        user_data = await db_manager.get_user_data(str(TEST_USER_ID))
        assert user_data["patients"]["12345"]["alias"] == alias

    async def test_alias_too_long(self, db_manager):
        """Псевдоним >25 символов — ошибка, состояние не меняется."""
        from src.handlers.registration import process_alias

        msg = make_message("ОченьДлинныйПсевдонимБолее25СимволовТочно")
        fsm = FakeFSMContext()
        await fsm.set_state(Registration.wait_alias)
        await fsm.update_data(
            fio="Иванова Анна Петровна",
            bday="1985-05-15",
            p_id="12345",
        )

        await process_alias(msg, state=fsm, db=db_manager)

        # Состояние не изменилось
        assert fsm._state == Registration.wait_alias
        msg.answer.assert_called_once()
        call_args = msg.answer.call_args[0]
        assert "Ошибка" in call_args[0]
        assert "25" in call_args[0]

        # Пациент не сохранён
        user_data = await db_manager.get_user_data(str(TEST_USER_ID))
        assert "12345" not in user_data["patients"]

    async def test_empty_alias_saves_without_alias(self, db_manager):
        """Пустой текст → alias удаляется (None), пациент сохранён."""
        from src.handlers.registration import process_alias

        msg = make_message(None)
        fsm = FakeFSMContext()
        await fsm.set_state(Registration.wait_alias)
        await fsm.update_data(
            fio="Петров Пётр Петрович",
            bday="2000-01-01",
            p_id="67890",
        )

        await process_alias(msg, state=fsm, db=db_manager)

        user_data = await db_manager.get_user_data(str(TEST_USER_ID))
        assert "67890" in user_data["patients"]
        # database.get_user_patients удаляет ключ alias если он None
        assert "alias" not in user_data["patients"]["67890"]
        assert user_data["patients"]["67890"]["fio"] == "Петров Пётр Петрович"


# ── T1.1.5: skip_alias ────────────────────────────────────────────────


class TestSkipAlias:
    """Пропуск ввода псевдонима через callback."""

    async def test_skip_alias_saves_patient(self, db_manager):
        """Пропуск → alias удаляется (None), пациент сохранён, FSM очищен."""
        from src.handlers.registration import skip_alias

        call = make_callback("skip_alias")
        fsm = FakeFSMContext()
        await fsm.set_state(Registration.wait_alias)
        await fsm.update_data(
            fio="Петров Пётр Петрович",
            bday="2000-01-01",
            p_id="67890",
        )

        await skip_alias(call, state=fsm, db=db_manager)

        # Пациент сохранён без псевдонима
        user_data = await db_manager.get_user_data(str(TEST_USER_ID))
        assert "67890" in user_data["patients"]
        # database.get_user_patients удаляет ключ alias если он None
        assert "alias" not in user_data["patients"]["67890"]
        assert user_data["patients"]["67890"]["fio"] == "Петров Пётр Петрович"

        # FSM очищен
        assert fsm._state is None


# ── T1.1.6: cancel_registration ───────────────────────────────────────


class TestCancelRegistration:
    """Отмена сценария регистрации."""

    async def test_cancel_clears_state_and_shows_patient_list(self, db_manager):
        """Отмена — FSM очищен, показывается список пациентов."""
        from src.handlers.registration import cancel_registration

        call = make_callback("cancel_registration")
        fsm = FakeFSMContext()
        await fsm.set_state(Registration.wait_fio)
        await fsm.update_data(fio="Иванов Иван Иванович")

        await cancel_registration(call, state=fsm, db=db_manager)

        # FSM очищен
        assert fsm._state is None
        assert fsm._data == {}
        call.message.edit_text.assert_called_once()
