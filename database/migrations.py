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


# Упорядоченный список миграций: (version, async_callable)
MIGRATIONS = [
    (1, migrate_v1_initial_schema),
    (2, migrate_v2_clinics_columns),
]
