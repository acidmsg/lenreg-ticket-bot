"""Транспорт экрана чата в слое ``handlers``.

Реализует порт :class:`~src.services.notification_port.ScreenTransport`:
отправка нового сообщения, тихая правка текста и удаление. Вся работа с Bot API
делегируется в :mod:`src.services.telegram_sender` — общий per-loop лимитер,
обработка 429 и классификация ошибок живут там, дублирования нет.

Клавиатура экрана собирается в этом слое
(:func:`src.keyboards.inline.get_screen_keyboard`), а не в сервисе: сервис не
импортирует ``keyboards`` (дизайн §10.3). Готовый ``reply_markup`` передаётся
через порт, поэтому транспорт не знает о составе событий.
"""

from __future__ import annotations

from typing import Any

from aiogram import Bot

from src.services import telegram_sender
from src.services.telegram_sender import EditOutcome


class TelegramScreenTransport:
    """Делегирует операции экрана в :mod:`src.services.telegram_sender`.

    Attributes:
        _bot: Экземпляр Telegram-бота.
    """

    def __init__(self, bot: Bot) -> None:
        """Сохраняет экземпляр бота для операций с сообщением-экраном."""
        self._bot = bot

    async def send_text(
        self,
        chat_id: int,
        text: str,
        reply_markup: Any = None,
        disable_notification: bool = False,
    ) -> int | None:
        """Отправляет текст экрана; ``None`` — отправка не удалась."""
        return await telegram_sender.send_text(
            self._bot,
            chat_id,
            text,
            reply_markup=reply_markup,
            disable_notification=disable_notification,
        )

    async def edit_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: Any = None,
    ) -> EditOutcome:
        """Правит текст существующего экрана и возвращает исход правки."""
        return await telegram_sender.edit_text(
            self._bot,
            chat_id,
            message_id,
            text,
            reply_markup=reply_markup,
        )

    async def delete_message(self, chat_id: int, message_id: int) -> bool:
        """Удаляет сообщение-экран; ``False`` — удалить не удалось."""
        return await telegram_sender.delete_message(self._bot, chat_id, message_id)
