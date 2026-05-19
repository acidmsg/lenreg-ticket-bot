"""
Фоновая задача автоудаления старых сообщений (TTL).
Проверяет last_messages и удаляет сообщения,
отправленные более MESSAGE_TTL_SECONDS назад.
"""

import asyncio
import time
from contextlib import suppress

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from loguru import logger

from src.config import settings
from src.database.manager import DatabaseManager
from src.utils.helpers import extract_msg_id


async def cleanup_loop(bot: Bot, db: DatabaseManager):
    """Фоновый цикл: проверяет last_messages и удаляет просроченные."""
    logger.info(
        "Цикл очистки старых сообщений запущен (TTL={} с, интервал={} с)",
        settings.MESSAGE_TTL_SECONDS,
        settings.CLEANUP_INTERVAL,
    )

    while True:
        try:
            await _cleanup_pass(bot, db)
        except asyncio.CancelledError:
            logger.info("Цикл очистки остановлен (cancelled)")
            break
        except Exception as e:
            logger.error(f"Ошибка в цикле очистки: {e}", exc_info=True)

        await asyncio.sleep(settings.CLEANUP_INTERVAL)


async def _cleanup_pass(bot: Bot, db: DatabaseManager):
    """Один проход очистки для всех пользователей.

    Обрабатывает пользователей батчами по BATCH_SIZE записей,
    чтобы не загружать всех пользователей в память одновременно.
    """
    now = time.time()
    ttl = settings.MESSAGE_TTL_SECONDS
    total_deleted = 0
    batch_size = 50

    user_ids = await db._db.get_all_user_ids()

    for i in range(0, len(user_ids), batch_size):
        batch = user_ids[i : i + batch_size]

        for uid in batch:
            user_data = await db._db.get_user(uid)
            if user_data is None:
                continue

            last_messages = user_data.get("last_messages", {})
            if not last_messages:
                continue

            changed = False

            for key in list(last_messages.keys()):
                value = last_messages[key]
                msg_id = extract_msg_id(value)

                if msg_id is None:
                    # Удаляем некорректные записи
                    del last_messages[key]
                    changed = True
                    continue

                # Если значение не dict (старый формат, нет ts) — пропускаем,
                # конвертируем при первом обновлении через set_last_message_id
                ts = value.get("ts") if isinstance(value, dict) else None
                if ts is None:
                    continue

                age = now - ts
                if age >= ttl:
                    try:
                        uid_int = int(uid)
                    except (ValueError, TypeError):
                        logger.warning(
                            "Некорректный uid {!r}, удаление сообщения пропущено",
                            uid,
                        )
                        continue

                    with suppress(TelegramAPIError):
                        await bot.delete_message(uid_int, msg_id)
                    del last_messages[key]
                    changed = True
                    total_deleted += 1
                    logger.debug(
                        "Удалено msg_id={} uid={} key={} возраст={:.1f}ч",
                        msg_id,
                        uid,
                        key,
                        age / 3600,
                    )

            if changed:
                await db.update_user(uid, {"last_messages": last_messages})

    if total_deleted:
        logger.info("Очистка завершена: удалено {} сообщений", total_deleted)
