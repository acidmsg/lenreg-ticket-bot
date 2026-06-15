#!/usr/bin/env python3
"""
CLI для ручной загрузки seed-данных (клиники, врачи) из JSON в БД.

Использование:
    python scripts/seed_data.py [db_path] [json_path] [--force]

    db_path   — путь к SQLite БД (по умолчанию: data/bot.db)
    json_path — путь к JSON с ключами clinics/doctors
                (по умолчанию: data/seed/clinics_doctors.json)
    --force   — загрузить даже при непустой таблице clinics

Примеры:
    python scripts/seed_data.py
    python scripts/seed_data.py data/bot.db data/seed/clinics_doctors.json --force

В Docker-контейнере (через volume mount scripts/):
    docker compose exec bot python scripts/seed_data.py \\
        data/bot.db data/seed/clinics_doctors.json --force
"""

import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в sys.path, чтобы импорты src.* работали
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database.connection import DatabaseConnection
from src.database.seed import seed_clinics_and_doctors_from_json


async def main() -> None:
    db_path = sys.argv[1] if len(sys.argv) > 1 else "data/bot.db"
    json_path = sys.argv[2] if len(sys.argv) > 2 else "data/seed/clinics_doctors.json"
    force = "--force" in sys.argv

    print(f"Seed-загрузка: db={db_path}, json={json_path}, force={force}")

    conn = DatabaseConnection(db_path)
    await conn.connect()
    try:
        clinics_added, doctors_added = await seed_clinics_and_doctors_from_json(
            conn.conn, json_path, force=force
        )
        print(
            f"Результат: {clinics_added} клиник(а), {doctors_added} врач(ей) добавлено"
        )
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
