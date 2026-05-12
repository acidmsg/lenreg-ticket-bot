"""
Тесты для DoctorManager (SQLite версия).
"""


class TestDoctorManager:
    """Набор тестов для DoctorManager."""

    async def test_load_empty_when_no_clinics(self, doctor_manager):
        """Загрузка из пустой SQLite даёт пустой словарь."""
        assert doctor_manager.data == {}

    async def test_merge_doctors_creates_clinic(self, doctor_manager):
        """merge_doctors сохраняет врачей в SQLite и обновляет кэш."""
        doctors = [
            {"IdDoc": "d1", "Name": "Иванов Иван", "SpesialityName": "Хирург"},
            {"IdDoc": "d2", "Name": "Петров Петр", "SpesialityName": "Терапевт"},
        ]
        await doctor_manager.merge_doctors("272", doctors)
        # Перезагружаем кэш
        await doctor_manager.load()
        assert "272" in doctor_manager.data
        assert len(doctor_manager.data["272"]["doctors"]) == 2
        assert doctor_manager.data["272"]["doctors"]["d1"]["name"] == "Иванов Иван"
        assert doctor_manager.data["272"]["doctors"]["d2"]["specialty"] == "Терапевт"

    async def test_merge_doctors_updates_existing(self, doctor_manager):
        """merge_doctors обновляет данные для существующей клиники."""
        await doctor_manager.merge_doctors(
            "272",
            [
                {"IdDoc": "d1", "Name": "Старое имя", "SpesialityName": "Хирург"},
            ],
        )
        await doctor_manager.merge_doctors(
            "272",
            [
                {"IdDoc": "d1", "Name": "Новое имя", "SpesialityName": "Хирург"},
            ],
        )
        await doctor_manager.load()
        assert doctor_manager.data["272"]["doctors"]["d1"]["name"] == "Новое имя"

    async def test_merge_doctors_keeps_existing_doctors(self, doctor_manager):
        """merge_doctors не удаляет существующих врачей при добавлении новых."""
        await doctor_manager.merge_doctors(
            "272",
            [
                {"IdDoc": "d1", "Name": "Иванов", "SpesialityName": "Хирург"},
            ],
        )
        await doctor_manager.merge_doctors(
            "272",
            [
                {"IdDoc": "d2", "Name": "Петров", "SpesialityName": "Терапевт"},
            ],
        )
        await doctor_manager.load()
        assert "d1" in doctor_manager.data["272"]["doctors"]
        assert "d2" in doctor_manager.data["272"]["doctors"]

    async def test_merge_doctors_ignores_invalid_entries(self, doctor_manager):
        """merge_doctors игнорирует записи без IdDoc или Name."""
        doctors = [
            {"IdDoc": "", "Name": "Без Id", "SpesialityName": "Хирург"},
            {"IdDoc": "d2", "Name": "", "SpesialityName": "Терапевт"},
            {"Name": "Без IdDoc", "SpesialityName": "Хирург"},
        ]
        await doctor_manager.merge_doctors("272", doctors)
        await doctor_manager.load()
        assert len(doctor_manager.data.get("272", {}).get("doctors", {})) == 0

    async def test_save_persists_data(self, database):
        """Данные сохраняются в SQLite и восстанавливаются."""
        from src.database.doctor_manager import DoctorManager

        mgr1 = DoctorManager(database)
        await mgr1.load()
        await mgr1.merge_doctors(
            "272",
            [
                {"IdDoc": "d1", "Name": "Иванов", "SpesialityName": "Хирург"},
            ],
        )

        # Второй экземпляр с тем же database
        mgr2 = DoctorManager(database)
        await mgr2.load()
        assert "272" in mgr2.data
        assert mgr2.data["272"]["doctors"]["d1"]["name"] == "Иванов"

    async def test_multiple_clinics(self, doctor_manager):
        """merge_doctors корректно работает с несколькими клиниками."""
        await doctor_manager.merge_doctors(
            "272",
            [
                {"IdDoc": "d1", "Name": "Врач 272", "SpesialityName": "Хирург"},
            ],
        )
        await doctor_manager.merge_doctors(
            "271",
            [
                {"IdDoc": "d2", "Name": "Врач 271", "SpesialityName": "Терапевт"},
            ],
        )
        await doctor_manager.load()
        assert len(doctor_manager.data) == 2
        assert doctor_manager.data["272"]["doctors"]["d1"]["name"] == "Врач 272"
        assert doctor_manager.data["271"]["doctors"]["d2"]["name"] == "Врач 271"
