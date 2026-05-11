"""
Скрипт миграции: переносит данные из конфигов (config.py, utils/helpers.py) в таблицы БД.

Запускать один раз после обновления кода:
    python scripts/migrate_configs_to_db.py

Можно вызывать многократно — идемпотентно.
"""

import asyncio
import logging
import sys
import os

# Добавляем корень проекта в пути
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("migration")


async def migrate():
    from database.database import Database
    from config import CLINICS_REGISTRY, settings
    from utils.helpers import SPECIALTY_ALIASES

    db = Database(settings.SQLITE_DB_PATH)
    await db.connect()

    # 1. Миграция клиник: проставляем type и is_active из CLINICS_REGISTRY
    logger.info("Миграция клиник...")
    for c_id, info in CLINICS_REGISTRY.items():
        existing_name = await db.get_clinic_name(c_id)
        name = existing_name or info.name
        await db.upsert_clinic_full(
            clinic_id=c_id,
            name=name,
            clinic_type=info.type,
            is_active=1,
        )
        logger.info(f"  Клиника {c_id}: name={name}, type={info.type}, active=1")

    # Если в БД есть клиники, которых нет в CLINICS_REGISTRY — не трогаем,
    # они остаются с дефолтными значениями (type='adult', is_active=1)

    # 2. Миграция конфигов
    logger.info("Миграция настроек...")
    config_defaults = {
        "slot_threshold_absolute": str(settings.SLOT_THRESHOLD_ABSOLUTE),
        "slot_threshold_percentage": str(settings.SLOT_THRESHOLD_PERCENTAGE),
        "check_interval": str(settings.CHECK_INTERVAL),
        "discovery_interval": str(settings.DISCOVERY_INTERVAL),
        "discovery_patient_id_adult": settings.DISCOVERY_PATIENT_ID_ADULT,
        "discovery_patient_id_child": settings.DISCOVERY_PATIENT_ID_CHILD,
        "default_clinic_id": settings.DEFAULT_CLINIC_ID,
        "default_birthday": settings.DEFAULT_BIRTHDAY,
        "message_ttl_seconds": str(settings.MESSAGE_TTL_SECONDS),
        "cleanup_interval": str(settings.CLEANUP_INTERVAL),
        "api_base_url": settings.API_BASE_URL,
        "referer_url": settings.REFERER_URL,
        "csrf_token": settings.CSRF_TOKEN,
        "api_timeout": str(settings.API_TIMEOUT),
    }
    for key, value in config_defaults.items():
        existing = await db.get_config(key)
        if not existing:
            await db.set_config(key, value)
            logger.info(f"  config {key}={value}")
        else:
            logger.info(f"  config {key}: уже существует ({existing}), пропускаем")

    # 3. Миграция псевдонимов специальностей
    logger.info("Миграция псевдонимов специальностей...")
    for full_name, short_name in SPECIALTY_ALIASES.items():
        await db.upsert_specialty_alias(full_name, short_name)
        logger.info(f"  alias: {full_name} -> {short_name}")

    logger.info("Миграция завершена успешно!")
    await db.close()


if __name__ == "__main__":
    asyncio.run(migrate())
