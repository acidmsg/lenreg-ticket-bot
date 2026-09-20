"""Репозиторий журнала действий администратора: таблица audit_log."""

from __future__ import annotations

import json
import time
from typing import Any

from src.database.base_repo import BaseRepository
from src.database.types import AuditLogEntry


def _escape_like(value: str) -> str:
    """Экранирует спецсимволы LIKE (``%``, ``_``, ``\\``) для буквального поиска.

    Args:
        value: Пользовательская подстрока.

    Returns:
        Подстрока, безопасная для шаблона LIKE с ``ESCAPE '\\'``.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class AuditRepository(BaseRepository):
    """Запись и выборка действий администратора (таблица audit_log)."""

    async def add_event(
        self,
        actor: str,
        action: str,
        target: str = "",
        payload: dict[str, Any] | None = None,
        ts: float | None = None,
    ) -> None:
        """Добавляет запись в журнал действий.

        Args:
            actor: Кто выполнил действие (логин дашборда, ``system``, ``bot``).
            action: Машиночитаемый код действия (``login``, ``backup_restore``…).
            target: Объект действия (файл бэкапа, uid, ключ настройки).
            payload: Дополнительные данные (сериализуются в JSON).
            ts: Время события; по умолчанию — текущее.
        """
        await self._c.execute(
            """INSERT INTO audit_log (ts, actor, action, target, payload_json)
               VALUES (?, ?, ?, ?, ?)""",
            (
                ts if ts is not None else time.time(),
                actor or "",
                action,
                target or "",
                json.dumps(payload or {}, ensure_ascii=False),
            ),
        )
        await self._c.commit()

    async def list_events(
        self,
        limit: int = 100,
        offset: int = 0,
        actor: str | None = None,
        action: str | None = None,
        since: float | None = None,
        until: float | None = None,
        search: str | None = None,
    ) -> list[AuditLogEntry]:
        """Возвращает записи журнала (новые первыми) с фильтрами.

        Args:
            limit: Размер страницы.
            offset: Смещение.
            actor: Фильтр по автору действия.
            action: Фильтр по коду действия.
            since: Нижняя граница времени (Unix-время).
            until: Верхняя граница времени (Unix-время).
            search: Подстрока по target/payload/action.

        Returns:
            Список записей журнала.
        """
        where, params = self._build_filter(actor, action, since, until, search)
        cursor = await self._c.execute(
            "SELECT id, ts, actor, action, target, payload_json FROM audit_log "
            f"{where} ORDER BY ts DESC, id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )
        rows = await cursor.fetchall()
        return [
            AuditLogEntry(
                id=row[0],
                ts=row[1],
                actor=row[2],
                action=row[3],
                target=row[4],
                payload_json=row[5],
            )
            for row in rows
        ]

    async def count_events(
        self,
        actor: str | None = None,
        action: str | None = None,
        since: float | None = None,
        until: float | None = None,
        search: str | None = None,
    ) -> int:
        """Считает записи журнала с теми же фильтрами, что ``list_events``."""
        where, params = self._build_filter(actor, action, since, until, search)
        cursor = await self._c.execute(
            f"SELECT COUNT(*) FROM audit_log {where}", params
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def distinct_actions(self) -> list[str]:
        """Возвращает список встречающихся в журнале кодов действий."""
        cursor = await self._c.execute(
            "SELECT DISTINCT action FROM audit_log ORDER BY action"
        )
        return [row[0] for row in await cursor.fetchall()]

    async def distinct_actors(self) -> list[str]:
        """Возвращает список встречающихся в журнале авторов действий."""
        cursor = await self._c.execute(
            "SELECT DISTINCT actor FROM audit_log ORDER BY actor"
        )
        return [row[0] for row in await cursor.fetchall() if row[0]]

    @staticmethod
    def _build_filter(
        actor: str | None,
        action: str | None,
        since: float | None,
        until: float | None,
        search: str | None,
    ) -> tuple[str, list[Any]]:
        """Собирает SQL-условие и параметры для фильтров журнала."""
        clauses: list[str] = []
        params: list[Any] = []
        if actor:
            clauses.append("actor = ?")
            params.append(actor)
        if action:
            clauses.append("action = ?")
            params.append(action)
        if since is not None:
            clauses.append("ts >= ?")
            params.append(since)
        if until is not None:
            clauses.append("ts <= ?")
            params.append(until)
        if search:
            clauses.append(
                "(target LIKE ? ESCAPE '\\' OR payload_json LIKE ? ESCAPE '\\' "
                "OR action LIKE ? ESCAPE '\\')"
            )
            like = f"%{_escape_like(search)}%"
            params.extend([like, like, like])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return where, params
