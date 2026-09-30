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
