"""
Тесты для services/doctor_discovery.py.
"""

from unittest.mock import AsyncMock, MagicMock


from services.doctor_discovery import (
    _get_clinic_type_from_db,
    fetch_specialties,
    sync_clinic_names,
)

# ── Вспомогательные фикстуры ────────────────────────────────────────────────


def _make_mock_api():
    """Создаёт мок ZdravClient."""
    api = MagicMock()
    api.fetch_speciality_list = AsyncMock()
    api.fetch_all_doctors = AsyncMock()
    api.fetch_clinic_list = AsyncMock()
    return api


def _make_mock_db():
    """Создаёт мок Database."""
    db = MagicMock()
    db.get_clinic_type = AsyncMock()
    db.get_clinic_discovery_patients = AsyncMock(return_value=("", ""))
    db.upsert_clinic = AsyncMock()
    return db


def _make_mock_doctor_manager(mock_db):
    """Создаёт мок DoctorManager."""
    mgr = MagicMock()
    mgr._db = mock_db
    mgr.merge_doctors = AsyncMock()
    return mgr


# ── fetch_specialties ───────────────────────────────────────────────────────


class TestFetchSpecialties:
    """Тесты для fetch_specialties."""

    async def test_success_returns_parsed_list(self):
        """Успешный ответ API — возвращает отфильтрованный список специальностей."""
        api = _make_mock_api()
        api.fetch_speciality_list.return_value = [
            {"IdSpesiality": 1, "NameSpesiality": "Хирургия"},
            {"IdSpesiality": 2, "NameSpesiality": "Терапия"},
        ]

        result = await fetch_specialties(api, "p123", "272")
        assert len(result) == 2
        assert result[0] == {"IdSpesiality": "1", "NameSpesiality": "Хирургия"}
        assert result[1] == {"IdSpesiality": "2", "NameSpesiality": "Терапия"}
        api.fetch_speciality_list.assert_called_once_with("p123", "272", limiter=None)

    async def test_empty_api_response_returns_empty_list(self):
        """Пустой ответ API — возвращает []."""
        api = _make_mock_api()
        api.fetch_speciality_list.return_value = []

        result = await fetch_specialties(api, "p123", "272")
        assert result == []

    async def test_api_exception_returns_empty_list(self):
        """Исключение API — возвращает [] (не пробрасывает исключение)."""
        api = _make_mock_api()
        api.fetch_speciality_list.side_effect = Exception("Connection error")

        result = await fetch_specialties(api, "p123", "272")
        assert result == []

    async def test_filters_missing_idspesiality(self):
        """Записи без IdSpesiality отфильтровываются."""
        api = _make_mock_api()
        api.fetch_speciality_list.return_value = [
            {"IdSpesiality": None, "NameSpesiality": "Без ID"},
            {"IdSpesiality": 1, "NameSpesiality": "Хирургия"},
            {"IdSpesiality": "", "NameSpesiality": "Пустой ID"},
        ]

        result = await fetch_specialties(api, "p123", "272")
        assert len(result) == 1
        assert result[0]["NameSpesiality"] == "Хирургия"

    async def test_filters_missing_namespesiality(self):
        """Записи без NameSpesiality отфильтровываются."""
        api = _make_mock_api()
        api.fetch_speciality_list.return_value = [
            {"IdSpesiality": 1, "NameSpesiality": None},
            {"IdSpesiality": 2, "NameSpesiality": ""},
            {"IdSpesiality": 3, "NameSpesiality": "Хирургия"},
        ]

        result = await fetch_specialties(api, "p123", "272")
        assert len(result) == 1
        assert result[0]["NameSpesiality"] == "Хирургия"

    async def test_converts_non_string_values_to_string(self):
        """Числовые значения приводятся к строке."""
        api = _make_mock_api()
        api.fetch_speciality_list.return_value = [
            {"IdSpesiality": 42, "NameSpesiality": 12345},
        ]

        result = await fetch_specialties(api, "p123", "272")
        assert len(result) == 1
        assert result[0]["IdSpesiality"] == "42"
        assert result[0]["NameSpesiality"] == "12345"
        assert isinstance(result[0]["IdSpesiality"], str)
        assert isinstance(result[0]["NameSpesiality"], str)


# ── _get_clinic_type_from_db ────────────────────────────────────────────────


class TestGetClinicTypeFromDb:
    """Тесты для _get_clinic_type_from_db."""

    async def test_returns_type_when_found(self):
        """Возвращает тип из БД, когда он найден."""
        db = _make_mock_db()
        db.get_clinic_type.return_value = "child"

        result = await _get_clinic_type_from_db(db, "272")
        assert result == "child"
        db.get_clinic_type.assert_called_once_with("272")

    async def test_returns_adult_when_none(self):
        """Возвращает 'adult', когда БД возвращает None/пусто."""
        db = _make_mock_db()
        db.get_clinic_type.return_value = None

        result = await _get_clinic_type_from_db(db, "272")
        assert result == "adult"

    async def test_returns_adult_when_empty_string(self):
        """Возвращает 'adult', когда БД возвращает пустую строку."""
        db = _make_mock_db()
        db.get_clinic_type.return_value = ""

        result = await _get_clinic_type_from_db(db, "272")
        assert result == "adult"

    async def test_returns_adult_on_exception(self):
        """Возвращает 'adult' при исключении из БД."""
        db = _make_mock_db()
        db.get_clinic_type.side_effect = Exception("DB error")

        result = await _get_clinic_type_from_db(db, "272")
        assert result == "adult"


# ── discovery_loop: логика выбора patient_id ────────────────────────────────


class TestDiscoveryPatientSelection:
    """
    Тесты логики выбора patient_id внутри discovery_loop
    (без запуска бесконечного цикла).
    """

    async def test_adult_clinic_uses_only_adult_patient(self):
        """Для adult-клиники в patient_ids попадает только adult ID."""
        _make_mock_api()
        db = _make_mock_db()
        db.get_clinic_type.return_value = "adult"
        db.get_clinic_discovery_patients.return_value = ("", "")

        clinic_type = await _get_clinic_type_from_db(db, "272")
        assert clinic_type == "adult"

        (
            clinic_patient_adult,
            clinic_patient_child,
        ) = await db.get_clinic_discovery_patients("272")

        adult_pid = "ADULT_GLOBAL"
        child_pid = "CHILD_GLOBAL"

        # Логика из discovery_loop:
        if clinic_type == "child":
            patient_ids = [clinic_patient_child or child_pid]
        elif clinic_type == "all":
            patient_ids = [
                clinic_patient_adult or adult_pid,
                clinic_patient_child or child_pid,
            ]
        else:  # adult
            patient_ids = [clinic_patient_adult or adult_pid]

        assert patient_ids == ["ADULT_GLOBAL"]
        assert len(patient_ids) == 1

    async def test_child_clinic_uses_only_child_patient(self):
        """Для child-клиники в patient_ids попадает только child ID."""
        db = _make_mock_db()
        db.get_clinic_type.return_value = "child"
        db.get_clinic_discovery_patients.return_value = ("", "")

        clinic_type = await _get_clinic_type_from_db(db, "272")
        assert clinic_type == "child"

        (
            clinic_patient_adult,
            clinic_patient_child,
        ) = await db.get_clinic_discovery_patients("272")

        adult_pid = "ADULT_GLOBAL"
        child_pid = "CHILD_GLOBAL"

        if clinic_type == "child":
            patient_ids = [clinic_patient_child or child_pid]
        elif clinic_type == "all":
            patient_ids = [
                clinic_patient_adult or adult_pid,
                clinic_patient_child or child_pid,
            ]
        else:
            patient_ids = [clinic_patient_adult or adult_pid]

        assert patient_ids == ["CHILD_GLOBAL"]
        assert len(patient_ids) == 1

    async def test_all_clinic_uses_both_patients(self):
        """Для all-клиники используются оба patient_id."""
        db = _make_mock_db()
        db.get_clinic_type.return_value = "all"
        db.get_clinic_discovery_patients.return_value = ("", "")

        clinic_type = await _get_clinic_type_from_db(db, "272")
        assert clinic_type == "all"

        (
            clinic_patient_adult,
            clinic_patient_child,
        ) = await db.get_clinic_discovery_patients("272")

        adult_pid = "ADULT_GLOBAL"
        child_pid = "CHILD_GLOBAL"

        if clinic_type == "child":
            patient_ids = [clinic_patient_child or child_pid]
        elif clinic_type == "all":
            patient_ids = [
                clinic_patient_adult or adult_pid,
                clinic_patient_child or child_pid,
            ]
        else:
            patient_ids = [clinic_patient_adult or adult_pid]

        assert patient_ids == ["ADULT_GLOBAL", "CHILD_GLOBAL"]
        assert len(patient_ids) == 2

    async def test_per_clinic_patient_overrides_global(self):
        """Per-клиника patient_id из БД имеет приоритет над глобальным."""
        db = _make_mock_db()
        db.get_clinic_type.return_value = "adult"
        db.get_clinic_discovery_patients.return_value = ("CLINIC_ADULT", "")

        clinic_type = await _get_clinic_type_from_db(db, "272")
        (
            clinic_patient_adult,
            clinic_patient_child,
        ) = await db.get_clinic_discovery_patients("272")

        adult_pid = "GLOBAL_ADULT"
        child_pid = "GLOBAL_CHILD"

        # Логика: clinic_patient or global_patient
        if clinic_type == "child":
            patient_ids = [clinic_patient_child or child_pid]
        elif clinic_type == "all":
            patient_ids = [
                clinic_patient_adult or adult_pid,
                clinic_patient_child or child_pid,
            ]
        else:
            patient_ids = [clinic_patient_adult or adult_pid]

        assert patient_ids == ["CLINIC_ADULT"]
        assert "GLOBAL_ADULT" not in patient_ids

    async def test_all_clinic_per_clinic_overrides_both(self):
        """Для all-клиники per-клиника пациенты переопределяют оба ID."""
        db = _make_mock_db()
        db.get_clinic_type.return_value = "all"
        db.get_clinic_discovery_patients.return_value = (
            "CLINIC_ADULT",
            "CLINIC_CHILD",
        )

        clinic_type = await _get_clinic_type_from_db(db, "272")
        (
            clinic_patient_adult,
            clinic_patient_child,
        ) = await db.get_clinic_discovery_patients("272")

        adult_pid = "GLOBAL_ADULT"
        child_pid = "GLOBAL_CHILD"

        if clinic_type == "child":
            patient_ids = [clinic_patient_child or child_pid]
        elif clinic_type == "all":
            patient_ids = [
                clinic_patient_adult or adult_pid,
                clinic_patient_child or child_pid,
            ]
        else:
            patient_ids = [clinic_patient_adult or adult_pid]

        assert patient_ids == ["CLINIC_ADULT", "CLINIC_CHILD"]


# ── sync_clinic_names ───────────────────────────────────────────────────────


class TestSyncClinicNames:
    """Тесты для sync_clinic_names."""

    async def test_syncs_clinics_successfully(self):
        """Успешная синхронизация названий клиник."""
        api = _make_mock_api()
        api.fetch_clinic_list.return_value = [
            {"IdLPU": "272", "LpuName": "Поликлиника №1"},
            {"IdLPU": "271", "LpuName": "Поликлиника №2"},
        ]
        db = _make_mock_db()

        await sync_clinic_names(api, db)

        assert db.upsert_clinic.call_count == 2
        db.upsert_clinic.assert_any_call("272", "Поликлиника №1")
        db.upsert_clinic.assert_any_call("271", "Поликлиника №2")

    async def test_handles_empty_clinic_list(self):
        """Пустой список клиник — upsert_clinic не вызывается."""
        api = _make_mock_api()
        api.fetch_clinic_list.return_value = []
        db = _make_mock_db()

        await sync_clinic_names(api, db)

        db.upsert_clinic.assert_not_called()

    async def test_handles_none_clinic_list(self):
        """None вместо списка — upsert_clinic не вызывается."""
        api = _make_mock_api()
        api.fetch_clinic_list.return_value = None
        db = _make_mock_db()

        await sync_clinic_names(api, db)

        db.upsert_clinic.assert_not_called()

    async def test_handles_api_exception(self):
        """Исключение API — не пробрасывается наружу."""
        api = _make_mock_api()
        api.fetch_clinic_list.side_effect = Exception("Network error")
        db = _make_mock_db()

        await sync_clinic_names(api, db)
        db.upsert_clinic.assert_not_called()

    async def test_uses_lpu_short_name_fallback(self):
        """Если LpuName отсутствует, используется LPUShortName."""
        api = _make_mock_api()
        api.fetch_clinic_list.return_value = [
            {"IdLPU": "272", "LPUShortName": "Короткое название"},
        ]
        db = _make_mock_db()

        await sync_clinic_names(api, db)

        db.upsert_clinic.assert_called_once_with("272", "Короткое название")

    async def test_skips_missing_clinic_id(self):
        """Записи без IdLPU пропускаются."""
        api = _make_mock_api()
        api.fetch_clinic_list.return_value = [
            {"IdLPU": None, "LpuName": "Без ID"},
            {"IdLPU": "", "LpuName": "Пустой ID"},
            {"IdLPU": "272", "LpuName": "Поликлиника №1"},
        ]
        db = _make_mock_db()

        await sync_clinic_names(api, db)

        db.upsert_clinic.assert_called_once_with("272", "Поликлиника №1")

    async def test_skips_missing_clinic_name(self):
        """Записи без имени (и LpuName, и LPUShortName) пропускаются."""
        api = _make_mock_api()
        api.fetch_clinic_list.return_value = [
            {"IdLPU": "272", "LpuName": None, "LPUShortName": None},
            {"IdLPU": "271", "LpuName": "", "LPUShortName": ""},
        ]
        db = _make_mock_db()

        await sync_clinic_names(api, db)

        db.upsert_clinic.assert_not_called()

    async def test_converts_clinic_id_to_string(self):
        """Числовой clinic_id приводится к строке."""
        api = _make_mock_api()
        api.fetch_clinic_list.return_value = [
            {"IdLPU": 272, "LpuName": "Поликлиника №1"},
        ]
        db = _make_mock_db()

        await sync_clinic_names(api, db)

        db.upsert_clinic.assert_called_once_with("272", "Поликлиника №1")
