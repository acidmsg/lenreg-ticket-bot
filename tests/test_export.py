"""
Тесты для сервиса экспорта данных мониторинга.

Использует временную SQLite БД (через conftest) и проверяет
корректность генерации CSV и JSON файлов.
"""

import csv
import json
import time
from pathlib import Path

import pytest
from src.services.export import export_monitoring_csv, export_monitoring_json


@pytest.mark.asyncio
async def test_export_csv_with_data(db_manager):
    """Тест экспорта CSV с данными мониторинга."""
    uid = "12345"
    p_id = "67890"
    d_id = "11111"

    # Добавляем пациента
    await db_manager.add_patient(
        uid,
        p_id,
        {"fio": "Иванов Иван Иванович", "bday": "1990-01-01"},
    )

    # Добавляем мониторинг
    await db_manager.toggle_monitoring(
        uid,
        p_id,
        d_id,
        "Петров Пётр",
        "123",
        "Терапевт",
    )

    # Добавляем запись в лог
    await db_manager.add_monitoring_log(
        uid=uid,
        p_id=p_id,
        d_id=d_id,
        doctor_name="Петров Пётр",
        patient_name="Иванов Иван Иванович",
        specialty="Терапевт",
        clinic_name="Поликлиника №1",
        slot_date="2025-06-15 10:00",
        status="появился",
        ts=time.time(),
    )

    filepath = await export_monitoring_csv(db_manager, int(uid))
    assert filepath is not None
    assert filepath.endswith(".csv")

    try:
        # Читаем CSV и проверяем структуру
        with open(filepath, newline="", encoding="utf-8-sig") as f:  # noqa: ASYNC230
            reader = csv.reader(f)
            rows = list(reader)

        # Проверяем заголовки
        assert len(rows) >= 1
        assert rows[0] == [
            "Пациент (ФИО)",
            "Специальность",
            "Врач",
            "Клиника",
            "Дата/время слота",
            "Статус",
            "Временная метка",
        ]

        # Проверяем наличие данных
        assert len(rows) >= 2
        data_row = rows[1]
        assert "Иванов Иван Иванович" in data_row[0]
        assert "Терапевт" in data_row[1]
        assert "Петров Пётр" in data_row[2]
        assert "Поликлиника №1" in data_row[3]
        assert "появился" in data_row[5]
    finally:
        Path(filepath).unlink(missing_ok=True)  # noqa: ASYNC240


@pytest.mark.asyncio
async def test_export_json_with_data(db_manager):
    """Тест экспорта JSON с данными мониторинга."""
    uid = "12345"
    p_id = "67890"
    d_id = "11111"

    await db_manager.add_patient(
        uid,
        p_id,
        {"fio": "Иванов Иван Иванович", "bday": "1990-01-01"},
    )

    await db_manager.toggle_monitoring(
        uid,
        p_id,
        d_id,
        "Петров Пётр",
        "123",
        "Терапевт",
    )

    await db_manager.add_monitoring_log(
        uid=uid,
        p_id=p_id,
        d_id=d_id,
        doctor_name="Петров Пётр",
        patient_name="Иванов Иван Иванович",
        specialty="Терапевт",
        clinic_name="Поликлиника №1",
        slot_date="2025-06-15 10:00",
        status="появился",
        ts=time.time(),
    )

    filepath = await export_monitoring_json(db_manager, int(uid))
    assert filepath is not None
    assert filepath.endswith(".json")

    try:
        with open(filepath, encoding="utf-8") as f:  # noqa: ASYNC230
            data = json.load(f)

        # Проверяем структуру JSON
        assert "user_id" in data
        assert data["user_id"] == 12345
        assert "exported_at" in data
        assert "patients" in data
        assert len(data["patients"]) > 0

        patient = data["patients"][0]
        assert "patient_name" in patient
        assert "doctors" in patient
        assert len(patient["doctors"]) > 0

        doctor = patient["doctors"][0]
        assert doctor["doctor_name"] == "Петров Пётр"
        assert doctor["specialty"] == "Терапевт"
        assert "status" in doctor
        assert "history" in doctor
        assert len(doctor["history"]) > 0

        log_entry = doctor["history"][0]
        assert log_entry["status"] == "появился"
        assert log_entry["slot_date"] == "2025-06-15 10:00"
    finally:
        Path(filepath).unlink(missing_ok=True)  # noqa: ASYNC240


@pytest.mark.asyncio
async def test_export_empty_data(db_manager):
    """Тест экспорта при отсутствии данных."""
    uid = "99999"

    with pytest.raises(ValueError, match="Нет данных для экспорта"):
        await export_monitoring_csv(db_manager, int(uid))

    with pytest.raises(ValueError, match="Нет данных для экспорта"):
        await export_monitoring_json(db_manager, int(uid))


@pytest.mark.asyncio
async def test_export_csv_empty_log(db_manager):
    """Тест экспорта CSV когда есть мониторинг, но нет логов."""
    uid = "12345"
    p_id = "67890"
    d_id = "11111"

    await db_manager.add_patient(
        uid,
        p_id,
        {"fio": "Тестовый Пациент", "bday": "1990-01-01"},
    )

    await db_manager.toggle_monitoring(
        uid,
        p_id,
        d_id,
        "Тестовый Врач",
        "123",
        "Хирург",
    )

    filepath = await export_monitoring_csv(db_manager, int(uid))

    try:
        with open(filepath, newline="", encoding="utf-8-sig") as f:  # noqa: ASYNC230
            reader = csv.reader(f)
            rows = list(reader)

        assert len(rows) >= 2
        assert rows[1][0] == "Тестовый Пациент"
        assert rows[1][1] == "Хирург"
        assert rows[1][2] == "Тестовый Врач"
        assert rows[1][5] == "активен"
    finally:
        Path(filepath).unlink(missing_ok=True)  # noqa: ASYNC240


@pytest.mark.asyncio
async def test_export_json_empty_log(db_manager):
    """Тест экспорта JSON когда есть мониторинг, но нет логов."""
    uid = "12345"
    p_id = "67890"
    d_id = "11111"

    await db_manager.add_patient(
        uid,
        p_id,
        {"fio": "Тестовый Пациент", "bday": "1990-01-01"},
    )

    await db_manager.toggle_monitoring(
        uid,
        p_id,
        d_id,
        "Тестовый Врач",
        "123",
        "Хирург",
    )

    filepath = await export_monitoring_json(db_manager, int(uid))

    try:
        with open(filepath, encoding="utf-8") as f:  # noqa: ASYNC230
            data = json.load(f)

        assert len(data["patients"]) == 1
        patient = data["patients"][0]
        assert patient["patient_name"] == "Тестовый Пациент"
        assert len(patient["doctors"]) == 1
        doctor = patient["doctors"][0]
        assert doctor["doctor_name"] == "Тестовый Врач"
        assert doctor["specialty"] == "Хирург"
        assert doctor["status"] == "активен"
        # Без логов — пустая история
        assert doctor["history"] == []
    finally:
        Path(filepath).unlink(missing_ok=True)  # noqa: ASYNC240


@pytest.mark.asyncio
async def test_export_csv_format_integrity(db_manager):
    """Тест целостности формата CSV: все строки одинаковой длины."""
    uid = "12345"

    # Добавляем несколько пациентов и врачей
    for i in range(3):
        p_id = f"p_{i}"
        d_id = f"d_{i}"
        await db_manager.add_patient(
            uid,
            p_id,
            {"fio": f"Пациент {i}", "bday": "1990-01-01"},
        )
        await db_manager.toggle_monitoring(
            uid,
            p_id,
            d_id,
            f"Врач {i}",
            str(100 + i),
            "Терапевт",
        )

    filepath = await export_monitoring_csv(db_manager, int(uid))

    try:
        with open(filepath, newline="", encoding="utf-8-sig") as f:  # noqa: ASYNC230
            reader = csv.reader(f)
            rows = list(reader)

        # Все строки должны иметь одинаковое количество колонок
        header_len = len(rows[0])
        for row in rows[1:]:
            assert len(row) == header_len, (
                f"Строка {row} имеет {len(row)} колонок, ожидалось {header_len}"
            )
    finally:
        Path(filepath).unlink(missing_ok=True)  # noqa: ASYNC240
