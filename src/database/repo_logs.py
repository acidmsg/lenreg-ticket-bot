"""
Репозиторий логов мониторинга: таблица monitoring_log.
"""

from __future__ import annotations

import time
from typing import Any

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

    # ── Алерты (DASH-5) ────────────────────────────────────────

    ALERT_STATES = ("new", "acked", "resolved")

    async def list_alerts(
        self,
        limit: int = 50,
        offset: int = 0,
        uid: str | None = None,
        status: str | None = None,
        ack_status: str | None = None,
        since: float | None = None,
        until: float | None = None,
    ) -> list[MonitoringLogEntry]:
        """Алерты (записи monitoring_log) с фильтрами и пагинацией.

        Новые записи — первыми; фильтры: пользователь, тип события,
        состояние подтверждения и период.
        """
        where, params = self._alert_filter(uid, status, ack_status, since, until)
        cursor = await self._c.execute(
            "SELECT id, uid, p_id, d_id, doctor_name, patient_name, specialty, "
            "clinic_name, slot_date, status, ts, ack_status, acked_by, acked_ts "
            f"FROM monitoring_log {where} "
            "ORDER BY ts DESC, id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
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
                "ack_status": row["ack_status"],
                "acked_by": row["acked_by"],
                "acked_ts": row["acked_ts"],
            }
            for row in rows
        ]

    async def count_alerts(
        self,
        uid: str | None = None,
        status: str | None = None,
        ack_status: str | None = None,
        since: float | None = None,
        until: float | None = None,
    ) -> int:
        """Количество алертов под теми же фильтрами, что ``list_alerts``."""
        where, params = self._alert_filter(uid, status, ack_status, since, until)
        cursor = await self._c.execute(
            f"SELECT COUNT(*) AS cnt FROM monitoring_log {where}", params
        )
        row = await cursor.fetchone()
        return int(row["cnt"]) if row else 0

    async def unacked_alerts_count(self) -> int:
        """Количество неподтверждённых алертов (для бейджа в сайдбаре)."""
        cursor = await self._c.execute(
            "SELECT COUNT(*) AS cnt FROM monitoring_log WHERE ack_status = 'new'"
        )
        row = await cursor.fetchone()
        return int(row["cnt"]) if row else 0

    async def set_alerts_state(
        self, alert_ids: list[int], state: str, actor: str
    ) -> int:
        """Переводит алерты в состояние ``acked``/``resolved``.

        Args:
            alert_ids: Идентификаторы записей monitoring_log.
            state: Новое состояние (``new``/``acked``/``resolved``).
            actor: Кто изменил состояние (для журнала и записи в строке).

        Returns:
            Сколько строк реально изменилось.
        """
        if state not in self.ALERT_STATES:
            raise ValueError(f"Недопустимое состояние алерта: {state}")
        if not alert_ids:
            return 0
        placeholders = ",".join("?" for _ in alert_ids)
        cursor = await self._c.execute(
            "UPDATE monitoring_log SET ack_status = ?, acked_by = ?, acked_ts = ? "
            f"WHERE id IN ({placeholders})",
            (state, actor, time.time(), *alert_ids),
        )
        await self._c.commit()
        return int(cursor.rowcount or 0)

    @staticmethod
    def _alert_filter(
        uid: str | None,
        status: str | None,
        ack_status: str | None,
        since: float | None,
        until: float | None,
    ) -> tuple[str, list[Any]]:
        """SQL-условие и параметры фильтров алертов."""
        clauses: list[str] = []
        params: list[Any] = []
        if uid:
            clauses.append("uid = ?")
            params.append(uid)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if ack_status:
            clauses.append("ack_status = ?")
            params.append(ack_status)
        if since is not None:
            clauses.append("ts >= ?")
            params.append(since)
        if until is not None:
            clauses.append("ts <= ?")
            params.append(until)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return where, params

    async def get_slot_events_per_hour(
        self, since_ts: float
    ) -> dict[int, dict[str, int]]:
        """События слотов по часам: ``{bucket_ts: {статус: количество}}``.

        Часы считаются от ``ts`` записи (Unix-время), поэтому тренды не
        зависят от часового пояса сервера.
        """
        c = self._db_conn.conn
        if c is None:
            return {}

        cursor = await c.execute(
            "SELECT CAST(ts / 3600 AS INTEGER) * 3600 AS bucket, "
            "status, COUNT(*) AS cnt "
            "FROM monitoring_log WHERE ts >= ? "
            "GROUP BY bucket, status",
            (since_ts,),
        )
        rows = await cursor.fetchall()

        result: dict[int, dict[str, int]] = {}
        for row in rows:
            bucket = int(row["bucket"])
            result.setdefault(bucket, {})[row["status"]] = int(row["cnt"])
        return result
