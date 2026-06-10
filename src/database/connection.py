"""
Подключение к SQLite: открытие, закрытие, миграции, WAL-режим.
"""

import os

import aiofiles.os
import aiosqlite
from loguru import logger


class DatabaseConnection:
    """Управление жизненным циклом подключения к SQLite."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection | None:
        """Активное соединение с БД или None, если не установлено."""
        return self._conn

    async def connect(self) -> None:
        """Открыть соединение и создать таблицы."""
        data_dir = os.path.dirname(self.db_path)
        if data_dir and not await aiofiles.os.path.exists(data_dir):
            try:
                await aiofiles.os.makedirs(data_dir)
                logger.info("Каталог '{}' создан для базы данных.", data_dir)
            except OSError as e:
                logger.error("Не удалось создать каталог '{}': {}", data_dir, e)
                raise

        # Диагностика прав доступа к файлу БД и директории
        await self._log_permissions(self.db_path, data_dir)

        try:
            self._conn = await aiosqlite.connect(self.db_path)
            c = self._conn
            if c is None:
                raise RuntimeError("Database connection not initialized")

            logger.info("Соединение с базой данных '{}' установлено.", self.db_path)

            c.row_factory = aiosqlite.Row

            await self._create_tables()
            await self._run_migrations()
            await self._enable_wal()

            # Проверка целостности БД после подключения
            from src.database.integrity import check_and_recover

            try:
                self._conn = await check_and_recover(self.db_path, self._conn)
            except Exception as e:
                logger.error("Ошибка при проверке целостности БД (нефатально): {}", e)
                # Если check_and_recover закрыл соединение — переподключаемся
                try:  # noqa: SIM105
                    await self._conn.close()
                except Exception:
                    pass
                self._conn = await aiosqlite.connect(self.db_path)
                self._conn.row_factory = aiosqlite.Row
                await self._enable_wal()
                logger.info(
                    "Переподключение к БД после ошибки integrity check выполнено"
                )

        except aiosqlite.Error as e:
            logger.error("Ошибка подключения aiosqlite для '{}': {}", self.db_path, e)
            raise
        except Exception as e:
            logger.error(
                "Общая ошибка при подключении к базе данных '{}': {}", self.db_path, e
            )
            raise

    async def close(self) -> None:
        """Закрыть соединение с WAL checkpoint."""
        if self._conn:
            try:
                await self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                logger.debug(
                    "Не удалось выполнить WAL checkpoint при закрытии БД",
                    exc_info=True,
                )
            await self._conn.close()
            self._conn = None

    async def _enable_wal(self) -> None:
        """Включить WAL-режим, busy_timeout и foreign_keys."""
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        await c.execute("PRAGMA journal_mode=WAL")
        await c.execute("PRAGMA busy_timeout=5000")
        await c.execute("PRAGMA foreign_keys=ON")

    @staticmethod
    async def _log_permissions(db_path: str, data_dir: str) -> None:
        """Логирует права доступа к файлу БД и директории для диагностики."""
        import stat as _stat

        if await aiofiles.os.path.exists(db_path):
            db_stat = await aiofiles.os.stat(db_path)
            db_mode = _stat.S_IMODE(db_stat.st_mode)
            db_readable = os.access(db_path, os.R_OK)
            db_writable = os.access(db_path, os.W_OK)
            logger.debug(
                "Файл БД: {}, права: {:o}, readable: {}, writable: {}, size: {}",
                db_path,
                db_mode,
                db_readable,
                db_writable,
                db_stat.st_size,
            )
            if not db_writable:
                logger.critical(
                    "Файл БД {} НЕ ДОСТУПЕН ДЛЯ ЗАПИСИ! "
                    "Проверьте права (chmod, chown) в docker-контейнере.",
                    db_path,
                )
        else:
            logger.debug(
                "Файл БД {} не существует, будет создан при connect()", db_path
            )

        if data_dir:
            dir_stat = await aiofiles.os.stat(data_dir)
            dir_mode = _stat.S_IMODE(dir_stat.st_mode)
            dir_writable = os.access(data_dir, os.W_OK)
            logger.debug(
                "Директория БД: {}, права: {:o}, writable: {}",
                data_dir,
                dir_mode,
                dir_writable,
            )
            if not dir_writable:
                logger.critical(
                    "Директория {} НЕ ДОСТУПНА ДЛЯ ЗАПИСИ! "
                    "WAL-режим SQLite требует права на запись в директорию.",
                    data_dir,
                )

    async def _create_tables(self) -> None:
        """Создаёт только таблицу schema_version — всё остальное через миграции."""
        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        await c.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)"
        )
        await c.commit()

    async def _run_migrations(self) -> None:
        """Применяет все миграции с версией > текущей schema_version."""
        from src.database.migrations import MIGRATIONS

        c = self._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")

        cursor = await c.execute("SELECT MAX(version) FROM schema_version")
        row = await cursor.fetchone()
        current = row[0] if (row and row[0] is not None) else 0

        for version, migrate_fn in MIGRATIONS:
            if version > current:
                logger.info("Применяется миграция v{}...", version)
                await migrate_fn(self)
                await c.execute(
                    "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                    (version,),
                )
                await c.commit()
                logger.info("Миграция v{} применена", version)
