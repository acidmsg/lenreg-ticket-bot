"""
Репозиторий экранов чата: таблица ``user_chat_screen``.

Экран — одно сообщение на пользователя и вид экрана (``kind = 'monitor'``).
Запись обслуживается отдельно от ``user_last_messages``: ключ ``(uid, kind)``
не разбирается ``update_user()`` и не перезаписывается массово.
"""

from __future__ import annotations

from aiosqlite import Row

from src.database.base_repo import BaseRepository
from src.database.types import ScreenRecord

# Список колонок вынесен в константу, чтобы SELECT-запросы не расходились.
_COLUMNS = (
    "uid, kind, chat_id, msg_id, content_type, render_hash, last_seen_ts, updated_at"
)


def _row_to_record(row: Row) -> ScreenRecord:
    """Преобразует строку выборки ``aiosqlite.Row`` в ``ScreenRecord``."""
    record: ScreenRecord = {
        "uid": int(row["uid"]),
        "kind": str(row["kind"]),
        "chat_id": int(row["chat_id"]),
        "msg_id": int(row["msg_id"]),
        "content_type": str(row["content_type"]),
        "render_hash": str(row["render_hash"]),
        "last_seen_ts": int(row["last_seen_ts"]),
        "updated_at": int(row["updated_at"]),
    }
    return record


class ScreenRepository(BaseRepository):
    """CRUD-операции с записями экрана чата."""

    async def get_screen(self, uid: int, kind: str) -> ScreenRecord | None:
        """Возвращает запись экрана или ``None``, если экрана нет."""
        cursor = await self._c.execute(
            f"SELECT {_COLUMNS} FROM user_chat_screen WHERE uid = ? AND kind = ?",
            (uid, kind),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_record(row)

    async def upsert_screen(self, record: ScreenRecord) -> None:
        """Создаёт или перезаписывает запись экрана (идемпотентно).

        Повторный вызов с теми же значениями не создаёт дубль: конфликт по
        ``(uid, kind)`` разрешается обновлением остальных колонок.
        """
        await self._c.execute(
            "INSERT INTO user_chat_screen "
            f"({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(uid, kind) DO UPDATE SET "
            "chat_id = excluded.chat_id, "
            "msg_id = excluded.msg_id, "
            "content_type = excluded.content_type, "
            "render_hash = excluded.render_hash, "
            "last_seen_ts = excluded.last_seen_ts, "
            "updated_at = excluded.updated_at",
            (
                record["uid"],
                record["kind"],
                record["chat_id"],
                record["msg_id"],
                record["content_type"],
                record["render_hash"],
                record["last_seen_ts"],
                record["updated_at"],
            ),
        )
        await self._c.commit()

    async def delete_screen(self, uid: int, kind: str) -> None:
        """Удаляет запись экрана; отсутствие записи ошибкой не считается."""
        await self._c.execute(
            "DELETE FROM user_chat_screen WHERE uid = ? AND kind = ?", (uid, kind)
        )
        await self._c.commit()

    async def list_stale_screens(
        self, before_ts: int, kind: str | None = None
    ) -> list[ScreenRecord]:
        """Записи с ``updated_at`` меньше порога (TTL-выборка для очистки).

        Args:
            before_ts: Порог Unix-времени в секундах (строгое «меньше»).
            kind: Ограничить выборку одним видом экрана; ``None`` — все виды.

        Returns:
            Список записей в порядке возрастания ``updated_at``.
        """
        if kind is None:
            cursor = await self._c.execute(
                f"SELECT {_COLUMNS} FROM user_chat_screen "
                "WHERE updated_at < ? ORDER BY updated_at",
                (before_ts,),
            )
        else:
            cursor = await self._c.execute(
                f"SELECT {_COLUMNS} FROM user_chat_screen "
                "WHERE updated_at < ? AND kind = ? ORDER BY updated_at",
                (before_ts, kind),
            )
        rows = await cursor.fetchall()
        return [_row_to_record(row) for row in rows]
