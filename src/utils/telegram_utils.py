"""
Telegram-специфичные утилиты: отправка/обновление сообщений, работа с клавиатурами.
"""

import contextlib
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import FSInputFile, Message

from src.database.manager import DatabaseManager


async def send_or_update_message(
    bot: Bot,
    chat_id: int,
    db: DatabaseManager,
    cache_key1: str,
    cache_key2: str,
    text: str,
    photo_path: Path | None = None,
    reply_markup=None,
    old_message: Message | None = None,
) -> Message | None:
    """Низкоуровневый хелпер: удалить старое → отправить новое → сохранить msg_id.

    Общий паттерн для ``_send_nav_photo`` и ``_send_notification``:
    1. Получить last_msg_id из БД и удалить предыдущее сообщение.
    2. Опционально удалить old_message (call.message).
    3. Отправить новое сообщение (с фото или без).
    4. Сохранить message_id в БД.
    """
    uid = str(chat_id)

    last_msg_id = await db.get_last_message_id(uid, cache_key1, cache_key2)
    if last_msg_id:
        with contextlib.suppress(TelegramAPIError):
            await bot.delete_message(chat_id, last_msg_id)

    if old_message is not None:
        with contextlib.suppress(Exception):
            await old_message.delete()

    if photo_path is not None:
        photo = FSInputFile(photo_path)
        new_msg = await bot.send_photo(
            chat_id,
            photo,
            caption=text,
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )
    else:
        new_msg = await bot.send_message(
            chat_id,
            text,
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )

    await db.set_last_message_id(uid, cache_key1, cache_key2, new_msg.message_id)
    return new_msg
