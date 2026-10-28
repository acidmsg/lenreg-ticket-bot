"""Базовый класс для всех репозиториев базы данных."""

from typing import cast

import aiosqlite

from src.database.connection import DatabaseConnection


class BaseRepository:
    """Общий функционал для всех репозиториев: хранение соединения, доступ к курсору."""

    def __init__(self, db_conn: DatabaseConnection) -> None:
        self._db_conn: DatabaseConnection = db_conn

    @property
    def _c(self) -> aiosqlite.Connection:
        """Возвращает активное соединение с БД или выбрасывает RuntimeError."""
        c = self._db_conn.conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        return c

    async def _fetch_text_value(
        self, sql: str, params: tuple[object, ...], column: str
    ) -> str | None:
        """Возвращает текстовое значение одной колонки из первой строки выборки.

        Единая реализация чтения «одно значение по ключу» для репозиториев.
        SQL передаётся целиком: имена таблиц и колонок в запрос не подставляются.

        Args:
            sql: Полный SELECT-запрос с плейсхолдерами.
            params: Значения для плейсхолдеров запроса.
            column: Имя колонки, значение которой нужно вернуть.

        Returns:
            Значение колонки или ``None``, если запись не найдена либо
            в колонке хранится ``NULL``.
        """
        cursor = await self._c.execute(sql, params)
        row = await cursor.fetchone()
        if row is None:
            return None
        return cast("str | None", row[column])
