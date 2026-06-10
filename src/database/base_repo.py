"""Базовый класс для всех репозиториев базы данных."""

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
