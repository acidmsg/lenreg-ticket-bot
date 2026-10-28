"""
Миграции схемы БД.

Каждая миграция — async callable(db: DatabaseConnection) -> None.
Номер версии хранится в таблице schema_version.

Однотипные миграции строятся на общем каркасе:

- `run_ddl_migration()` — DDL-скрипт (``CREATE TABLE`` / ``CREATE INDEX``),
  commit и запись в лог;
- `run_statement_migration()` — одно выражение без проверки существования
  (``ALTER TABLE ... ADD COLUMN``), commit и запись в лог;
- `add_missing_columns()` — идемпотентное добавление колонок: набор
  существующих читается через ``PRAGMA table_info``.

Добавление новой миграции:
1. Написать async-функцию migrate_vN_... на одном из каркасов выше
2. Добавить (N, migrate_vN_...) в список MIGRATIONS
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    import aiosqlite

    from src.database.connection import DatabaseConnection


# ── Общий каркас миграций ─────────────────────────────────────────────


def _require_connection(db: DatabaseConnection) -> aiosqlite.Connection:
    """Возвращает активное соединение или падает, если оно не открыто."""
    connection = db._conn
    if connection is None:
        raise RuntimeError("Database connection not initialized")
    return connection


async def _column_names(connection: aiosqlite.Connection, table: str) -> set[str]:
    """Имена существующих колонок таблицы (``PRAGMA table_info``)."""
    cursor = await connection.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in await cursor.fetchall()}


async def run_ddl_migration(
    db: DatabaseConnection, script: str, *, version: int, message: str
) -> None:
    """Каркас DDL-миграции: выполнение скрипта, commit и запись в лог.

    Скрипт обязан быть идемпотентным (``CREATE TABLE/INDEX IF NOT EXISTS``),
    чтобы повторный прогон миграции не падал.
    """
    connection = _require_connection(db)
    await connection.executescript(script)
    await connection.commit()
    logger.info("Миграция v{}: {}", version, message)


async def run_statement_migration(
    db: DatabaseConnection, statement: str, *, version: int, message: str
) -> None:
    """Каркас миграции из одного выражения: выполнение, commit и запись в лог."""
    connection = _require_connection(db)
    await connection.execute(statement)
    await connection.commit()
    logger.info("Миграция v{}: {}", version, message)


async def add_missing_columns(
    db: DatabaseConnection,
    table: str,
    columns: dict[str, str],
    *,
    version: int,
    message: str,
) -> list[str]:
    """Идемпотентно добавляет недостающие колонки таблицы.

    SQLite не поддерживает ``ALTER TABLE ... ADD COLUMN IF NOT EXISTS``,
    поэтому существующие колонки читаются через ``PRAGMA table_info``, а
    ``ALTER TABLE`` выполняется только для отсутствующих. Возвращает список
    фактически добавленных колонок.
    """
    connection = _require_connection(db)
    existing = await _column_names(connection, table)
    added: list[str] = []
    for column_name, definition in columns.items():
        if column_name in existing:
            continue
        await connection.execute(
            f"ALTER TABLE {table} ADD COLUMN {column_name} {definition}"
        )
        added.append(column_name)
    await connection.commit()
    logger.info("Миграция v{}: {} (добавлено: {})", version, message, added)
    return added


# ── Миграции ─────────────────────────────────────────────────────────

_INITIAL_SCHEMA_DDL = """
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
"""


async def migrate_v1_initial_schema(db: DatabaseConnection) -> None:
    """Создание всех таблиц (initial schema)."""
    await run_ddl_migration(
        db, _INITIAL_SCHEMA_DDL, version=1, message="создана начальная схема"
    )


_MONITORING_LOG_DDL = """
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
"""


async def migrate_v6_monitoring_log(db: DatabaseConnection) -> None:
    """Создаёт таблицу monitoring_log для истории изменений слотов."""
    await run_ddl_migration(
        db, _MONITORING_LOG_DDL, version=6, message="создана таблица monitoring_log"
    )


async def migrate_v7_add_date_column(db: DatabaseConnection) -> None:
    """Добавляет колонку date в таблицу user_monitoring."""
    await run_statement_migration(
        db,
        "ALTER TABLE user_monitoring ADD COLUMN date TEXT DEFAULT ''",
        version=7,
        message="добавлена колонка date в user_monitoring",
    )


_BOOKINGS_DDL = """
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
"""


async def migrate_v8_create_bookings(db: DatabaseConnection) -> None:
    """Создаёт таблицу bookings для хранения записей на приём."""
    await run_ddl_migration(
        db, _BOOKINGS_DDL, version=8, message="создана таблица bookings"
    )


async def migrate_v9_add_monitoring_filters(db: DatabaseConnection) -> None:
    """Добавляет колонки фильтра отслеживания в таблицу ``user_monitoring``.

    Миграция идемпотентна: перед ``ALTER TABLE`` проверяется наличие колонки
    через ``PRAGMA table_info`` (SQLite не поддерживает ``ADD COLUMN IF NOT EXISTS``).
    """
    await add_missing_columns(
        db,
        "user_monitoring",
        {
            "date_from": "TEXT DEFAULT ''",
            "date_to": "TEXT DEFAULT ''",
            "time_from": "TEXT DEFAULT ''",
            "time_to": "TEXT DEFAULT ''",
            "specific_dates": "TEXT DEFAULT '[]'",
        },
        version=9,
        message="колонки фильтра user_monitoring",
    )


_AUDIT_LOG_DDL = """
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
"""


async def migrate_v10_create_audit_log(db: DatabaseConnection) -> None:
    """Создание журнала действий администратора (DASH-2)."""
    await run_ddl_migration(
        db, _AUDIT_LOG_DDL, version=10, message="создана таблица audit_log"
    )


async def migrate_v11_audit_actor_index(db: DatabaseConnection) -> None:
    """Индекс по автору действий в журнале (DASH-2).

    Страница /audit-log фильтрует по actor и строит список авторов
    (``distinct_actors``) — без индекса это full table scan.
    """
    await run_statement_migration(
        db,
        "CREATE INDEX IF NOT EXISTS idx_audit_log_actor ON audit_log (actor, ts DESC)",
        version=11,
        message="индекс idx_audit_log_actor",
    )


async def migrate_v12_monitoring_log_ack(db: DatabaseConnection) -> None:
    """Статус подтверждения алертов в monitoring_log (DASH-5).

    Шум отделяется от нового: каждая запись получает состояние
    ``new`` / ``acked`` / ``resolved`` плюс кто и когда подтвердил.
    """
    await add_missing_columns(
        db,
        "monitoring_log",
        {
            "ack_status": "TEXT NOT NULL DEFAULT 'new'",
            "acked_by": "TEXT NOT NULL DEFAULT ''",
            "acked_ts": "REAL NOT NULL DEFAULT 0",
        },
        version=12,
        message="подтверждение алертов",
    )
    await run_statement_migration(
        db,
        "CREATE INDEX IF NOT EXISTS idx_monitoring_log_ack "
        "ON monitoring_log (ack_status, ts DESC)",
        version=12,
        message="индекс idx_monitoring_log_ack",
    )


_METRICS_HOURLY_DDL = """
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
"""


async def migrate_v13_metrics_hourly(db: DatabaseConnection) -> None:
    """Почасовые агрегаты метрик для трендов на сводке (DASH-6).

    Счётчики процесса (проверки API, ошибки, латентность, найденные слоты,
    уведомления) накапливаются по часам: спарклайны строятся по истории,
    а не по мгновенным значениям, и переживают перезапуск дашборда.
    """
    await run_ddl_migration(
        db, _METRICS_HOURLY_DDL, version=13, message="создана таблица metrics_hourly"
    )


_USER_STATE_DDL = """
CREATE TABLE IF NOT EXISTS user_state (
    uid        TEXT PRIMARY KEY,
    paused     INTEGER NOT NULL DEFAULT 0,
    updated_ts REAL NOT NULL DEFAULT 0
);
"""


async def migrate_v14_user_state(db: DatabaseConnection) -> None:
    """Состояние пользователя: пауза мониторинга (DASH-8).

    Пауза — это состояние, а не удаление мониторинга: при возобновлении
    цепочки пациент-врач остаются на месте.
    """
    await run_ddl_migration(
        db,
        _USER_STATE_DDL,
        version=14,
        message="состояние пользователя (пауза мониторинга)",
    )


_FAVORITE_CLINICS_DDL = """
CREATE TABLE IF NOT EXISTS favorite_clinics (
    uid         TEXT NOT NULL,
    clinic_id   TEXT NOT NULL,
    created_at  REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (uid, clinic_id)
);
"""


async def migrate_v15_favorite_clinics(db: DatabaseConnection) -> None:
    """Избранные клиники аккаунта (P4-FAV).

    Привязка — к аккаунту (``uid``), не к пациенту: набор «своих» клиник один
    на аккаунт и показывается первым при выборе клиники и поиске врача.
    Повторная вставка пары (uid, clinic_id) ничего не меняет — ключ первичный.
    """
    await run_ddl_migration(
        db,
        _FAVORITE_CLINICS_DDL,
        version=15,
        message="избранные клиники аккаунта (favorite_clinics)",
    )


async def migrate_v16_metrics_doctors(db: DatabaseConnection) -> None:
    """Динамика справочника врачей в почасовых метриках (PERF-OBS).

    Таблица ``metrics_hourly`` (миграция v13) хранила счётчики трендов; для
    наблюдения за обходами discovery добавляются колонки: сколько врачей
    всего в справочнике, сколько новых обнаружено и сколько циклов прошло.
    Миграция идемпотентна: наличие колонки проверяется через ``PRAGMA table_info``.
    """
    await add_missing_columns(
        db,
        "metrics_hourly",
        {
            "doctors_total": "INTEGER NOT NULL DEFAULT 0",
            "doctors_added": "INTEGER NOT NULL DEFAULT 0",
            "discovery_cycles": "INTEGER NOT NULL DEFAULT 0",
        },
        version=16,
        message="динамика discovery в metrics_hourly",
    )


async def migrate_v17_clinic_sync_state(db: DatabaseConnection) -> None:
    """Состояние синхронизации реестра врачей по клиникам (PERF-CACHE).

    ``doctors_synced_at`` хранит момент последнего успешного обхода клиники,
    ``doctors_count`` — сколько врачей было получено в том обходе. Повторный
    обход пропускает клиники, обновлённые свежее TTL (см. doctor_scan_ttl_hours).
    Миграция идемпотентна: наличие колонки проверяется через ``PRAGMA table_info``.
    """
    await add_missing_columns(
        db,
        "clinics",
        {
            "doctors_synced_at": "REAL NOT NULL DEFAULT 0",
            "doctors_count": "INTEGER NOT NULL DEFAULT 0",
        },
        version=17,
        message="состояние синхронизации врачей",
    )


_CLINIC_SLOTS_DDL = """
CREATE TABLE IF NOT EXISTS clinic_slots (
    clinic_id     TEXT NOT NULL,
    doctor_id     TEXT NOT NULL,
    free_tickets  INTEGER NOT NULL DEFAULT 0,
    nearest_date  TEXT NOT NULL DEFAULT '',
    updated_at    REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (clinic_id, doctor_id)
);
CREATE INDEX IF NOT EXISTS idx_clinic_slots_clinic ON clinic_slots(clinic_id);
"""


async def migrate_v18_clinic_slots(db: DatabaseConnection) -> None:
    """Кэш талонов (слотов) по клиникам (PERF-CACHE, T3).

    ``clinic_slots`` хранит талоны (``CountFreeTicket``/``NearestDate``)
    отдельно от реестра врачей (``doctors``): реестр живёт долго
    (``doctor_scan_ttl_hours``), а талоны меняются часто и обновляются своим
    коротким TTL (``slot_cache_ttl_minutes``). Экран «Выберите врача» отдаёт
    талоны из этой таблицы, не дожидаясь портала. Миграция идемпотентна:
    таблица создаётся через ``CREATE TABLE IF NOT EXISTS``.
    """
    await run_ddl_migration(
        db,
        _CLINIC_SLOTS_DDL,
        version=18,
        message="создана таблица clinic_slots (кэш талонов)",
    )


async def migrate_v19_clinic_empty_sync_streak(db: DatabaseConnection) -> None:
    """Счётчик подряд идущих пустых синков клиники (PERF-BACKOFF, T6).

    ``empty_sync_streak`` — сколько подряд обходов клиники вернули 0 врачей;
    успешный непустой синк сбрасывает счётчик в 0. Клиники с ненулевым
    счётчиком обходятся по бэкоффу (``empty_clinic_backoff_hours``) реже, чем
    по обычному TTL, — частые пустые обходы не тратят портальные вызовы
    впустую. Миграция идемпотентна: наличие колонки проверяется через
    ``PRAGMA table_info``.
    """
    await add_missing_columns(
        db,
        "clinics",
        {"empty_sync_streak": "INTEGER NOT NULL DEFAULT 0"},
        version=19,
        message="бэкофф клиник без врачей",
    )


async def migrate_v20_bookings_status(db: DatabaseConnection) -> None:
    """Добавляет колонку status в bookings (pending/confirmed/failed)."""
    await add_missing_columns(
        db,
        "bookings",
        {"status": "TEXT NOT NULL DEFAULT 'confirmed'"},
        version=20,
        message="колонка status в bookings",
    )


async def migrate_v21_naming_constitution(db: DatabaseConnection) -> None:
    """Приведение имён схемы к конституции `.roo/rules/naming.md` (DB-CONSTITUTION).

    Таблицы в единственном числе переименованы во множественное; колонки-счётчики
    получили суффикс `_count`, устаревший суффикс `_ts` заменён на `_at`.
    Используется `ALTER TABLE ... RENAME` (SQLite >= 3.25): без пересборки таблиц
    и без потери данных. Миграция идемпотентна — наличие проверяется по
    `sqlite_master` и `PRAGMA table_info`.
    """
    c = _require_connection(db)

    async def rename_table(old: str, new: str) -> None:
        cursor = await c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (old,)
        )
        if await cursor.fetchone() is not None:
            await c.execute(f"ALTER TABLE {old} RENAME TO {new}")

    async def rename_column(table: str, old: str, new: str) -> None:
        cursor = await c.execute(f"PRAGMA table_info({table})")
        columns = {row[1] for row in await cursor.fetchall()}
        if old in columns and new not in columns:
            await c.execute(f"ALTER TABLE {table} RENAME COLUMN {old} TO {new}")

    await rename_table("audit_log", "audit_logs")
    await rename_table("monitoring_log", "monitoring_logs")
    await rename_table("user_state", "user_states")

    for old, new in (
        ("api_checks", "api_check_count"),
        ("api_errors", "api_error_count"),
        ("slots_found", "found_slot_count"),
        ("notifications", "notification_count"),
        ("bucket_ts", "bucket_at"),
    ):
        await rename_column("metrics_hourly", old, new)
    await rename_column("user_states", "updated_ts", "updated_at")

    # Имена индексов содержали старые имена таблиц — пересоздаём.
    for index in (
        "idx_audit_log_ts",
        "idx_audit_log_action",
        "idx_audit_log_actor",
        "idx_monitoring_log_uid",
        "idx_monitoring_log_ts",
        "idx_monitoring_log_ack",
    ):
        await c.execute(f"DROP INDEX IF EXISTS {index}")
    await c.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_logs_ts ON audit_logs (ts DESC)"
    )
    await c.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_logs_action "
        "ON audit_logs (action, ts DESC)"
    )
    await c.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_logs_actor ON audit_logs (actor, ts DESC)"
    )
    await c.execute(
        "CREATE INDEX IF NOT EXISTS idx_monitoring_logs_uid ON monitoring_logs(uid)"
    )
    await c.execute(
        "CREATE INDEX IF NOT EXISTS idx_monitoring_logs_ts ON monitoring_logs(ts)"
    )
    await c.execute(
        "CREATE INDEX IF NOT EXISTS idx_monitoring_logs_ack "
        "ON monitoring_logs (ack_status, ts DESC)"
    )
    await c.commit()
    logger.info("Миграция v21: имена схемы приведены к конституции")


async def migrate_v22_user_language(db: DatabaseConnection) -> None:
    """Язык интерфейса пользователя (ru/en) в user_states (i18n).

    Telegram отдаёт язык клиента в language_code; храним выбор по пользователю,
    чтобы уведомления формировались на его языке (см. src/i18n).
    """
    await add_missing_columns(
        db,
        "user_states",
        {"language": "TEXT NOT NULL DEFAULT ''"},
        version=22,
        message="язык пользователя (user_states.language)",
    )


_CLINIC_SLOT_SCANS_DDL = """
CREATE TABLE IF NOT EXISTS clinic_slot_scans (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    clinic_id         TEXT NOT NULL,
    scanned_at        REAL NOT NULL DEFAULT 0,
    doctor_count      INTEGER NOT NULL DEFAULT 0,
    free_ticket_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_clinic_slot_scans_clinic_ts
    ON clinic_slot_scans (clinic_id, scanned_at DESC);
CREATE INDEX IF NOT EXISTS idx_clinic_slot_scans_ts
    ON clinic_slot_scans (scanned_at DESC);
"""


async def migrate_v23_clinic_slot_scans(db: DatabaseConnection) -> None:
    """История полных сканов талонов клиники (аналитика всплесков).

    ``clinic_slots`` хранит только последний снимок: каждая запись
    перезаписывается. Для ответа на вопрос «когда появляются талоны» нужна
    история агрегатов по клинике, а не текущее состояние. Таблица пишется
    из ``sync_clinic_slots()`` и не участвует в выдаче талонов пользователю.
    Миграция идемпотентна: ``CREATE TABLE IF NOT EXISTS``.
    """
    await run_ddl_migration(
        db,
        _CLINIC_SLOT_SCANS_DDL,
        version=23,
        message="создана таблица clinic_slot_scans (история сканов)",
    )


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
    (15, migrate_v15_favorite_clinics),
    (16, migrate_v16_metrics_doctors),
    (17, migrate_v17_clinic_sync_state),
    (18, migrate_v18_clinic_slots),
    (19, migrate_v19_clinic_empty_sync_streak),
    (20, migrate_v20_bookings_status),
    (21, migrate_v21_naming_constitution),
    (22, migrate_v22_user_language),
    (23, migrate_v23_clinic_slot_scans),
]
