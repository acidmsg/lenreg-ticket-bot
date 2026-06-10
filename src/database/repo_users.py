"""
Репозиторий пользователей: пациенты, last_messages, агрегация UserData.
"""

from __future__ import annotations

import json

from loguru import logger

from src.database.base_repo import BaseRepository
from src.database.types import (
    LastMessageEntry,
    MonitoringEntry,
    PatientInfo,
    UserData,
)


class UserRepository(BaseRepository):
    """CRUD-операции с пользователями: пациенты, last_messages."""

    # ── Пользователи (агрегация) ─────────────────────────────

    async def get_user(self, uid: str) -> UserData | None:
        """Возвращает все данные пользователя: пациенты, мониторинг, last_messages."""
        patients = await self.get_user_patients(uid)
        monitoring = await self._get_user_monitoring(uid)
        lm_cursor = await self._c.execute(
            "SELECT p_id, d_id, msg_id, ts FROM user_last_messages WHERE uid = ?",
            (uid,),
        )
        lm_rows = await lm_cursor.fetchall()
        last_messages: dict[str, LastMessageEntry] = {}
        for lmr in lm_rows:
            key = f"{lmr['p_id']}_{lmr['d_id']}"
            last_messages[key] = {"msg_id": lmr["msg_id"], "ts": lmr["ts"]}

        if not patients and not monitoring and not last_messages:
            return None

        user_data: UserData = {
            "patients": patients,
            "monitoring": monitoring,
            "last_messages": last_messages,
        }
        return user_data

    async def get_all_user_ids(self) -> list[str]:
        """Возвращает все уникальные uid из таблиц пользователей."""
        cursor = await self._c.execute("""
            SELECT DISTINCT uid FROM user_patients
            UNION
            SELECT DISTINCT uid FROM user_monitoring
            UNION
            SELECT DISTINCT uid FROM user_last_messages
        """)
        rows = await cursor.fetchall()
        return [row["uid"] for row in rows]

    # ── last_messages ───────────────────────────────────────

    async def set_last_message(
        self, uid: str, p_id: str, d_id: str, msg_id: int, ts: float = 0
    ) -> None:
        """Сохраняет ID последнего сообщения."""
        await self._c.execute(
            "INSERT OR REPLACE INTO user_last_messages "
            "(uid, p_id, d_id, msg_id, ts) VALUES (?, ?, ?, ?, ?)",
            (uid, p_id, d_id, msg_id, ts),
        )
        await self._c.commit()

    async def get_last_message(
        self, uid: str, p_id: str, d_id: str
    ) -> LastMessageEntry | None:
        """Возвращает запись о последнем сообщении или None."""
        try:
            c = self._db_conn.conn
            if c is None:
                return None
            cursor = await c.execute(
                "SELECT msg_id, ts FROM user_last_messages "
                "WHERE uid = ? AND p_id = ? AND d_id = ?",
                (uid, p_id, d_id),
            )
            row = await cursor.fetchone()
            if row:
                entry: LastMessageEntry = {"msg_id": row["msg_id"], "ts": row["ts"]}
                return entry
        except Exception:
            logger.debug(
                "Ошибка при get_last_message uid={} p_id={} d_id={}",
                uid,
                p_id,
                d_id,
                exc_info=True,
            )
        return None

    # ── Пациенты ────────────────────────────────────────────

    async def get_user_patients(self, uid: str) -> dict[str, PatientInfo]:
        """Возвращает словарь пациентов пользователя."""
        cursor = await self._c.execute(
            "SELECT p_id, fio, bday, alias, confirmed_clinics "
            "FROM user_patients WHERE uid = ?",
            (uid,),
        )
        rows = await cursor.fetchall()
        result: dict[str, PatientInfo] = {}
        for row in rows:
            confirmed = (
                json.loads(row["confirmed_clinics"]) if row["confirmed_clinics"] else []
            )
            p_info: PatientInfo = {
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
    ) -> None:
        """Добавляет или обновляет запись пациента."""
        if confirmed_clinics is None:
            confirmed_clinics = []
        await self._c.execute(
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
        await self._c.commit()

    async def update_patient_confirmed_clinics(
        self,
        uid: str,
        p_id: str,
        confirmed_clinics: list,
    ) -> None:
        """Обновляет список подтверждённых клиник пациента."""
        await self._c.execute(
            "UPDATE user_patients SET confirmed_clinics = ? WHERE uid = ? AND p_id = ?",
            (json.dumps(confirmed_clinics, ensure_ascii=False), uid, p_id),
        )
        await self._c.commit()

    # ── Мониторинг (внутренний, используется get_user) ──────

    async def _get_user_monitoring(
        self, uid: str
    ) -> dict[str, dict[str, MonitoringEntry]]:
        """Возвращает словарь мониторинга пользователя (для агрегации в get_user)."""
        cursor = await self._c.execute(
            "SELECT p_id, d_id, name, clinic_id, specialty, date "
            "FROM user_monitoring WHERE uid = ?",
            (uid,),
        )
        rows = await cursor.fetchall()
        result: dict[str, dict[str, MonitoringEntry]] = {}
        for row in rows:
            p_id = row["p_id"]
            if p_id not in result:
                result[p_id] = {}
            result[p_id][row["d_id"]] = {
                "name": row["name"],
                "clinic_id": row["clinic_id"],
                "specialty": row["specialty"],
                "date": row["date"],
            }
        return result
