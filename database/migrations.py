"""
Миграции схемы БД.

Каждая миграция — async callable(db: Database) -> None.
Номер версии хранится в таблице schema_version.
Добавление новой миграции:
1. Написать async-функцию migrate_vN_...
2. Добавить (N, migrate_vN_...) в список MIGRATIONS
"""

import logging

logger = logging.getLogger(__name__)


async def migrate_v1_initial_schema(db):
    """Создание всех таблиц (initial schema)."""
    c = db._conn
    if c is None:
        raise RuntimeError("Database connection not initialized")
    await c.executescript("""
CREATE TABLE IF NOT EXISTS user_last_messages (
uid                 TEXT NOT NULL,
p_id                TEXT NOT NULL,
d_id                TEXT NOT NULL,
msg_id              INTEGER NOT NULL,
ts                  REAL NOT NULL DEFAULT 0,
PRIMARY KEY (uid, p_id, d_id)
);
CREATE TABLE IF NOT EXISTS clinics (
clinic_id           TEXT PRIMARY KEY,
name                TEXT NOT NULL DEFAULT 'Unknown',
type                TEXT NOT NULL DEFAULT 'adult',
is_active           INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS doctors (
clinic_id           TEXT NOT NULL,
doctor_id           TEXT NOT NULL,
name                TEXT NOT NULL,
specialty           TEXT NOT NULL DEFAULT '',
PRIMARY KEY (clinic_id, doctor_id)
);
CREATE TABLE IF NOT EXISTS user_patients (
uid                 TEXT NOT NULL,
p_id                TEXT NOT NULL,
fio                 TEXT NOT NULL DEFAULT '',
bday                TEXT NOT NULL DEFAULT '',
alias               TEXT,
confirmed_clinics   TEXT NOT NULL DEFAULT '[]',
PRIMARY KEY (uid, p_id)
);
CREATE TABLE IF NOT EXISTS user_monitoring (
uid                 TEXT NOT NULL,
p_id                TEXT NOT NULL,
d_id                TEXT NOT NULL,
name                TEXT NOT NULL DEFAULT '',
clinic_id           TEXT NOT NULL DEFAULT '',
specialty           TEXT NOT NULL DEFAULT '',
PRIMARY KEY (uid, p_id, d_id)
);
CREATE TABLE IF NOT EXISTS config (
key                 TEXT PRIMARY KEY,
value               TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS specialty_aliases (
full_name           TEXT PRIMARY KEY,
short_name          TEXT NOT NULL DEFAULT ''
);
""")
    await c.commit()


async def migrate_v2_clinics_columns(db):
    """Добавляет недостающие колонки в таблицу clinics."""
    c = db._conn
    if c is None:
        return
    for col, col_type, default in [
        ("type", "TEXT", "'adult'"),
        ("is_active", "INTEGER", "1"),
        ("city", "TEXT", "''"),
        ("discovery_patient_adult", "TEXT", "''"),
        ("discovery_patient_child", "TEXT", "''"),
    ]:
        try:
            await c.execute(
                f"ALTER TABLE clinics ADD COLUMN {col} {col_type} NOT NULL DEFAULT {default}"
            )
        except Exception:
            pass  # колонка уже существует


async def migrate_v5_seed_new_config_keys(db):
    """Заполняет config дефолтными значениями из settings (INSERT OR IGNORE — безопасен для существующих БД)."""
    c = db._conn
    if c is None:
        return
    from config import settings as s

    all_keys = {
        "api_timeout": str(s.API_TIMEOUT),
        "check_interval": str(s.CHECK_INTERVAL),
        "discovery_interval": str(s.DISCOVERY_INTERVAL),
        "message_ttl_seconds": str(s.MESSAGE_TTL_SECONDS),
        "cleanup_interval": str(s.CLEANUP_INTERVAL),
        "slot_threshold_absolute": str(s.SLOT_THRESHOLD_ABSOLUTE),
        "slot_threshold_percentage": str(s.SLOT_THRESHOLD_PERCENTAGE),
        "discovery_patient_adult": str(s.DISCOVERY_PATIENT_ID_ADULT),
        "discovery_patient_child": str(s.DISCOVERY_PATIENT_ID_CHILD),
        "default_clinic_id": str(s.DEFAULT_CLINIC_ID),
        "default_birthday": str(s.DEFAULT_BIRTHDAY),
        "api_base_url": s.API_BASE_URL,
        "referer_url": s.REFERER_URL,
        "csrf_token": s.CSRF_TOKEN,
        "admin_ids": s.ADMIN_IDS,
        "error_notify_enabled": str(s.ERROR_NOTIFY_ENABLED),
        "environment": s.ENVIRONMENT,
        "user_rate_limit_max": str(s.USER_RATE_LIMIT_MAX),
        "user_rate_limit_period": str(s.USER_RATE_LIMIT_PERIOD),
    }

    for key, value in all_keys.items():
        await c.execute(
            "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)",
            (key, value),
        )
    await c.commit()
    logger.info("Миграция v5: config заполнен дефолтными значениями")


# Упорядоченный список миграций: (version, async_callable)
MIGRATIONS = [
    (1, migrate_v1_initial_schema),
    (2, migrate_v2_clinics_columns),
    (5, migrate_v5_seed_new_config_keys),
]
