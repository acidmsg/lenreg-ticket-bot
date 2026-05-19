# type: ignore
"""
Интеграционные тесты для handlers/common.py — T1.2.

Тестирует основные обработчики навигации и мониторинга:
- cmd_start, back_to_main
- select_patient, select_city, select_clinic
- toggle_doctor (включение/отключение)
- stop_patient_monitoring, stop_clinic_monitoring, stop_all_monitoring
- back_to_cities, back_to_clinics
- handle_noop, handle_delete_patient
"""

from unittest.mock import AsyncMock

# ── Reuse фабрик из test_handlers_registration ─────────────────────────
from tests.handlers.test_handlers_registration import (
    TEST_USER_ID,
    make_callback,
    make_message,
    make_mock_api,
)

# ── Fixture: сидирование клиник и врачей ──────────────────────────────


async def _seed_clinic(db_manager, clinic_id: str, name: str):
    """Сидирует одну активную клинику."""
    await db_manager._db.upsert_clinic(clinic_id, name)


async def _seed_doctors(db_manager, clinic_id: str, doctors: list[dict]):
    """Сидирует список врачей для клиники."""
    for doc in doctors:
        await db_manager._db.upsert_doctor(
            clinic_id=clinic_id,
            doctor_id=doc["id"],
            name=doc["name"],
            specialty=doc.get("specialty", ""),
        )


def make_mock_bot() -> AsyncMock:
    """Создаёт AsyncMock для Bot aiogram."""
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    # send_photo возвращает объект с int message_id, иначе SQLite падает
    bot.send_photo = AsyncMock(return_value=AsyncMock(message_id=12345))
    bot.edit_message_text = AsyncMock()
    bot.delete_message = AsyncMock()
    return bot


# ── T1.2.1: cmd_start ─────────────────────────────────────────────────


class TestCmdStart:
    """Обработчик /start."""

    async def test_no_patients_shows_welcome(self, db_manager):
        """Нет пациентов — приветствие + предложение добавить."""
        from src.handlers.common import cmd_start

        msg = make_message("/start")
        bot = make_mock_bot()
        # Мокаем message_id для сохранения в БД (строка 337)
        msg.answer.return_value.message_id = 999
        await cmd_start(msg, db=db_manager, bot=bot)

        msg.answer.assert_called_once()
        # Текст передаётся позиционно: message.answer("text", reply_markup=...)
        text = msg.answer.call_args[0][0]
        assert "У тебя пока нет добавленных пациентов" in text
        assert "reply_markup" in msg.answer.call_args[1]

    async def test_with_patients_shows_list(self, db_manager):
        """Есть пациенты — показывается список."""
        from src.handlers.common import cmd_start

        await db_manager.add_patient(
            str(TEST_USER_ID),
            "111",
            {"fio": "Иванов Иван Иванович", "bday": "1990-01-01", "alias": None},
        )
        msg = make_message("/start")
        bot = make_mock_bot()
        # Мокаем message_id для сохранения в БД (строка 337)
        msg.answer.return_value.message_id = 999
        await cmd_start(msg, db=db_manager, bot=bot)

        msg.answer.assert_called_once()
        text = msg.answer.call_args[0][0]
        assert "Ваши пациенты" in text
        assert "reply_markup" in msg.answer.call_args[1]

    async def test_no_from_user_uses_unknown_uid(self, db_manager):
        """Нет from_user — uid = 'unknown', показывается приветствие."""
        from src.handlers.common import cmd_start

        msg = make_message("/start")
        object.__setattr__(msg, "from_user", None)
        bot = make_mock_bot()
        # Мокаем message_id для сохранения в БД (строка 337)
        msg.answer.return_value.message_id = 999

        await cmd_start(msg, db=db_manager, bot=bot)

        # from_user=None → uid="unknown" → нет пациентов → приветствие
        msg.answer.assert_called_once()
        text = msg.answer.call_args[0][0]
        assert "У тебя пока нет добавленных пациентов" in text


# ── T1.2.2: back_to_main ──────────────────────────────────────────────


class TestBackToMain:
    """Callback back_to_main."""

    async def test_no_patients_shows_welcome(self, db_manager):
        """Нет пациентов — приветствие."""
        from src.handlers.common import back_to_main

        call = make_callback("back_to_main")
        await back_to_main(call, db=db_manager)

        call.message.edit_text.assert_called_once()
        text = call.message.edit_text.call_args[0][0]
        assert "У тебя пока нет добавленных пациентов" in text

    async def test_with_patients_shows_list(self, db_manager):
        """Есть пациенты — список."""
        from src.handlers.common import back_to_main

        await db_manager.add_patient(
            str(TEST_USER_ID),
            "111",
            {"fio": "Иванов Иван Иванович", "bday": "1990-01-01", "alias": None},
        )
        call = make_callback("back_to_main")
        await back_to_main(call, db=db_manager)

        call.message.edit_text.assert_called_once()
        text = call.message.edit_text.call_args[0][0]
        assert "Ваши пациенты" in text


# ── T1.2.3: select_patient ────────────────────────────────────────────


class TestSelectPatient:
    """Выбор пациента → показываем города."""

    async def test_select_patient_shows_cities(self, db_manager):
        """После выбора пациента — сообщение с городами."""
        from src.handlers.common import select_patient

        await _seed_clinic(db_manager, "101", "Поликлиника Всеволожск")
        await _seed_clinic(db_manager, "102", "Поликлиника Мурино")

        await db_manager.add_patient(
            str(TEST_USER_ID),
            "111",
            {"fio": "Иванов Иван Иванович", "bday": "1990-01-01", "alias": None},
        )
        call = make_callback("sel_p_111")
        await select_patient(call, db=db_manager)

        call.message.edit_text.assert_called_once()
        text = call.message.edit_text.call_args[0][0]
        assert "город" in text
        assert "reply_markup" in call.message.edit_text.call_args[1]

    async def test_no_from_user_returns_early(self, db_manager):
        """Нет from_user — выход."""
        from src.handlers.common import select_patient

        call = make_callback("sel_p_111")
        object.__setattr__(call, "from_user", None)

        await select_patient(call, db=db_manager)

        call.message.edit_text.assert_not_called()


# ── T1.2.4: select_city ────────────────────────────────────────────────


class TestSelectCity:
    """Выбор города → список клиник."""

    async def test_select_city_shows_clinics(self, db_manager):
        """Выбор города — список клиник этого города."""
        from src.handlers.common import select_city

        await _seed_clinic(db_manager, "201", "Поликлиника Мурино")
        await _seed_clinic(db_manager, "202", "Детская Мурино")

        await db_manager.add_patient(
            str(TEST_USER_ID),
            "111",
            {"fio": "Иванов Иван Иванович", "bday": "1990-01-01", "alias": None},
        )
        call = make_callback("sel_cty_111_1")
        await select_city(call, db=db_manager)

        call.message.edit_text.assert_called_once()
        assert "reply_markup" in call.message.edit_text.call_args[1]

    async def test_select_all_cities(self, db_manager):
        """Выбор 'Все клиники' (idx = all)."""
        from src.handlers.common import select_city

        await _seed_clinic(db_manager, "201", "Поликлиника Мурино")
        await db_manager.add_patient(
            str(TEST_USER_ID),
            "111",
            {"fio": "Иванов Иван Иванович", "bday": "1990-01-01", "alias": None},
        )
        call = make_callback("sel_cty_111_all")
        await select_city(call, db=db_manager)

        call.message.edit_text.assert_called_once()
        text = call.message.edit_text.call_args[0][0]
        assert "Все клиники" in text


# ── T1.2.5: select_clinic ─────────────────────────────────────────────


class TestSelectClinic:
    """Выбор клиники → список врачей."""

    async def test_clinic_with_doctors(self, db_manager):
        """Клиника с врачами в БД — сразу показывается список врачей."""
        from src.handlers.common import select_clinic

        api = make_mock_api()

        await _seed_clinic(db_manager, "301", "Поликлиника тестовая")
        await _seed_doctors(
            db_manager,
            "301",
            [
                {"id": "d1", "name": "Иванов И.И.", "specialty": "Терапевт"},
                {"id": "d2", "name": "Петров П.П.", "specialty": "Хирург"},
            ],
        )
        await db_manager.add_patient(
            str(TEST_USER_ID),
            "111",
            {"fio": "Тестов Тест Тестович", "bday": "2000-01-01", "alias": None},
        )

        call = make_callback("sel_c_111_301_all")
        await select_clinic(call, db=db_manager, api=api)

        call.message.edit_text.assert_called_once()
        text = call.message.edit_text.call_args[0][0]
        assert "врачей" in text
        assert "reply_markup" in call.message.edit_text.call_args[1]
        # API не вызывался (врачи уже есть в БД)
        api.fetch_all_doctors.assert_not_called()

    async def test_clinic_empty_triggers_discovery(self, db_manager):
        """Клиника без врачей — on-demand discovery."""
        from src.handlers.common import select_clinic

        api = make_mock_api()
        api.fetch_speciality_list = AsyncMock(
            return_value=[{"IdSpesiality": "10", "NameSpesiality": "Терапевт"}]
        )
        api.fetch_all_doctors = AsyncMock(
            return_value=[{"Id": 1, "Name": "Сидоров С.С.", "SpesialityName": ""}]
        )

        await _seed_clinic(db_manager, "302", "Поликлиника без врачей")
        await db_manager.add_patient(
            str(TEST_USER_ID),
            "111",
            {"fio": "Тестов Тест Тестович", "bday": "2000-01-01", "alias": None},
        )

        call = make_callback("sel_c_111_302_all")
        await select_clinic(call, db=db_manager, api=api)

        # Discovery вызывался
        api.fetch_speciality_list.assert_called_once()
        api.fetch_all_doctors.assert_called_once()
        # Сообщение с врачами
        call.message.edit_text.assert_called_once()


# ── T1.2.6: toggle_doctor ─────────────────────────────────────────────


class TestToggleDoctor:
    """Включение / отключение мониторинга врача."""

    async def test_enable_monitoring(self, db_manager):
        """Включение мониторинга — check_slots вызван, сообщение сохранено."""
        from src.handlers.common import toggle_doctor

        api = make_mock_api()
        api.check_slots = AsyncMock(
            return_value=["01.06.2026 10:00", "01.06.2026 11:00"]
        )
        bot = make_mock_bot()

        await _seed_clinic(db_manager, "401", "Тестовая клиника")
        await _seed_doctors(
            db_manager,
            "401",
            [{"id": "d1", "name": "Иванов И.И.", "specialty": "Терапевт"}],
        )
        await db_manager.add_patient(
            str(TEST_USER_ID),
            "111",
            {"fio": "Тестов Тест Тестович", "bday": "2000-01-01", "alias": None},
        )

        call = make_callback("tgl_111_401_d1")

        # call.message.answer вызывается для "загрузочного" сообщения,
        # результат используется для edit_text и сохранения message_id в БД.
        # Чтобы не сломать SQLite, loading_msg должен иметь int .message_id.
        loading_msg_mock = AsyncMock()
        loading_msg_mock.message_id = 99999
        loading_msg_mock.edit_text = AsyncMock()
        call.message.answer.return_value = loading_msg_mock

        await toggle_doctor(call, db=db_manager, api=api, bot=bot)

        # call.answer был вызван
        call.answer.assert_called()

        # API check_slots вызван с нужными параметрами
        api.check_slots.assert_called_once_with("d1", "111", "401")

        # Мониторинг активирован
        user_data = await db_manager.get_user_data(str(TEST_USER_ID))
        assert "111" in user_data["monitoring"]
        assert "d1" in user_data["monitoring"]["111"]

    async def test_enable_no_slots(self, db_manager):
        """Включение мониторинга — слотов нет."""
        from src.handlers.common import toggle_doctor

        api = make_mock_api()
        api.check_slots = AsyncMock(return_value=[])
        bot = make_mock_bot()

        await _seed_clinic(db_manager, "402", "Тестовая клиника 2")
        await _seed_doctors(
            db_manager,
            "402",
            [{"id": "d1", "name": "Петров П.П.", "specialty": "Хирург"}],
        )
        await db_manager.add_patient(
            str(TEST_USER_ID),
            "111",
            {"fio": "Тестов Тест Тестович", "bday": "2000-01-01", "alias": None},
        )

        call = make_callback("tgl_111_402_d1")

        # Подменяем возврат call.message.answer
        loading_msg_mock = AsyncMock()
        loading_msg_mock.message_id = 99998
        loading_msg_mock.edit_text = AsyncMock()
        call.message.answer.return_value = loading_msg_mock

        await toggle_doctor(call, db=db_manager, api=api, bot=bot)

        # Мониторинг активирован даже если слотов нет
        user_data = await db_manager.get_user_data(str(TEST_USER_ID))
        assert "d1" in user_data["monitoring"]["111"]

    async def test_disable_monitoring(self, db_manager):
        """Отключение мониторинга — врач удалён из monitoring."""
        from src.handlers.common import toggle_doctor

        api = make_mock_api()
        api.check_slots = AsyncMock()
        bot = make_mock_bot()

        await _seed_clinic(db_manager, "403", "Тестовая клиника 3")
        await _seed_doctors(
            db_manager,
            "403",
            [{"id": "d1", "name": "Сидоров С.С.", "specialty": "Терапевт"}],
        )
        await db_manager.add_patient(
            str(TEST_USER_ID),
            "111",
            {"fio": "Тестов Тест Тестович", "bday": "2000-01-01", "alias": None},
        )

        # Предварительно включаем мониторинг
        await db_manager.toggle_monitoring(
            str(TEST_USER_ID), "111", "d1", "Сидоров С.С.", "403", "Терапевт"
        )

        call = make_callback("tgl_111_403_d1")
        await toggle_doctor(call, db=db_manager, api=api, bot=bot)

        # Мониторинг отключён — ключ пациента удалён из monitoring полностью
        user_data = await db_manager.get_user_data(str(TEST_USER_ID))
        assert "111" not in user_data["monitoring"]

        # При отключении send_photo вызван (call.answer — нет, он только в enable-пути)
        bot.send_photo.assert_called()


# ── T1.2.7: handle_noop ───────────────────────────────────────────────


class TestHandleNoop:
    """Заглушка для кнопки-разделителя."""

    async def test_noop_answers(self):
        """noop callback — вызывается answer()."""
        from src.handlers.common import handle_noop

        call = make_callback("noop")
        await handle_noop(call)

        call.answer.assert_called_once()


# ── T1.2.8: stop_all_monitoring ───────────────────────────────────────


class TestStopAllMonitoring:
    """Сброс всего мониторинга."""

    async def test_stop_all_clears_monitoring(self, db_manager):
        """Stop all — весь мониторинг очищен, сообщение обновлено."""
        from src.handlers.common import stop_all_monitoring

        bot = make_mock_bot()

        await db_manager.add_patient(
            str(TEST_USER_ID),
            "111",
            {"fio": "Тестов Тест Тестович", "bday": "2000-01-01", "alias": None},
        )
        await db_manager.toggle_monitoring(
            str(TEST_USER_ID), "111", "d1", "Врач 1", "500", "Терапевт"
        )
        await db_manager.toggle_monitoring(
            str(TEST_USER_ID), "111", "d2", "Врач 2", "500", "Хирург"
        )

        call = make_callback("stop_all")
        await stop_all_monitoring(call, db=db_manager, bot=bot)

        user_data = await db_manager.get_user_data(str(TEST_USER_ID))
        assert user_data["monitoring"] == {}
        bot.send_photo.assert_called_once()
        caption = bot.send_photo.call_args[1]["caption"]
        assert "✅" in caption


# ── T1.2.9: back_to_cities ────────────────────────────────────────────


class TestBackToCities:
    """Возврат к выбору города."""

    async def test_back_to_cities_shows_cities(self, db_manager):
        """Кнопка назад → список городов."""
        from src.handlers.common import back_to_cities

        await _seed_clinic(db_manager, "601", "Тестовая")
        await db_manager.add_patient(
            str(TEST_USER_ID),
            "111",
            {"fio": "Тестов Тест Тестович", "bday": "2000-01-01", "alias": None},
        )
        call = make_callback("back_to_cities_111")
        await back_to_cities(call, db=db_manager)

        call.message.edit_text.assert_called_once()
        text = call.message.edit_text.call_args[0][0]
        assert "город" in text
        assert "reply_markup" in call.message.edit_text.call_args[1]


# ── T1.2.10: back_to_clinics ───────────────────────────────────────────


class TestBackToClinics:
    """Возврат к списку клиник."""

    async def test_back_to_clinics_shows_clinics(self, db_manager):
        """Кнопка назад — список клиник."""
        from src.handlers.common import back_to_clinics

        await _seed_clinic(db_manager, "701", "Тестовая клиника")
        await db_manager.add_patient(
            str(TEST_USER_ID),
            "111",
            {"fio": "Тестов Тест Тестович", "bday": "2000-01-01", "alias": None},
        )
        call = make_callback("back_to_clinics_111_1")
        await back_to_clinics(call, db=db_manager)

        call.message.edit_text.assert_called_once()
        assert "reply_markup" in call.message.edit_text.call_args[1]


# ── T1.2.11: stop_patient_monitoring ──────────────────────────────────


class TestStopPatientMonitoring:
    """Сброс мониторинга конкретного пациента."""

    async def test_stop_patient_city_context(self, db_manager):
        """Сброс в контексте городов."""
        from src.handlers.common import stop_patient_monitoring

        bot = make_mock_bot()

        await _seed_clinic(db_manager, "801", "Тестовая")
        await db_manager.add_patient(
            str(TEST_USER_ID),
            "111",
            {"fio": "Тестов Тест Тестович", "bday": "2000-01-01", "alias": None},
        )
        await db_manager.toggle_monitoring(
            str(TEST_USER_ID), "111", "d1", "Врач 1", "801", "Терапевт"
        )

        call = make_callback("stop_patient_111_city_all")
        await stop_patient_monitoring(call, db=db_manager, bot=bot)

        user_data = await db_manager.get_user_data(str(TEST_USER_ID))
        assert "111" not in user_data["monitoring"]
        bot.send_photo.assert_called_once()
        caption = bot.send_photo.call_args[1]["caption"]
        assert "✅" in caption

    async def test_stop_patient_clinic_context(self, db_manager):
        """Сброс в контексте клиник."""
        from src.handlers.common import stop_patient_monitoring

        bot = make_mock_bot()

        await _seed_clinic(db_manager, "802", "Тестовая 2")
        await db_manager.add_patient(
            str(TEST_USER_ID),
            "222",
            {"fio": "Тестов Тест Тестович", "bday": "2000-01-01", "alias": None},
        )
        await db_manager.toggle_monitoring(
            str(TEST_USER_ID), "222", "d1", "Врач 1", "802", "Терапевт"
        )

        call = make_callback("stop_patient_222_clinic_1")
        await stop_patient_monitoring(call, db=db_manager, bot=bot)

        user_data = await db_manager.get_user_data(str(TEST_USER_ID))
        assert "222" not in user_data["monitoring"]
        bot.send_photo.assert_called_once()


# ── T1.2.12: stop_clinic_monitoring ───────────────────────────────────


class TestStopClinicMonitoring:
    """Сброс мониторинга для конкретной клиники."""

    async def test_stop_clinic_removes_clinic_doctors(self, db_manager):
        """Сброс клиники — только врачи этой клиники удалены."""
        from src.handlers.common import stop_clinic_monitoring

        bot = make_mock_bot()

        await _seed_clinic(db_manager, "901", "Клиника A")
        await _seed_clinic(db_manager, "902", "Клиника B")
        await _seed_doctors(
            db_manager,
            "901",
            [
                {"id": "d1", "name": "Врач A1", "specialty": "Терапевт"},
                {"id": "d2", "name": "Врач A2", "specialty": "Хирург"},
            ],
        )
        await _seed_doctors(
            db_manager,
            "902",
            [{"id": "d3", "name": "Врач B1", "specialty": "Терапевт"}],
        )
        await db_manager.add_patient(
            str(TEST_USER_ID),
            "111",
            {"fio": "Тестов Тест Тестович", "bday": "2000-01-01", "alias": None},
        )
        await db_manager.toggle_monitoring(
            str(TEST_USER_ID), "111", "d1", "Врач A1", "901", "Терапевт"
        )
        await db_manager.toggle_monitoring(
            str(TEST_USER_ID), "111", "d2", "Врач A2", "901", "Хирург"
        )
        await db_manager.toggle_monitoring(
            str(TEST_USER_ID), "111", "d3", "Врач B1", "902", "Терапевт"
        )

        call = make_callback("stop_clinic_111_901")
        await stop_clinic_monitoring(call, db=db_manager, bot=bot)

        user_data = await db_manager.get_user_data(str(TEST_USER_ID))
        monitoring = user_data["monitoring"].get("111", {})
        # Врачи клиники 901 удалены, клиники 902 — остались
        assert "d1" not in monitoring
        assert "d2" not in monitoring
        assert "d3" in monitoring


# ── T1.2.13: handle_delete_patient ────────────────────────────────────


class TestHandleDeletePatient:
    """Удаление пациента."""

    async def test_delete_ask_shows_confirmation(self, db_manager):
        """del_p_ask — диалог подтверждения."""
        from src.handlers.common import handle_delete_patient

        await db_manager.add_patient(
            str(TEST_USER_ID),
            "111",
            {"fio": "Тестов Тест Тестович", "bday": "2000-01-01", "alias": None},
        )
        call = make_callback("del_p_ask_111")
        await handle_delete_patient(call, db=db_manager)

        call.message.edit_text.assert_called_once()
        text = call.message.edit_text.call_args[0][0]
        assert "уверены" in text.lower()

    async def test_delete_yes_with_other_patients(self, db_manager):
        """del_p_yes + есть другие пациенты — возврат к списку."""
        from src.handlers.common import handle_delete_patient

        await db_manager.add_patient(
            str(TEST_USER_ID),
            "111",
            {"fio": "Пациент 1", "bday": "2000-01-01", "alias": None},
        )
        await db_manager.add_patient(
            str(TEST_USER_ID),
            "222",
            {"fio": "Пациент 2", "bday": "1995-05-05", "alias": None},
        )
        call = make_callback("del_p_yes_111")
        # handler проверяет call.bot is None → return
        # call.bot — property на _bot; задаём внутреннее поле
        mock_bot = make_mock_bot()
        object.__setattr__(call, "_bot", mock_bot)

        await handle_delete_patient(call, db=db_manager)

        # Пациент 111 удалён
        user_data = await db_manager.get_user_data(str(TEST_USER_ID))
        assert "111" not in user_data["patients"]
        assert "222" in user_data["patients"]
        mock_bot.send_photo.assert_called_once()

    async def test_delete_yes_last_patient_shows_welcome(self, db_manager):
        """del_p_yes + это последний пациент — приветствие."""
        from src.handlers.common import handle_delete_patient

        await db_manager.add_patient(
            str(TEST_USER_ID),
            "111",
            {"fio": "Пациент 1", "bday": "2000-01-01", "alias": None},
        )
        call = make_callback("del_p_yes_111")
        mock_bot = make_mock_bot()
        object.__setattr__(call, "_bot", mock_bot)

        await handle_delete_patient(call, db=db_manager)

        user_data = await db_manager.get_user_data(str(TEST_USER_ID))
        assert "111" not in user_data["patients"]
        mock_bot.send_photo.assert_called_once()
        caption = mock_bot.send_photo.call_args[1]["caption"]
        assert "Привет" in caption

    async def test_delete_yes_no_bot_returns_early(self, db_manager):
        """del_p_yes без bot — ранний возврат, пациент не удалён."""
        from src.handlers.common import handle_delete_patient

        await db_manager.add_patient(
            str(TEST_USER_ID),
            "111",
            {"fio": "Пациент 1", "bday": "2000-01-01", "alias": None},
        )
        call = make_callback("del_p_yes_111")
        # call.bot = None (значение по умолчанию в make_callback)

        await handle_delete_patient(call, db=db_manager)

        # Пациент НЕ удалён (ранний возврат из-за call.bot is None)
        user_data = await db_manager.get_user_data(str(TEST_USER_ID))
        assert "111" in user_data["patients"]
