"""
Миграции схемы БД.

Каждая миграция — async callable(db: Database) -> None.
Номер версии хранится в таблице schema_version.
Добавление новой миграции:
1. Написать async-функцию migrate_vN_...
2. Добавить (N, migrate_vN_...) в список MIGRATIONS
"""

from loguru import logger


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
clinic_id               TEXT PRIMARY KEY,
name                    TEXT NOT NULL DEFAULT 'Unknown',
type                    TEXT NOT NULL DEFAULT 'adult',
is_active               INTEGER NOT NULL DEFAULT 1,
city                    TEXT NOT NULL DEFAULT '',
discovery_patient_adult TEXT NOT NULL DEFAULT '',
discovery_patient_child TEXT NOT NULL DEFAULT ''
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


async def migrate_v6_monitoring_log(db):
    """Создаёт таблицу monitoring_log для истории изменений слотов."""
    c = db._conn
    if c is None:
        raise RuntimeError("Database connection not initialized")
    await c.executescript("""
CREATE TABLE IF NOT EXISTS monitoring_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    uid         TEXT NOT NULL,
    p_id        TEXT NOT NULL,
    d_id        TEXT NOT NULL,
    doctor_name TEXT NOT NULL DEFAULT '',
    patient_name TEXT NOT NULL DEFAULT '',
    specialty   TEXT NOT NULL DEFAULT '',
    clinic_name TEXT NOT NULL DEFAULT '',
    slot_date   TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT '',
    ts          REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_monitoring_log_uid ON monitoring_log(uid);
CREATE INDEX IF NOT EXISTS idx_monitoring_log_ts ON monitoring_log(ts);
""")
    await c.commit()
    logger.info("Миграция v6: создана таблица monitoring_log")


# Упорядоченный список миграций: (version, async_callable)
MIGRATIONS = [
    (1, migrate_v1_initial_schema),
    (6, migrate_v6_monitoring_log),
]
