"""
Миграции схемы БД.

Каждая миграция — async callable(db: Database) -> None.
Номер версии хранится в таблице schema_version.
Добавление новой миграции:
1. Написать async-функцию migrate_vN_...
2. Добавить (N, migrate_vN_...) в список MIGRATIONS
"""

from loguru import logger


async def migrate_v1_initial_schema(db) -> None:
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


async def migrate_v6_monitoring_log(db) -> None:
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


async def migrate_v7_add_date_column(db) -> None:
    """Добавляет колонку date в таблицу user_monitoring."""
    c = db._conn
    if c is None:
        raise RuntimeError("Database connection not initialized")
    await c.execute("ALTER TABLE user_monitoring ADD COLUMN date TEXT DEFAULT ''")
    await c.commit()
    logger.info("Миграция v7: добавлена колонка date в user_monitoring")


async def migrate_v8_create_bookings(db) -> None:
    """Создаёт таблицу bookings для хранения записей на приём."""
    c = db._conn
    if c is None:
        raise RuntimeError("Database connection not initialized")
    await c.executescript("""
CREATE TABLE IF NOT EXISTS bookings (
    booking_id     TEXT PRIMARY KEY,
    uid            TEXT NOT NULL,
    p_id           TEXT NOT NULL,
    d_id           TEXT NOT NULL,
    doctor_name    TEXT NOT NULL DEFAULT '',
    patient_name   TEXT NOT NULL DEFAULT '',
    specialty      TEXT NOT NULL DEFAULT '',
    clinic_id      TEXT NOT NULL DEFAULT '',
    clinic_name    TEXT NOT NULL DEFAULT '',
    slot_date      TEXT NOT NULL DEFAULT '',
    slot_time      TEXT NOT NULL DEFAULT '',
    appointment_id TEXT NOT NULL DEFAULT '',
    created_at     REAL NOT NULL DEFAULT 0,
    is_archived    INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_bookings_uid ON bookings(uid);
CREATE INDEX IF NOT EXISTS idx_bookings_created_at ON bookings(created_at);
""")
    await c.commit()
    logger.info("Миграция v8: создана таблица bookings")


async def migrate_v9_add_monitoring_filters(db) -> None:
    """Добавляет колонки фильтра отслеживания в таблицу ``user_monitoring``.

    Миграция идемпотентна: перед ``ALTER TABLE`` проверяется наличие колонки
    через ``PRAGMA table_info`` (SQLite не поддерживает ``ADD COLUMN IF NOT EXISTS``).
    """
    c = db._conn
    if c is None:
        raise RuntimeError("Database connection not initialized")

    cursor = await c.execute("PRAGMA table_info(user_monitoring)")
    existing_columns = {row["name"] for row in await cursor.fetchall()}

    new_columns: dict[str, str] = {
        "date_from": "TEXT DEFAULT ''",
        "date_to": "TEXT DEFAULT ''",
        "time_from": "TEXT DEFAULT ''",
        "time_to": "TEXT DEFAULT ''",
        "specific_dates": "TEXT DEFAULT '[]'",
    }

    added: list[str] = []
    for column_name, definition in new_columns.items():
        if column_name in existing_columns:
            continue
        await c.execute(
            f"ALTER TABLE user_monitoring ADD COLUMN {column_name} {definition}"
        )
        added.append(column_name)

    await c.commit()
    logger.info("Миграция v9: колонки фильтра user_monitoring (добавлено: {})", added)


async def migrate_v10_create_audit_log(db) -> None:
    """Создание журнала действий администратора (DASH-2)."""
    c = db._conn
    if c is None:
        raise RuntimeError("Database connection not initialized")
    await c.executescript("""
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    actor TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_audit_log_ts ON audit_log (ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log (action, ts DESC);
""")
    await c.commit()
    logger.info("Миграция v10: создана таблица audit_log")


async def migrate_v11_audit_actor_index(db) -> None:
    """Индекс по автору действий в журнале (DASH-2).

    Страница /audit-log фильтрует по actor и строит список авторов
    (``distinct_actors``) — без индекса это full table scan.
    """
    c = db._conn
    if c is None:
        raise RuntimeError("Database connection not initialized")
    await c.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_log_actor ON audit_log (actor, ts DESC)"
    )
    await c.commit()
    logger.info("Миграция v11: индекс idx_audit_log_actor")


async def migrate_v12_monitoring_log_ack(db) -> None:
    """Статус подтверждения алертов в monitoring_log (DASH-5).

    Шум отделяется от нового: каждая запись получает состояние
    ``new`` / ``acked`` / ``resolved`` плюс кто и когда подтвердил.
    """
    c = db._conn
    if c is None:
        raise RuntimeError("Database connection not initialized")

    cursor = await c.execute("PRAGMA table_info(monitoring_log)")
    existing_columns = {row[1] for row in await cursor.fetchall()}

    new_columns = {
        "ack_status": "TEXT NOT NULL DEFAULT 'new'",
        "acked_by": "TEXT NOT NULL DEFAULT ''",
        "acked_ts": "REAL NOT NULL DEFAULT 0",
    }
    added: list[str] = []
    for column_name, definition in new_columns.items():
        if column_name in existing_columns:
            continue
        await c.execute(
            f"ALTER TABLE monitoring_log ADD COLUMN {column_name} {definition}"
        )
        added.append(column_name)

    await c.execute(
        "CREATE INDEX IF NOT EXISTS idx_monitoring_log_ack "
        "ON monitoring_log (ack_status, ts DESC)"
    )
    await c.commit()
    logger.info("Миграция v12: подтверждение алертов (добавлено: {})", added)


async def migrate_v13_metrics_hourly(db) -> None:
    """Почасовые агрегаты метрик для трендов на сводке (DASH-6).

    Счётчики процесса (проверки API, ошибки, латентность, найденные слоты,
    уведомления) накапливаются по часам: спарклайны строятся по истории,
    а не по мгновенным значениям, и переживают перезапуск дашборда.
    """
    c = db._conn
    if c is None:
        raise RuntimeError("Database connection not initialized")

    await c.executescript("""
CREATE TABLE IF NOT EXISTS metrics_hourly (
    bucket_ts     INTEGER PRIMARY KEY,
    api_checks    INTEGER NOT NULL DEFAULT 0,
    api_errors    INTEGER NOT NULL DEFAULT 0,
    latency_sum   REAL NOT NULL DEFAULT 0,
    latency_max   REAL NOT NULL DEFAULT 0,
    latency_count INTEGER NOT NULL DEFAULT 0,
    slots_found   INTEGER NOT NULL DEFAULT 0,
    notifications INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_metrics_hourly_bucket ON metrics_hourly(bucket_ts);
""")
    await c.commit()
    logger.info("Миграция v13: создана таблица metrics_hourly")


async def migrate_v14_user_state(db) -> None:
    """Состояние пользователя: пауза мониторинга (DASH-8).

    Пауза — это состояние, а не удаление мониторинга: при возобновлении
    цепочки пациент-врач остаются на месте.
    """
    c = db._conn
    if c is None:
        raise RuntimeError("Database connection not initialized")

    await c.executescript("""
CREATE TABLE IF NOT EXISTS user_state (
    uid        TEXT PRIMARY KEY,
    paused     INTEGER NOT NULL DEFAULT 0,
    updated_ts REAL NOT NULL DEFAULT 0
);
""")
    await c.commit()
    logger.info("Миграция v14: состояние пользователя (пауза мониторинга)")


# Упорядоченный список миграций: (version, async_callable)
MIGRATIONS = [
    (1, migrate_v1_initial_schema),
    (6, migrate_v6_monitoring_log),
    (7, migrate_v7_add_date_column),
    (8, migrate_v8_create_bookings),
    (9, migrate_v9_add_monitoring_filters),
    (10, migrate_v10_create_audit_log),
    (11, migrate_v11_audit_actor_index),
    (12, migrate_v12_monitoring_log_ack),
    (13, migrate_v13_metrics_hourly),
    (14, migrate_v14_user_state),
]
