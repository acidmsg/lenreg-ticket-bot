"""
Фоновая задача автоудаления старых сообщений (TTL).

Удаляет эфемерные сообщения старше ``MESSAGE_TTL_SECONDS`` и «вечные» экраны
чата (``user_chat_screen``, ``kind = monitor``), у которых нет активного
мониторинга и которые не обновлялись дольше ``SCREEN_STALE_SECONDS``.
"""

import asyncio
import time
from contextlib import suppress

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from loguru import logger

from src.config import settings
from src.database.manager import DatabaseManager
from src.database.types import UserData
from src.services.screen_port import KIND_MONITOR, ScreenServicePort
from src.utils.helpers import extract_msg_id

# Размер батча пользователей за один проход: ограничивает память при обходе.
_USER_BATCH_SIZE = 50


async def cleanup_loop(
    bot: Bot, db: DatabaseManager, screen_service: ScreenServicePort | None = None
) -> None:
    """Фоновый цикл: удаляет просроченные сообщения и «вечные» экраны."""
    logger.info(
        "Цикл очистки старых сообщений запущен (TTL={} с, интервал={} с)",
        settings.MESSAGE_TTL_SECONDS,
        settings.CLEANUP_INTERVAL,
    )

    while True:
        try:
            await _cleanup_pass(bot, db, screen_service)
        except asyncio.CancelledError:
            logger.info("Цикл очистки остановлен (cancelled)")
            break
        except Exception as e:
            logger.opt(exception=True).error(f"Ошибка в цикле очистки: {e}")

        await asyncio.sleep(settings.CLEANUP_INTERVAL)


async def _cleanup_iteration(
    bot: Bot,
    db: DatabaseManager,
    screen_service: ScreenServicePort | None = None,
) -> None:
    """Одна итерация очистки старых сообщений (для BackgroundTaskManager).

    Выполняет один полный проход по всем пользователям, удаляя сообщения
    старше ``MESSAGE_TTL_SECONDS``, и TTL-проход по экранам чата.
    Менеджер владеет ``while True``, sleep, retry и обработкой CancelledError.
    """
    await _cleanup_pass(bot, db, screen_service)


async def _cleanup_pass(
    bot: Bot, db: DatabaseManager, screen_service: ScreenServicePort | None = None
) -> None:
    """Один проход очистки для всех пользователей.

    Обрабатывает пользователей батчами по ``_USER_BATCH_SIZE`` записей,
    чтобы не загружать всех пользователей в память одновременно.
    """
    now = time.time()
    total_deleted = 0

    user_ids = await db.get_all_user_ids()

    for i in range(0, len(user_ids), _USER_BATCH_SIZE):
        batch = user_ids[i : i + _USER_BATCH_SIZE]
        for uid in batch:
            user_data = await db.get_user(uid)
            if user_data is None:
                continue
            total_deleted += await _cleanup_user_messages(bot, db, uid, user_data, now)

    if screen_service is not None:
        screens_removed = await _cleanup_screens(db, screen_service, now)
        if screens_removed:
            logger.info("Очистка экранов: удалено {} записей", screens_removed)

    if total_deleted:
        logger.info("Очистка завершена: удалено {} сообщений", total_deleted)


async def _cleanup_user_messages(
    bot: Bot,
    db: DatabaseManager,
    uid: str,
    user_data: UserData,
    now: float,
) -> int:
    """Удаляет просроченные эфемерные сообщения одного пользователя.

    Returns:
        Число удалённых сообщений.
    """
    last_messages = user_data.get("last_messages", {})
    if not last_messages:
        return 0

    ttl = settings.MESSAGE_TTL_SECONDS
    changed = False
    deleted_count = 0
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
        if age < ttl:
            continue

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
        deleted_count += 1
        logger.debug(
            "Удалено msg_id={} uid={} key={} возраст={:.1f}ч",
            msg_id,
            uid,
            key,
            age / 3600,
        )

    if changed:
        await db.update_user(uid, {"last_messages": last_messages})
    return deleted_count


async def _cleanup_screens(
    db: DatabaseManager, screen_service: ScreenServicePort, now: float
) -> int:
    """Удаляет экраны, которые давно не обновлялись и не нужны пользователю.

    Экран «вечный»: общий TTL сообщений к нему не применяется (дизайн §9.3).
    Удаляется только запись, у которой ``updated_at`` старше
    ``SCREEN_STALE_SECONDS`` **и** у пользователя пуст мониторинг. Запись
    активного пользователя не трогается, ``updated_at`` не сдвигается.

    Returns:
        Число снятых экранов.
    """
    threshold = int(now - settings.SCREEN_STALE_SECONDS)
    stale = await db.list_stale_screens(threshold, KIND_MONITOR)
    removed = 0
    for record in stale:
        uid = str(record["uid"])
        if await _has_active_monitoring(db, uid):
            continue
        try:
            await screen_service.discard_screen(record["uid"], KIND_MONITOR)
        except Exception:
            logger.opt(exception=True).warning(
                "Не удалось удалить экран чата uid={} — повтор на следующем проходе",
                uid,
            )
            continue
        removed += 1
    return removed


async def _has_active_monitoring(db: DatabaseManager, uid: str) -> bool:
    """Есть ли у пользователя хотя бы одна активная пара «пациент — врач»."""
    user = await db.get_user(uid)
    monitoring = (user or {}).get("monitoring", {})
    return any(monitoring.values())
