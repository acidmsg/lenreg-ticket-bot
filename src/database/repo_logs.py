"""
Репозиторий логов мониторинга: таблица monitoring_log.
"""

from __future__ import annotations

from loguru import logger

from src.database.base_repo import BaseRepository
from src.database.types import MonitoringLogEntry


class LogRepository(BaseRepository):
    """CRUD-операции с логами мониторинга (таблица monitoring_log)."""

    async def add_monitoring_log(
        self,
        uid: str,
        p_id: str,
        d_id: str,
        doctor_name: str,
        patient_name: str,
        specialty: str,
        clinic_name: str,
        slot_date: str,
        status: str,
        ts: float,
    ) -> None:
        """Добавляет запись в лог мониторинга (появление/исчезновение слота)."""
        await self._c.execute(
            """INSERT INTO monitoring_log
               (uid, p_id, d_id, doctor_name, patient_name, specialty,
                clinic_name, slot_date, status, ts)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                uid,
                p_id,
                d_id,
                doctor_name,
                patient_name,
                specialty,
                clinic_name,
                slot_date,
                status,
                ts,
            ),
        )
        await self._c.commit()

    async def get_user_monitoring_logs(
        self, uid: str, limit: int = 5000, offset: int = 0
    ) -> list[MonitoringLogEntry]:
        """Возвращает логи мониторинга для пользователя, отсортированные по времени."""
        cursor = await self._c.execute(
            "SELECT id, uid, p_id, d_id, doctor_name, patient_name, "
            "specialty, clinic_name, slot_date, status, ts "
            "FROM monitoring_log "
            "WHERE uid = ? ORDER BY ts DESC LIMIT ? OFFSET ?",
            (uid, limit, offset),
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": row["id"],
                "uid": row["uid"],
                "p_id": row["p_id"],
                "d_id": row["d_id"],
                "doctor_name": row["doctor_name"],
                "patient_name": row["patient_name"],
                "specialty": row["specialty"],
                "clinic_name": row["clinic_name"],
                "slot_date": row["slot_date"],
                "status": row["status"],
                "ts": row["ts"],
            }
            for row in rows
        ]

    async def get_user_monitoring_logs_count(self, uid: str) -> int:
        """Возвращает количество записей лога для пользователя."""
        try:
            c = self._db_conn.conn
            if c is None:
                return 0
            cursor = await c.execute(
                "SELECT COUNT(*) as cnt FROM monitoring_log WHERE uid = ?",
                (uid,),
            )
            row = await cursor.fetchone()
            return row["cnt"] if row else 0
        except Exception:
            logger.debug(
                "Ошибка при get_user_monitoring_logs_count uid={}",
                uid,
                exc_info=True,
            )
            return 0

    async def get_all_monitoring_logs(
        self,
        limit: int = 50,
        offset: int = 0,
        uid: str | None = None,
        status: str | None = None,
    ) -> list[MonitoringLogEntry]:
        """Возвращает логи мониторинга с пагинацией и фильтрацией."""
        cursor = await self._c.execute(
            "SELECT id, uid, p_id, d_id, doctor_name, patient_name, "
            "specialty, clinic_name, slot_date, status, ts "
            "FROM monitoring_log "
            "WHERE (uid = ? OR ? IS NULL) "
            "AND (status = ? OR ? IS NULL) "
            "ORDER BY ts DESC LIMIT ? OFFSET ?",
            (uid, uid, status, status, limit, offset),
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": row["id"],
                "uid": row["uid"],
                "p_id": row["p_id"],
                "d_id": row["d_id"],
                "doctor_name": row["doctor_name"],
                "patient_name": row["patient_name"],
                "specialty": row["specialty"],
                "clinic_name": row["clinic_name"],
                "slot_date": row["slot_date"],
                "status": row["status"],
                "ts": row["ts"],
            }
            for row in rows
        ]

    async def get_all_monitoring_logs_count(
        self, uid: str | None = None, status: str | None = None
    ) -> int:
        """Возвращает количество записей лога мониторинга (с фильтрами)."""
        try:
            c = self._db_conn.conn
            if c is None:
                return 0
            cursor = await c.execute(
                "SELECT COUNT(*) as cnt FROM monitoring_log "
                "WHERE (uid = ? OR ? IS NULL) "
                "AND (status = ? OR ? IS NULL)",
                (uid, uid, status, status),
            )
            row = await cursor.fetchone()
            return row["cnt"] if row else 0
        except Exception:
            logger.debug(
                "Ошибка при get_all_monitoring_logs_count uid={} status={}",
                uid,
                status,
                exc_info=True,
            )
            return 0
