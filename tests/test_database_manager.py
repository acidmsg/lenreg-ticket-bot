"""
Тесты для DatabaseManager (SQLite версия).
"""


class TestDatabaseManager:
    """Набор тестов для DatabaseManager."""

    async def test_load_empty_when_no_db(self, temp_db_path):
        """Загрузка из пустого SQLite-файла даёт пустой кэш."""
        from database.database import Database
        from database.manager import DatabaseManager

        db = Database(temp_db_path)
        await db.connect()
        mgr = DatabaseManager(db)
        await mgr.load()
        assert mgr.data == {}
        await db.close()

    async def test_get_user_data_creates_default(self, db_manager):
        """get_user_data создаёт запись по умолчанию для нового пользователя."""
        data = db_manager.get_user_data("999")
        assert "patients" in data
        assert "monitoring" in data
        assert "last_messages" in data
        assert data["patients"] == {}
        assert data["monitoring"] == {}

    async def test_get_user_data_existing(self, db_manager):
        """get_user_data возвращает существующие данные."""
        await db_manager.update_user("555", {"name": "test"})
        data = db_manager.get_user_data("555")
        assert data["name"] == "test"

    async def test_get_user_data_migrates_last_messages(self, db_manager):
        """Если в данных нет 'last_messages', он добавляется."""
        data = db_manager.get_user_data("111")
        # Новый пользователь всегда получает last_messages
        assert "last_messages" in data

    async def test_update_user(self, db_manager):
        """update_user обновляет данные пользователя."""
        await db_manager.update_user("123", {"name": "test"})
        assert db_manager.data["123"]["name"] == "test"

    async def test_add_patient(self, db_manager):
        """add_patient добавляет пациента."""
        p_info = {
            "fio": "Иванов Иван",
            "bday": "1990-01-01",
            "alias": None,
            "confirmed_clinics": [],
        }
        await db_manager.add_patient("100", "p1", p_info)
        assert db_manager.data["100"]["patients"]["p1"]["fio"] == "Иванов Иван"
        assert db_manager.data["100"]["patients"]["p1"]["confirmed_clinics"] == []

    async def test_add_confirmed_clinic(self, db_manager):
        """add_confirmed_clinic добавляет clinic_id."""
        p_info = {"fio": "Test", "bday": "1990-01-01", "alias": None}
        await db_manager.add_patient("100", "p1", p_info)
        await db_manager.add_confirmed_clinic("100", "p1", 272)
        assert 272 in db_manager.data["100"]["patients"]["p1"]["confirmed_clinics"]

    async def test_add_confirmed_clinic_deduplicates(self, db_manager):
        """add_confirmed_clinic не добавляет дубликаты."""
        p_info = {"fio": "Test", "bday": "1990-01-01", "alias": None}
        await db_manager.add_patient("100", "p1", p_info)
        await db_manager.add_confirmed_clinic("100", "p1", 272)
        await db_manager.add_confirmed_clinic("100", "p1", 272)
        assert db_manager.data["100"]["patients"]["p1"]["confirmed_clinics"] == [272]

    async def test_toggle_monitoring_add(self, db_manager):
        """toggle_monitoring добавляет врача в мониторинг."""
        await db_manager.toggle_monitoring("100", "p1", "d1", "Иванов", "272", "Хирург")
        assert "d1" in db_manager.data["100"]["monitoring"]["p1"]
        assert db_manager.data["100"]["monitoring"]["p1"]["d1"]["name"] == "Иванов"

    async def test_toggle_monitoring_remove(self, db_manager):
        """toggle_monitoring удаляет врача из мониторинга при повторном вызове."""
        await db_manager.toggle_monitoring("100", "p1", "d1", "Иванов", "272", "Хирург")
        await db_manager.toggle_monitoring("100", "p1", "d1", "Иванов", "272", "Хирург")
        assert "d1" not in db_manager.data["100"]["monitoring"]["p1"]

    async def test_stop_all_monitoring(self, db_manager):
        """stop_all_monitoring очищает мониторинг пользователя."""
        await db_manager.toggle_monitoring("100", "p1", "d1", "Иванов", "272", "Хирург")
        await db_manager.stop_all_monitoring("100")
        assert db_manager.data["100"]["monitoring"] == {}

    async def test_delete_patient(self, db_manager):
        """delete_patient удаляет пациента и его мониторинг."""
        await db_manager.add_patient("100", "p1", {"fio": "Test", "bday": "1990-01-01"})
        await db_manager.toggle_monitoring("100", "p1", "d1", "Иванов", "272", "Хирург")
        await db_manager.delete_patient("100", "p1")
        assert "p1" not in db_manager.data["100"]["patients"]
        assert "p1" not in db_manager.data["100"]["monitoring"]

    async def test_last_message_id(self, db_manager):
        """set_last_message_id и get_last_message_id работают корректно."""
        await db_manager.set_last_message_id("100", "p1", "d1", 123)
        msg_id = db_manager.get_last_message_id("100", "p1", "d1")
        assert msg_id == 123

    async def test_get_last_message_id_none(self, db_manager):
        """get_last_message_id возвращает None для несуществующего ключа."""
        msg_id = db_manager.get_last_message_id("999", "p1", "d1")
        assert msg_id is None

    async def test_save_persists_data(self, temp_db_path):
        """Данные сохраняются в SQLite и восстанавливаются."""
        from database.database import Database
        from database.manager import DatabaseManager

        # Первый экземпляр — сохраняем данные
        db1 = Database(temp_db_path)
        mgr1 = DatabaseManager(db1)
        await mgr1.load()
        await mgr1.update_user("save_test", {"name": "persisted"})
        await db1.close()

        # Второй экземпляр — проверяем что данные на месте
        db2 = Database(temp_db_path)
        mgr2 = DatabaseManager(db2)
        await mgr2.load()
        assert mgr2.data["save_test"]["name"] == "persisted"
        await db2.close()
