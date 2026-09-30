"""Идентичность бота: username, разрешённый один раз при старте.

Deep-link'и Mini App (``https://t.me/<bot>?startapp=…``) требуют username бота.
``get_me()`` — сетевой вызов Telegram API, поэтому результат кэшируется на
процесс: клавиатуры уведомлений берут username из кэша, а не ходят в сеть на
каждое сообщение.
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from loguru import logger

# Username бота без ведущего «@»; пустая строка — ещё не разрешён.
_bot_username: str = ""


def set_bot_username(username: str | None) -> None:
    """Сохраняет username бота в кэш процесса (без ведущего «@»).

    Args:
        username: username из Telegram (может быть ``None`` или с «@»).
    """
    global _bot_username
    _bot_username = (username or "").lstrip("@").strip()


def get_bot_username() -> str:
    """Возвращает кэшированный username бота.

    Returns:
        Username без «@» либо пустая строка, если он ещё не разрешён.
    """
    return _bot_username


async def resolve_bot_username(bot: Bot) -> str:
    """Разрешает username бота через ``get_me()`` и кэширует его.

    Вызывается один раз при старте. Сетевой сбой не роняет запуск: при ошибке
    API возвращается пустая строка, а клавиатуры уведомлений остаются на
    прежней WebApp-кнопке.

    Args:
        bot: запущенный экземпляр бота.

    Returns:
        Username без «@» либо пустая строка, если его не удалось получить.
    """
    try:
        me = await bot.me()
    except TelegramAPIError as exc:
        logger.warning("Не удалось получить username бота (get_me): {}", exc)
        return ""

    set_bot_username(me.username)
    if not get_bot_username():
        logger.warning(
            "У бота не задан username — deep-link'и в уведомлениях недоступны, "
            "используется WebApp-кнопка"
        )
    else:
        logger.info("Username бота для deep-link'ов: @{}", get_bot_username())
    return _bot_username
