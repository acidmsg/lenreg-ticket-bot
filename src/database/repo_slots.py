"""
Репозиторий кэша талонов (слотов) по клиникам (PERF-CACHE, T3).

Талоны (``CountFreeTicket``/``NearestDate``) меняются часто, поэтому хранятся
отдельно от реестра врачей (таблица ``doctors``, TTL ``doctor_scan_ttl_hours``)
в таблице ``clinic_slots`` со своим коротким TTL (``slot_cache_ttl_minutes``).
Запись бывает двух видов: полная (``replace_clinic_slots``) перезаписывает
набор врачей клиники целиком, чтобы выпавший из свежего ответа портала врач
не остался со старыми талонами; частичная (``upsert_clinic_slots``) обновляет
только переданных врачей и сохраняет остальных (точечное обновление, T4).

Поле ``free_tickets`` заполняется из двух портальных источников: полный обход
клиники (``/doctor_list/``) даёт ``CountFreeTicket``, точечное обновление
(``/appointment_list/``, T4) — число доступных слотов. Счётчики близки, но не
тождественны, поэтому значение врача определяется последним обновившим его
путём: расхождение осознанное, чтобы сверка не считала его ошибкой.
"""

from __future__ import annotations

import time
from typing import Any

from src.database.base_repo import BaseRepository


class SlotsRepository(BaseRepository):
    """CRUD-операции с кэшем талонов (таблица clinic_slots)."""

    async def replace_clinic_slots(
        self, clinic_id: str, rows: list[dict[str, Any]], ts: float | None = None
    ) -> int:
        """Перезаписывает набор талонов клиники одним заходом.

        Прежние записи клиники удаляются, затем вставляются полученные: так
        врач, пропавший из свежего ответа портала, не остаётся в кэше со
        старыми талонами. Записи без ``doctor_id`` пропускаются.

        Args:
            clinic_id: ID клиники.
            rows: Талоны с ключами ``doctor_id``, ``free_tickets``,
                ``nearest_date``.
            ts: Метка свежести (по умолчанию текущее время).

        Returns:
            Сколько талонов записано.
        """
        timestamp = time.time() if ts is None else ts
        cid = str(clinic_id)
        prepared = self._prepare_rows(cid, rows, timestamp)

        c = self._c
        try:
            await c.execute("DELETE FROM clinic_slots WHERE clinic_id = ?", (cid,))
            if prepared:
                await c.executemany(
                    "INSERT INTO clinic_slots "
                    "(clinic_id, doctor_id, free_tickets, nearest_date, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    prepared,
                )
            await c.commit()
        except Exception:
            # Сбой вставки не должен оставлять осиротевший DELETE: иначе его
            # зафиксирует первый же commit соседнего вызова на этом соединении.
            await c.rollback()
            raise
        return len(prepared)

    async def upsert_clinic_slots(
        self, clinic_id: str, rows: list[dict[str, Any]], ts: float | None = None
    ) -> int:
        """Добавляет или обновляет талоны указанных врачей клиники (T4).

        В отличие от ``replace_clinic_slots``, записи врачей, не попавших в
        ``rows``, сохраняются: обновляются только переданные ``doctor_id``.
        Применяется при точечном опросе конкретных врачей, когда полный batch
        по клинике не нужен. Записи без ``doctor_id`` пропускаются.

        Args:
            clinic_id: ID клиники.
            rows: Талоны с ключами ``doctor_id``, ``free_tickets``,
                ``nearest_date``.
            ts: Метка свежести (по умолчанию текущее время).

        Returns:
            Сколько талонов записано.
        """
        timestamp = time.time() if ts is None else ts
        cid = str(clinic_id)
        prepared = self._prepare_rows(cid, rows, timestamp)
        if not prepared:
            return 0

        c = self._c
        try:
            await c.executemany(
                "INSERT INTO clinic_slots "
                "(clinic_id, doctor_id, free_tickets, nearest_date, updated_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(clinic_id, doctor_id) DO UPDATE SET "
                "free_tickets = excluded.free_tickets, "
                "nearest_date = excluded.nearest_date, "
                "updated_at = excluded.updated_at",
                prepared,
            )
            await c.commit()
        except Exception:
            # Сбой вставки не должен оставлять незавершённую транзакцию: иначе
            # её зафиксирует первый же commit соседнего вызова на этом соединении.
            await c.rollback()
            raise
        return len(prepared)

    @staticmethod
    def _prepare_rows(
        clinic_id: str, rows: list[dict[str, Any]], timestamp: float
    ) -> list[tuple[str, str, int, str, float]]:
        """Готовит строки талонов к записи, отбрасывая записи без ``doctor_id``."""
        return [
            (
                clinic_id,
                str(row.get("doctor_id", "")),
                int(row.get("free_tickets", 0) or 0),
                str(row.get("nearest_date") or ""),
                timestamp,
            )
            for row in rows
            if str(row.get("doctor_id", ""))
        ]

    async def get_clinic_slots(self, clinic_id: str) -> list[dict[str, Any]]:
        """Возвращает талоны клиники списком (ключ — ``doctor_id``).

        ``nearest_date`` отдаётся строкой; пустая строка означает «даты нет»
        (вызывающий приводит её к ``None`` для контракта ответа API).
        """
        cursor = await self._c.execute(
            "SELECT doctor_id, free_tickets, nearest_date, updated_at "
            "FROM clinic_slots WHERE clinic_id = ?",
            (str(clinic_id),),
        )
        rows = await cursor.fetchall()
        return [
            {
                "doctor_id": row["doctor_id"],
                "free_tickets": int(row["free_tickets"] or 0),
                "nearest_date": row["nearest_date"] or "",
                "updated_at": float(row["updated_at"] or 0),
            }
            for row in rows
        ]

    async def get_clinic_slots_state(self, clinic_id: str) -> float:
        """Возвращает свежесть кэша талонов клиники: ``max(updated_at)``.

        Для клиники без записей талонов возвращает ``0.0`` — метку «никогда».
        """
        cursor = await self._c.execute(
            "SELECT MAX(updated_at) AS ts FROM clinic_slots WHERE clinic_id = ?",
            (str(clinic_id),),
        )
        row = await cursor.fetchone()
        return float(row["ts"] or 0) if row else 0.0

    async def record_clinic_slot_scan(
        self,
        clinic_id: str,
        *,
        doctor_count: int,
        free_ticket_count: int,
        ts: float | None = None,
    ) -> None:
        """Записывает агрегат одного полного скана талонов клиники.

        История нужна для аналитики всплесков: ``clinic_slots`` хранит
        только последний снимок, а эта таблица — временной ряд.
        """
        timestamp = time.time() if ts is None else ts
        c = self._c
        try:
            await c.execute(
                "INSERT INTO clinic_slot_scans "
                "(clinic_id, scanned_at, doctor_count, free_ticket_count) "
                "VALUES (?, ?, ?, ?)",
                (str(clinic_id), timestamp, int(doctor_count), int(free_ticket_count)),
            )
            await c.commit()
        except Exception:
            await c.rollback()
            raise

    async def get_clinic_slot_scan_history(
        self, clinic_id: str, *, hours: int = 24 * 30, limit: int = 5000
    ) -> list[dict[str, Any]]:
        """Возвращает сырые точки сканов клиники за последние ``hours`` часов."""
        since = time.time() - hours * 3600
        cursor = await self._c.execute(
            "SELECT scanned_at, doctor_count, free_ticket_count "
            "FROM clinic_slot_scans "
            "WHERE clinic_id = ? AND scanned_at >= ? "
            "ORDER BY scanned_at ASC LIMIT ?",
            (str(clinic_id), since, limit),
        )
        rows = await cursor.fetchall()
        return [
            {
                "scanned_at": float(row["scanned_at"] or 0),
                "doctor_count": int(row["doctor_count"] or 0),
                "free_ticket_count": int(row["free_ticket_count"] or 0),
            }
            for row in rows
        ]

    async def get_clinic_slot_scan_summary(
        self, clinic_id: str, *, hours: int = 24 * 30
    ) -> list[dict[str, Any]]:
        """Возвращает почасовую агрегацию сканов клиники за ``hours`` часов."""
        since = time.time() - hours * 3600
        cursor = await self._c.execute(
            "SELECT CAST(scanned_at / 3600 AS INTEGER) * 3600 AS bucket_at, "
            "MAX(free_ticket_count) AS max_free_ticket_count, "
            "MIN(free_ticket_count) AS min_free_ticket_count, "
            "AVG(free_ticket_count) AS avg_free_ticket_count, "
            "MAX(doctor_count) AS doctor_count, COUNT(*) AS scan_count "
            "FROM clinic_slot_scans "
            "WHERE clinic_id = ? AND scanned_at >= ? "
            "GROUP BY bucket_at ORDER BY bucket_at ASC",
            (str(clinic_id), since),
        )
        rows = await cursor.fetchall()
        return [
            {
                "bucket_at": int(row["bucket_at"] or 0),
                "max_free_ticket_count": int(row["max_free_ticket_count"] or 0),
                "min_free_ticket_count": int(row["min_free_ticket_count"] or 0),
                "avg_free_ticket_count": float(row["avg_free_ticket_count"] or 0),
                "doctor_count": int(row["doctor_count"] or 0),
                "scan_count": int(row["scan_count"] or 0),
            }
            for row in rows
        ]
