"""
Единый SQLite-движок для хранения данных.
Заменяет JSON-файлы (users_config.json, doctors.json).
Обеспечивает:
- атомарные транзакции
- автоматическую миграцию из JSON при первом запуске
- единый пул соединений
"""

import json
import logging
import os
from typing import Any, Dict, Optional

import aiosqlite

logger = logging.getLogger(__name__)


class Database:
    """SQLite-обёртка с автоматическим созданием таблиц и миграцией из JSON."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    # ── Управление соединением ──────────────────────────────
    async def connect(self):
        """Открыть соединение и создать таблицы."""

        # Убедимся, что каталог для файла базы данных существует
        data_dir = os.path.dirname(self.db_path)
        if data_dir and not os.path.exists(data_dir):
            try:
                os.makedirs(data_dir)
                logger.info(f"Каталог '{data_dir}' создан для базы данных.")
            except OSError as e:
                logger.error(f"Не удалось создать каталог '{data_dir}': {e}")
                raise

        # Проверяем, существовал ли файл БД до попытки подключения.
        # aiosqlite.connect() создаст его, если нет.
        db_file_existed = os.path.exists(self.db_path)

        try:
            self._conn = await aiosqlite.connect(self.db_path)
            # noinspection PyTypeChecker
            c = self._conn
            if c is None:
                raise RuntimeError("Database connection not initialized")

            logger.info(f"Соединение с базой данных '{self.db_path}' установлено.")

            # Если файл БД был только что создан, выполним минимальный запрос,
            # чтобы убедиться, что он распознается как база данных.
            if not db_file_existed:
                try:
                    await c.execute(
                        "SELECT 1"
                    )  # Простой запрос для инициализации заголовка БД
                    await c.commit()
                    logger.info(
                        f"Новая база данных '{self.db_path}' успешно инициализирована простым запросом."
                    )
                except Exception as e:
                    logger.error(
                        f"Не удалось выполнить начальный запрос к новой базе данных '{self.db_path}': {e}"
                    )
                    raise

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
CREATE TABLE IF NOT EXISTS users (
uid                 TEXT PRIMARY KEY,
patients            TEXT NOT NULL DEFAULT '{}',
monitoring          TEXT NOT NULL DEFAULT '{}',
last_messages       TEXT NOT NULL DEFAULT '{}',
last_notification_id INTEGER,
extra               TEXT NOT NULL DEFAULT '{}'
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
CREATE TABLE IF NOT EXISTS schema_version (
version             INTEGER PRIMARY KEY
);
""")
        await c.commit()

    # ── Миграция из JSON ────────────────────────────────────
    async def migrate_from_json(
        self,
        users_json_path: str,
        doctors_json_path: str,
    ):
        """
        Перенести данные из JSON-файлов в SQLite.
        Безопасно: проверяет, есть ли уже данные в базе.
        """
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        cursor = await c.execute("SELECT COUNT(*) FROM users")
        row = await cursor.fetchone()
        if row and row[0] > 0:
            logger.info("База данных уже содержит записи, миграция JSON пропущена")
            return
        logger.info("Запуск миграции из JSON в SQLite…")

        # ── Пользователи ──
        if os.path.exists(users_json_path):
            with open(users_json_path, "r", encoding="utf-8") as f:
                users_data: Dict = json.load(f)
            for uid, payload in users_data.items():
                patients = json.dumps(payload.get("patients", {}), ensure_ascii=False)
                monitoring = json.dumps(
                    payload.get("monitoring", {}), ensure_ascii=False
                )
                last_msgs = json.dumps(
                    payload.get("last_messages", {}), ensure_ascii=False
                )
                notif_id = payload.get("last_notification_id")
                await c.execute(
                    """INSERT OR REPLACE INTO users
                    (uid, patients, monitoring, last_messages, last_notification_id)
                    VALUES (?, ?, ?, ?, ?)""",
                    (uid, patients, monitoring, last_msgs, notif_id),
                )
            logger.info("Мигрировано пользователей: %d", len(users_data))

        # ── Врачи ──
        if os.path.exists(doctors_json_path):
            with open(doctors_json_path, "r", encoding="utf-8") as f:
                doctors_data: Dict = json.load(f)
            for clinic_id, clinic_info in doctors_data.items():
                clinic_name = clinic_info.get("name", "Unknown")
                await c.execute(
                    "INSERT OR REPLACE INTO clinics (clinic_id, name) VALUES (?, ?)",
                    (clinic_id, clinic_name),
                )
                for doc_id, doc_info in clinic_info.get("doctors", {}).items():
                    await c.execute(
                        """INSERT OR REPLACE INTO doctors
                        (clinic_id, doctor_id, name, specialty)
                        VALUES (?, ?, ?, ?)""",
                        (
                            clinic_id,
                            doc_id,
                            doc_info.get("name", ""),
                            doc_info.get("specialty", ""),
                        ),
                    )
            logger.info("Мигрировано клиник: %d", len(doctors_data))
        await c.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (1)")
        await c.commit()
        logger.info("Миграция из JSON завершена")

    # ── Пользователи ────────────────────────────────────────
    async def get_user(self, uid: str) -> Optional[Dict[str, Any]]:
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        cursor = await c.execute("SELECT * FROM users WHERE uid = ?", (uid,))
        row = await cursor.fetchone()
        if row is None:
            return None
        result = {
            "patients": json.loads(row["patients"]),
            "monitoring": json.loads(row["monitoring"]),
            "last_messages": json.loads(row["last_messages"]),
            "last_notification_id": row["last_notification_id"],
        }
        extra = (
            json.loads(row["extra"]) if row["extra"] and row["extra"] != "{}" else {}
        )
        result.update(extra)
        return result

    async def ensure_user(self, uid: str) -> Dict[str, Any]:
        user = await self.get_user(uid)
        if user is not None:
            return user
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        await c.execute(
            "INSERT OR IGNORE INTO users (uid) VALUES (?)",
            (uid,),
        )
        await c.commit()
        return {
            "patients": {},
            "monitoring": {},
            "last_messages": {},
            "last_notification_id": None,
        }

    async def update_extra(self, uid: str, extra: Dict[str, Any]):
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        current_extra = {}
        cursor = await c.execute("SELECT extra FROM users WHERE uid = ?", (uid,))
        row = await cursor.fetchone()
        if row and row["extra"] and row["extra"] != "{}":
            current_extra = json.loads(row["extra"])
        current_extra.update(extra)
        await c.execute(
            "UPDATE users SET extra = ? WHERE uid = ?",
            (json.dumps(current_extra, ensure_ascii=False), uid),
        )
        await c.commit()

    _ALLOWED_FIELDS = frozenset(
        {
            "patients",
            "monitoring",
            "last_messages",
            "last_notification_id",
            "extra",
        }
    )

    async def update_user_field(self, uid: str, field: str, value: Any):
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        if field not in self._ALLOWED_FIELDS:
            raise ValueError(f"Field '{field}' is not allowed for direct update")
        await c.execute(
            f"UPDATE users SET [{field}] = ? WHERE uid = ?",
            (json.dumps(value, ensure_ascii=False), uid),
        )
        await c.commit()

    async def set_last_notification_id(self, uid: str, msg_id: int):
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        await c.execute(
            "UPDATE users SET last_notification_id = ? WHERE uid = ?",
            (msg_id, uid),
        )
        await c.commit()

    async def get_all_user_ids(self) -> list[str]:
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        cursor = await c.execute("SELECT uid FROM users")
        rows = await cursor.fetchall()
        return [row["uid"] for row in rows]

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
