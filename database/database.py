"""
Единый SQLite-движок для хранения данных.
"""

import json
import logging
import os
import re
from typing import Any, Dict, Optional

import aiosqlite

logger = logging.getLogger(__name__)


def detect_clinic_type(name: str) -> str:
    """
    Определяет тип клиники по её названию.

    Порядок проверки:
    1. 'стоматолог' → 'all' (в стоматологии есть и взрослые, и дети).
       Даже если в названии есть "детск" — стоматология всегда all.
    2. 'детск' → 'child' (детская, детский и т.п.)
    3. Иначе → 'adult'
    """
    if not name:
        return "adult"
    lower = name.lower()
    # Стоматология — приоритетно all, даже если есть "детская" в названии
    if re.search(r"стоматолог", lower):
        return "all"
    if re.search(r"детск", lower):
        return "child"
    return "adult"


def detect_clinic_city(name: str) -> str:
    """
    Определяет город/район по полному названию клиники.

    Приоритет: сначала ищем конкретный населённый пункт,
    потом определяем по ЛПУ (часть в кавычках).
    """
    if not name:
        return "Прочее"

    lower = name.lower()

    # Конкретные населённые пункты (приоритет — первое совпадение)
    settlements = [
        ("кудрово", "Кудрово"),
        ("мурино", "Мурино"),
        ("девяткино", "Девяткино"),
        ("бугры", "Бугры"),
        ("кузьмолово", "Кузьмолово"),
        ("токсово", "Токсово"),
        ("сертолово", "Сертолово"),
        ("всеволожск", "Всеволожск"),
        ("всеволож", "Всеволожск"),
        ("павлово", "Павлово"),
        ("разметелево", "Разметелево"),
        ("рахья", "Рахья"),
        ("романовка", "Романовка"),
        ("щеглово", "Щеглово"),
        ("заневский", "Заневский"),
        ("дубровка", "Дубровка"),
        ("кальтино", "Кальтино"),
        ("краснозвездин", "Краснозвездинское"),
        ("морозов", "им. Морозова"),
        ("гарболово", "Гарболово"),
        ("рапполово", "Рапполово"),
        ("вартемяги", "Вартемяги"),
        ("куйвози", "Куйвози"),
        ("лесколово", "Лесколово"),
        ("сте – клянный", "Стеклянный"),
        ("пери", "Пери"),
        ("лесное", "Лесное"),
        ("юкки", "Юкки"),
        ("хиттолово", "Хиттолово"),
        ("ненимяки", "Ненимяки"),
        ("лехтуси", "Лехтуси"),
        ("васкелово", "Васкелово"),
        ("лаврики", "Лаврики"),
        ("воейково", "Воейково"),
        ("каменка", "Каменка"),
        ("грибное", "Грибное"),
        ("ваганово", "Ваганово"),
        ("новая пустошь", "Новая Пустошь"),
        ("углово", "Углово"),
        ("старая", "Старая"),
        ("ясная", "Ясная"),
    ]
    for keyword, city in settlements:
        if keyword in lower:
            return city

    # Определяем по ЛПУ (часть в кавычках)
    lpu_match = re.search(r'"([^"]+)"', name)
    lpu = lpu_match.group(1).lower() if lpu_match else lower

    if "всеволож" in lpu:
        return "Всеволожск"
    if "сертолов" in lpu:
        return "Сертолово"
    if "токсов" in lpu:
        return "Токсово"
    if "лонд" in lpu.replace(" ", ""):
        return "Наркология (ЛОНД)"
    if "лоцпз" in lpu.replace(" ", ""):
        return "Психиатрия (ЛОЦПЗ)"
    if "медицентр" in lpu:
        return "Медицентр"

    return "Прочее"


class Database:
    """SQLite-обёртка с созданием таблиц."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    # ── Управление соединением ──────────────────────────────
    async def connect(self):
        """Открыть соединение и создать таблицы."""
        data_dir = os.path.dirname(self.db_path)
        if data_dir and not os.path.exists(data_dir):
            try:
                os.makedirs(data_dir)
                logger.info(f"Каталог '{data_dir}' создан для базы данных.")
            except OSError as e:
                logger.error(f"Не удалось создать каталог '{data_dir}': {e}")
                raise

        try:
            self._conn = await aiosqlite.connect(self.db_path)
            c = self._conn
            if c is None:
                raise RuntimeError("Database connection not initialized")

            logger.info(f"Соединение с базой данных '{self.db_path}' установлено.")

            c.row_factory = aiosqlite.Row

            await self._create_tables()
            await self._enable_wal()

        except aiosqlite.Error as e:
            logger.error(f"Ошибка подключения aiosqlite для '{self.db_path}': {e}")
            raise
        except Exception as e:
            logger.error(
                f"Общая ошибка при подключении к базе данных '{self.db_path}': {e}"
            )
            raise

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def _enable_wal(self):
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        await c.execute("PRAGMA journal_mode=WAL")
        await c.execute("PRAGMA busy_timeout=5000")
        await c.execute("PRAGMA foreign_keys=ON")

    async def _create_tables(self):
        c = self._conn
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
CREATE TABLE IF NOT EXISTS schema_version (
version             INTEGER PRIMARY KEY
);
""")
        await c.commit()
        # Миграция для существующих БД: добавить колонки, если их нет
        await self._migrate_clinics_add_columns()

    async def _migrate_clinics_add_columns(self):
        """Добавляет недостающие колонки в таблицу clinics (для существующих БД)."""
        c = self._conn
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

    # ── Пользователи ────────────────────────────────────────
    async def get_user(self, uid: str) -> Optional[Dict[str, Any]]:
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")

        patients = await self.get_user_patients(uid)
        monitoring = await self.get_user_monitoring(uid)
        lm_cursor = await c.execute(
            "SELECT p_id, d_id, msg_id, ts FROM user_last_messages WHERE uid = ?",
            (uid,),
        )
        lm_rows = await lm_cursor.fetchall()
        last_messages = {}
        for lmr in lm_rows:
            key = f"{lmr['p_id']}_{lmr['d_id']}"
            last_messages[key] = {"msg_id": lmr["msg_id"], "ts": lmr["ts"]}

        if not patients and not monitoring and not last_messages:
            return None

        return {
            "patients": patients,
            "monitoring": monitoring,
            "last_messages": last_messages,
        }

    async def get_all_user_ids(self) -> list[str]:
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        cursor = await c.execute("""
            SELECT DISTINCT uid FROM user_patients
            UNION
            SELECT DISTINCT uid FROM user_monitoring
            UNION
            SELECT DISTINCT uid FROM user_last_messages
        """)
        rows = await cursor.fetchall()
        return [row["uid"] for row in rows]

    # ── last_messages (user_last_messages) ───────────────────

    async def set_last_message(
        self, uid: str, p_id: str, d_id: str, msg_id: int, ts: float = 0
    ):
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        await c.execute(
            "INSERT OR REPLACE INTO user_last_messages (uid, p_id, d_id, msg_id, ts) VALUES (?, ?, ?, ?, ?)",
            (uid, p_id, d_id, msg_id, ts),
        )
        await c.commit()

    async def get_last_message(
        self, uid: str, p_id: str, d_id: str
    ) -> Optional[Dict[str, Any]]:
        c = self._conn
        if c is None:
            return None
        cursor = await c.execute(
            "SELECT msg_id, ts FROM user_last_messages WHERE uid = ? AND p_id = ? AND d_id = ?",
            (uid, p_id, d_id),
        )
        row = await cursor.fetchone()
        if row:
            return {"msg_id": row["msg_id"], "ts": row["ts"]}
        return None

    # ── Пациенты (user_patients) ────────────────────────────

    async def get_user_patients(self, uid: str) -> Dict[str, Dict[str, Any]]:
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        cursor = await c.execute(
            "SELECT p_id, fio, bday, alias, confirmed_clinics "
            "FROM user_patients WHERE uid = ?",
            (uid,),
        )
        rows = await cursor.fetchall()
        result = {}
        for row in rows:
            confirmed = (
                json.loads(row["confirmed_clinics"]) if row["confirmed_clinics"] else []
            )
            p_info = {
                "fio": row["fio"],
                "bday": row["bday"],
                "alias": row["alias"],
                "confirmed_clinics": confirmed,
            }
            if p_info["alias"] is None:
                del p_info["alias"]
            result[row["p_id"]] = p_info
        return result

    async def add_patient(
        self,
        uid: str,
        p_id: str,
        fio: str,
        bday: str,
        alias: str | None,
        confirmed_clinics: list | None = None,
    ):
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        if confirmed_clinics is None:
            confirmed_clinics = []
        await c.execute(
            """INSERT OR REPLACE INTO user_patients
               (uid, p_id, fio, bday, alias, confirmed_clinics)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                uid,
                p_id,
                fio,
                bday,
                alias,
                json.dumps(confirmed_clinics, ensure_ascii=False),
            ),
        )
        await c.commit()

    async def update_patient_confirmed_clinics(
        self,
        uid: str,
        p_id: str,
        confirmed_clinics: list,
    ):
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        await c.execute(
            "UPDATE user_patients SET confirmed_clinics = ? WHERE uid = ? AND p_id = ?",
            (json.dumps(confirmed_clinics, ensure_ascii=False), uid, p_id),
        )
        await c.commit()

    async def delete_patient(self, uid: str, p_id: str):
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        await c.execute(
            "DELETE FROM user_patients WHERE uid = ? AND p_id = ?",
            (uid, p_id),
        )
        await c.execute(
            "DELETE FROM user_monitoring WHERE uid = ? AND p_id = ?",
            (uid, p_id),
        )
        await c.execute(
            "DELETE FROM user_last_messages WHERE uid = ? AND p_id = ?",
            (uid, p_id),
        )
        await c.commit()

    # ── Мониторинг (user_monitoring) ────────────────────────

    async def get_user_monitoring(
        self, uid: str
    ) -> Dict[str, Dict[str, Dict[str, Any]]]:
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        cursor = await c.execute(
            "SELECT p_id, d_id, name, clinic_id, specialty "
            "FROM user_monitoring WHERE uid = ?",
            (uid,),
        )
        rows = await cursor.fetchall()
        result: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for row in rows:
            p_id = row["p_id"]
            if p_id not in result:
                result[p_id] = {}
            result[p_id][row["d_id"]] = {
                "name": row["name"],
                "clinic_id": row["clinic_id"],
                "specialty": row["specialty"],
            }
        return result

    async def add_monitoring_entry(
        self,
        uid: str,
        p_id: str,
        d_id: str,
        name: str,
        clinic_id: str,
        specialty: str,
    ):
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        await c.execute(
            """INSERT OR REPLACE INTO user_monitoring
               (uid, p_id, d_id, name, clinic_id, specialty)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (uid, p_id, d_id, name, clinic_id, specialty),
        )
        await c.commit()

    async def remove_monitoring_entry(self, uid: str, p_id: str, d_id: str):
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        await c.execute(
            "DELETE FROM user_monitoring WHERE uid = ? AND p_id = ? AND d_id = ?",
            (uid, p_id, d_id),
        )
        await c.commit()

    async def clear_all_monitoring(self, uid: str):
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        await c.execute(
            "DELETE FROM user_monitoring WHERE uid = ?",
            (uid,),
        )
        await c.commit()

    # ── Врачи ───────────────────────────────────────────────

    async def get_clinic_doctors(self, clinic_id: str) -> Dict[str, Dict[str, str]]:
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        cursor = await c.execute(
            "SELECT doctor_id, name, specialty FROM doctors WHERE clinic_id = ?",
            (clinic_id,),
        )
        rows = await cursor.fetchall()
        return {
            row["doctor_id"]: {"name": row["name"], "specialty": row["specialty"]}
            for row in rows
        }

    async def upsert_doctor(
        self, clinic_id: str, doctor_id: str, name: str, specialty: str
    ):
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        await c.execute(
            """INSERT OR REPLACE INTO doctors
            (clinic_id, doctor_id, name, specialty)
            VALUES (?, ?, ?, ?)""",
            (clinic_id, doctor_id, name, specialty),
        )
        await c.commit()

    async def upsert_clinic(self, clinic_id: str, name: str):
        """
        Обновляет только название клиники. Не затирает type/is_active/city.
        Если клиники нет — вставляет с типом и городом, определёнными по названию.
        """
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        clinic_type = detect_clinic_type(name)
        city = detect_clinic_city(name)
        await c.execute(
            "INSERT INTO clinics (clinic_id, name, type, is_active, city) "
            "VALUES (?, ?, ?, 1, ?) "
            "ON CONFLICT(clinic_id) DO UPDATE SET name = excluded.name",
            (clinic_id, name, clinic_type, city),
        )
        await c.commit()

    async def merge_doctors(self, clinic_id: str, doctors: list[Dict]):
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        # Создаём запись клиники, если её ещё нет (название будет "Unknown",
        # потом sync_clinic_names обновит его из API)
        existing_name = await self.get_clinic_name(str(clinic_id))
        if existing_name is None:
            await self.upsert_clinic(str(clinic_id), "Unknown")
        for doc in doctors:
            raw_id = doc.get("IdDoc")
            if not raw_id:
                continue
            doc_id = str(raw_id)
            doc_name = doc.get("Name")
            if not doc_name:
                continue
            specialty = doc.get("SpesialityName", "")
            await self.upsert_doctor(clinic_id, doc_id, doc_name, specialty)

    async def get_all_clinic_ids(self) -> list[str]:
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        cursor = await c.execute("SELECT clinic_id FROM clinics")
        rows = await cursor.fetchall()
        return [row["clinic_id"] for row in rows]

    async def get_clinic_name(self, clinic_id: str) -> Optional[str]:
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        cursor = await c.execute(
            "SELECT name FROM clinics WHERE clinic_id = ?", (clinic_id,)
        )
        row = await cursor.fetchone()
        return row["name"] if row else None

    async def get_all_clinic_names(self) -> dict[str, str]:
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        cursor = await c.execute("SELECT clinic_id, name FROM clinics")
        rows = await cursor.fetchall()
        return {row["clinic_id"]: row["name"] for row in rows}

    # ── Клиники: расширенные методы ─────────────────────────

    async def get_clinic_type(self, clinic_id: str) -> Optional[str]:
        """Возвращает тип клиники (adult/child/all)."""
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        cursor = await c.execute(
            "SELECT type FROM clinics WHERE clinic_id = ?", (clinic_id,)
        )
        row = await cursor.fetchone()
        return row["type"] if row else None

    async def get_clinic_discovery_patients(self, clinic_id: str) -> tuple[str, str]:
        """
        Возвращает per-клиника discovery пациентов (adult, child).
        Если для клиники не заданы свои пациенты — возвращает ('', '').
        """
        c = self._conn
        if c is None:
            return ("", "")
        cursor = await c.execute(
            "SELECT discovery_patient_adult, discovery_patient_child FROM clinics WHERE clinic_id = ?",
            (clinic_id,),
        )
        row = await cursor.fetchone()
        if row:
            return (
                row["discovery_patient_adult"] or "",
                row["discovery_patient_child"] or "",
            )
        return ("", "")

    async def get_active_clinics(self) -> list[dict]:
        """Возвращает список активных клиник с полными данными (включая city)."""
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        cursor = await c.execute(
            "SELECT clinic_id, name, type, is_active, city FROM clinics WHERE is_active = 1"
        )
        rows = await cursor.fetchall()
        return [
            {
                "clinic_id": row["clinic_id"],
                "name": row["name"],
                "type": row["type"],
                "is_active": row["is_active"],
                "city": row["city"] or "",
            }
            for row in rows
        ]

    async def get_distinct_cities(self) -> list[str]:
        """Возвращает отсортированный список уникальных городов активных клиник."""
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        cursor = await c.execute(
            "SELECT DISTINCT city FROM clinics WHERE is_active = 1 AND city != '' ORDER BY city"
        )
        rows = await cursor.fetchall()
        return [row["city"] for row in rows]

    # ── Сидирование данными из fallback-констант ────────────

    async def seed_specialty_aliases_from_fallback(self):
        """
        Заполняет таблицу specialty_aliases из SPECIALTY_ALIASES, если она пуста.
        """
        c = self._conn
        if c is None:
            return
        try:
            cursor = await c.execute("SELECT COUNT(*) as cnt FROM specialty_aliases")
            row = await cursor.fetchone()
            if row and row["cnt"] > 0:
                return  # уже есть данные

            from utils.helpers import SPECIALTY_ALIASES

            for full_name, short_name in SPECIALTY_ALIASES.items():
                await self.upsert_specialty_alias(full_name, short_name)
            logger.info(
                f"Таблица specialty_aliases заполнена из SPECIALTY_ALIASES ({len(SPECIALTY_ALIASES)} записей)"
            )
        except Exception as e:
            logger.warning(f"Не удалось заполнить specialty_aliases из fallback: {e}")

    async def seed_config_from_defaults(self):
        """
        Заполняет таблицу config дефолтными значениями из settings, если она пуста.
        """
        c = self._conn
        if c is None:
            return
        try:
            cursor = await c.execute("SELECT COUNT(*) as cnt FROM config")
            row = await cursor.fetchone()
            if row and row["cnt"] > 0:
                return  # уже есть данные

            from config import settings as s

            defaults = {
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
            }

            for key, value in defaults.items():
                await self.set_config(key, value)
            logger.info(
                f"Таблица config заполнена дефолтными значениями ({len(defaults)} записей)"
            )
        except Exception as e:
            logger.warning(f"Не удалось заполнить config из defaults: {e}")

    async def get_active_clinic_ids(self) -> list[str]:
        """Возвращает список clinic_id активных клиник (is_active = 1)."""
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        cursor = await c.execute("SELECT clinic_id FROM clinics WHERE is_active = 1")
        rows = await cursor.fetchall()
        return [row["clinic_id"] for row in rows]

    # ── Config (key-value) ──────────────────────────────────

    async def get_config(self, key: str, default: str = "") -> str:
        """Возвращает значение конфига по ключу."""
        c = self._conn
        if c is None:
            return default
        cursor = await c.execute("SELECT value FROM config WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return row["value"] if row else default

    async def set_config(self, key: str, value: str):
        """Устанавливает значение конфига."""
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        await c.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            (key, value),
        )
        await c.commit()

    async def get_all_config(self) -> dict[str, str]:
        """Возвращает все конфиги как dict."""
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        cursor = await c.execute("SELECT key, value FROM config")
        rows = await cursor.fetchall()
        return {row["key"]: row["value"] for row in rows}

    # ── Specialty Aliases ───────────────────────────────────

    async def get_all_specialty_aliases(self) -> dict[str, str]:
        """Возвращает все псевдонимы специальностей."""
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        cursor = await c.execute("SELECT full_name, short_name FROM specialty_aliases")
        rows = await cursor.fetchall()
        return {row["full_name"]: row["short_name"] for row in rows}

    async def upsert_specialty_alias(self, full_name: str, short_name: str):
        """Добавляет или обновляет псевдоним специальности."""
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        await c.execute(
            "INSERT OR REPLACE INTO specialty_aliases (full_name, short_name) VALUES (?, ?)",
            (full_name, short_name),
        )
        await c.commit()
