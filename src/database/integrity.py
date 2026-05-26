"""
Проверка и восстановление целостности SQLite БД при старте.

Используется в ``Database.connect()`` для раннего обнаружения
повреждений файла БД (database disk image is malformed).
"""

import asyncio
import os
import shutil
import time

import aiofiles.os
import aiosqlite
from loguru import logger


async def check_and_recover(
    db_path: str, conn: aiosqlite.Connection
) -> aiosqlite.Connection:
    """Проверяет целостность БД и пытается восстановить при повреждении.

    Возвращает (возможно, новое) соединение с БД.
    При невозможности восстановления стартует с чистой БД.

    Args:
        db_path: Путь к файлу БД.
        conn: Текущее соединение (может быть закрыто и заменено).

    Returns:
        Активное соединение с БД (исходное или новое).
    """
    # Шаг 1: PRAGMA integrity_check
    try:
        cursor = await conn.execute("PRAGMA integrity_check")
        row = await cursor.fetchone()
        result = row[0] if row else ""

        if result.lower() == "ok":
            logger.debug("PRAGMA integrity_check: OK")
            return conn

        logger.critical(
            "PRAGMA integrity_check FAILED: {}",
            result,
        )
    except aiosqlite.Error as e:
        logger.critical(
            "PRAGMA integrity_check ERROR: {}",
            e,
        )
        result = str(e)

    # Шаг 2: закрываем текущее соединение
    await conn.close()

    # Шаг 3: бэкап битого файла
    ts = int(time.time())
    backup_path = f"{db_path}.corrupted.{ts}"
    if await aiofiles.os.path.exists(db_path):
        await asyncio.to_thread(shutil.copy2, db_path, backup_path)
        logger.info("Повреждённая БД скопирована в: {}", backup_path)

    # Шаг 4: пытаемся восстановить через .dump / .recover
    dump_sql = await _try_dump_or_recover(db_path)

    # Шаг 5: создаём новую БД из дампа
    new_conn = await _restore_from_dump(db_path, dump_sql, backup_path, ts)

    if new_conn is not None:
        return new_conn

    # Шаг 6: всё failed — чистый старт
    logger.critical(
        "Восстановление БД не удалось. Бот запустится с чистой БД. "
        "Бэкап битого файла: {}",
        backup_path,
    )
    if await aiofiles.os.path.exists(db_path):
        await asyncio.to_thread(os.remove, db_path)

    new_conn = await aiosqlite.connect(db_path)
    new_conn.row_factory = aiosqlite.Row
    await new_conn.execute("PRAGMA journal_mode=WAL")
    await new_conn.execute("PRAGMA busy_timeout=5000")
    await new_conn.execute("PRAGMA foreign_keys=ON")
    logger.warning("Бот запущен с чистой БД. Данные пользователей утеряны.")
    return new_conn


async def _try_dump_or_recover(db_path: str) -> str | None:
    """Пытается .dump, затем .recover через sqlite3 CLI."""
    for cmd in (".dump", ".recover"):
        try:
            proc = await asyncio.create_subprocess_exec(
                "sqlite3",
                db_path,
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _stderr = await proc.communicate()
            if proc.returncode == 0 and stdout:
                text = stdout.decode("utf-8", errors="replace")
                if text.strip():
                    logger.info(
                        "{} успешен: {} байт SQL",
                        cmd,
                        len(text),
                    )
                    return text
        except FileNotFoundError:
            logger.warning("sqlite3 CLI не найден в PATH")
            break
        except Exception as e:
            logger.warning("Ошибка при {}: {}", cmd, e)
    return None


async def _restore_from_dump(
    db_path: str,
    dump_sql: str | None,
    backup_path: str,
    ts: int,
) -> aiosqlite.Connection | None:
    """Пытается восстановить БД из SQL-дампа.

    Returns:
        Новое соединение или None, если восстановление не удалось.
    """
    if dump_sql is None:
        return None

    new_db_path = f"{db_path}.recovered.{ts}"
    try:
        new_conn = await aiosqlite.connect(new_db_path)
        await new_conn.executescript(dump_sql)
        await new_conn.commit()
        await new_conn.close()

        if await aiofiles.os.path.exists(db_path):
            await asyncio.to_thread(os.remove, db_path)
        await asyncio.to_thread(shutil.move, new_db_path, db_path)
        logger.info("БД восстановлена из дампа. Бэкап: {}", backup_path)

        # Переподключаемся и проверяем
        restored_conn = await aiosqlite.connect(db_path)
        restored_conn.row_factory = aiosqlite.Row
        await restored_conn.execute("PRAGMA journal_mode=WAL")
        await restored_conn.execute("PRAGMA busy_timeout=5000")
        await restored_conn.execute("PRAGMA foreign_keys=ON")

        cursor = await restored_conn.execute("PRAGMA integrity_check")
        row = await cursor.fetchone()
        if row and row[0].lower() == "ok":
            logger.info("Восстановленная БД прошла integrity_check")
            return restored_conn
        else:
            logger.error(
                "Восстановленная БД НЕ прошла проверку: {}",
                row[0] if row else "нет результата",
            )
            await restored_conn.close()
    except Exception as e:
        logger.error("Ошибка при восстановлении БД из дампа: {}", e)

    return None
