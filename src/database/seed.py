"""
Seed-механизм: предзагрузка клиник и врачей из JSON-файла.

Безопасен для многократного запуска — использует INSERT OR IGNORE,
существующие записи не перезаписываются.

Использование:
    from src.database.seed import seed_clinics_and_doctors_from_json

    # Авто-загрузка при старте (если таблица clinics пуста)
    await seed_clinics_and_doctors_from_json(db_conn, "data/seed/clinics_doctors.json")

    # Принудительная перезагрузка (ручной режим)
    await seed_clinics_and_doctors_from_json(
        db_conn, "data/seed/clinics_doctors.json", force=True
    )
"""

from __future__ import annotations

import json

import aiofiles
import aiofiles.os
from loguru import logger


async def seed_clinics_and_doctors_from_json(
    db_conn,
    json_path: str,
    force: bool = False,
) -> tuple[int, int]:
    """
    Загружает клиники и врачей из JSON-файла в БД.

    По умолчанию (``force=False``) загрузка пропускается, если в таблице
    clinics уже есть записи. При ``force=True`` INSERT OR IGNORE выполняется
    в любом случае (для дозагрузки новых записей в непустую таблицу).

    Args:
        db_conn: активное соединение aiosqlite.Connection
        json_path: путь к JSON-файлу с ключами ``clinics`` и ``doctors``
        force: если True — загружать даже при непустой таблице clinics

    Returns:
        (clinics_added, doctors_added) — количество новых записей,
        добавленных в этой сессии.
    """
    if not await aiofiles.os.path.exists(json_path):
        logger.warning("Seed-файл не найден: {}, пропускаю загрузку", json_path)
        return (0, 0)

    # Проверка: если clinics уже содержит данные и force=False — пропускаем
    if not force:
        cursor = await db_conn.execute("SELECT COUNT(*) as cnt FROM clinics")
        row = await cursor.fetchone()
        if row and row["cnt"] > 0:
            logger.debug(
                "Таблица clinics уже содержит {} записей, seed-загрузка пропущена "
                "(используйте force=True для принудительной дозагрузки)",
                row["cnt"],
            )
            return (0, 0)

    async with aiofiles.open(json_path, encoding="utf-8") as f:
        raw = await f.read()
    data = json.loads(raw)

    clinics_added = 0
    for clinic in data.get("clinics", []):
        cursor = await db_conn.execute(
            "INSERT OR IGNORE INTO clinics "
            "(clinic_id, name, type, is_active, city, "
            "discovery_patient_adult, discovery_patient_child) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                clinic["clinic_id"],
                clinic["name"],
                clinic.get("type", "adult"),
                clinic.get("is_active", 1),
                clinic.get("city", ""),
                clinic.get("discovery_patient_adult", ""),
                clinic.get("discovery_patient_child", ""),
            ),
        )
        if cursor.rowcount > 0:
            clinics_added += 1

    doctors_added = 0
    for doctor in data.get("doctors", []):
        cursor = await db_conn.execute(
            "INSERT OR IGNORE INTO doctors "
            "(clinic_id, doctor_id, name, specialty) "
            "VALUES (?, ?, ?, ?)",
            (
                doctor["clinic_id"],
                doctor["doctor_id"],
                doctor["name"],
                doctor.get("specialty", ""),
            ),
        )
        if cursor.rowcount > 0:
            doctors_added += 1

    await db_conn.commit()

    if clinics_added or doctors_added:
        logger.info(
            "Seed: загружено {} клиник(а), {} врач(ей) из {}",
            clinics_added,
            doctors_added,
            json_path,
        )
    else:
        logger.debug(
            "Seed: все записи из {} уже присутствуют в БД (0 новых)",
            json_path,
        )

    return (clinics_added, doctors_added)
