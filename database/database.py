"""
Единый SQLite-движок для хранения данных.
"""

import json
import logging
import os
from typing import Any, Dict, Optional

import aiosqlite

from config import CLINICS_REGISTRY

logger = logging.getLogger(__name__)


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
name                TEXT NOT NULL DEFAULT 'Unknown'
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
CREATE TABLE IF NOT EXISTS schema_version (
version             INTEGER PRIMARY KEY
);
""")
        await c.commit()

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
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        await c.execute(
            "INSERT OR REPLACE INTO clinics (clinic_id, name) VALUES (?, ?)",
            (clinic_id, name),
        )
        await c.commit()

    async def merge_doctors(self, clinic_id: str, doctors: list[Dict]):
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        # Не перезаписываем название клиники, если оно уже установлено (из API)
        existing_name = await self.get_clinic_name(str(clinic_id))
        if existing_name is None:
            clinic_info = CLINICS_REGISTRY.get(str(clinic_id))
            clinic_name = clinic_info.name if clinic_info else "Unknown"
            await self.upsert_clinic(str(clinic_id), clinic_name)
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
