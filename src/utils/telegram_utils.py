"""
Telegram-специфичные утилиты: отправка/обновление сообщений, работа с клавиатурами.
"""

import contextlib
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import FSInputFile, InputRichMessage, Message
from loguru import logger

from src.database.manager import DatabaseManager


async def _send_plain_message(
    bot: Bot,
    chat_id: int,
    text: str,
    photo_path: Path | None,
    reply_markup,
) -> Message:
    """Отправляет обычное фото-сообщение (или текст) — fallback rich.

    Повторяет поведение :func:`send_or_update_message`: при наличии файла —
    ``send_photo`` с подписью, иначе — ``send_message``. Обе ветки используют
    ``parse_mode="Markdown"``.
    """
    if photo_path is not None:
        photo = FSInputFile(photo_path)
        try:
            return await bot.send_photo(
                chat_id,
                photo,
                caption=text,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
        except Exception:
            logger.debug("Не удалось отправить фото-подпись, отправляю текстом")
    return await bot.send_message(
        chat_id,
        text,
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )


async def send_or_update_rich_message(
    bot: Bot,
    chat_id: int,
    db: DatabaseManager,
    cache_key1: str,
    cache_key2: str,
    rich_message: InputRichMessage,
    fallback_text: str,
    photo_path: Path | None = None,
    reply_markup=None,
    old_message: Message | None = None,
) -> Message | None:
    """Удалить старое → отправить rich-сообщение → сохранить msg_id.

    Тот же паттерн, что у :func:`send_or_update_message`. Если ``send_rich_
    message`` недоступен (ошибка Telegram API), выполняется деградация к
    обычной отправке (``fallback_text`` + ``photo_path``), чтобы
    функциональность экрана сохранилась.
    """
    uid = str(chat_id)

    last_msg_id = await db.get_last_message_id(uid, cache_key1, cache_key2)
    if last_msg_id:
        with contextlib.suppress(TelegramAPIError):
            await bot.delete_message(chat_id, last_msg_id)

    if old_message is not None:
        with contextlib.suppress(Exception):
            await old_message.delete()

    try:
        new_msg = await bot.send_rich_message(
            chat_id,
            rich_message=rich_message,
            reply_markup=reply_markup,
        )
    except (TelegramAPIError, AttributeError, TypeError) as exc:
        logger.warning(
            "send_rich_message недоступен ({}), fallback на обычное: {}",
            type(exc).__name__,
            exc,
        )
        new_msg = await _send_plain_message(
            bot, chat_id, fallback_text, photo_path, reply_markup
        )

    await db.set_last_message_id(uid, cache_key1, cache_key2, new_msg.message_id)
    return new_msg


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
