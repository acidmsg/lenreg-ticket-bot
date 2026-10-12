"""Реализация порта уведомлений в слое транспорта.

:class:`TelegramNotifier` структурно реализует
:class:`~src.services.notification_port.NotificationPort`: собирает представление
уведомления (инлайн-клавиатура и картинка типа уведомления) и делегирует
отправку в :func:`~src.services.telegram_sender.send_telegram_message`.
"""

from __future__ import annotations

from aiogram import Bot

from src.assets.utils import get_notify_image_path
from src.keyboards.inline import get_notification_keyboard
from src.services.telegram_sender import TelegramMessage, send_telegram_message
from src.utils.protocols import LastMessageStore


class TelegramNotifier:
    """Отправляет уведомление о номерках: представление + делегирование в sender.

    Attributes:
        _bot: Экземпляр Telegram-бота.
        _store: Хранилище id последнего сообщения (обычно ``DatabaseManager``).
    """

    def __init__(self, bot: Bot, store: LastMessageStore) -> None:
        """Сохраняет транспорт отправки.

        Args:
            bot: Экземпляр Telegram-бота.
            store: Хранилище id последнего сообщения (обычно ``DatabaseManager``).
        """
        self._bot = bot
        self._store = store

    async def notify(
        self,
        chat_id: int,
        p_id: str,
        d_id: str,
        text: str,
        notify_type: str,
    ) -> bool:
        """Отправляет уведомление с клавиатурой и картинкой типа уведомления.

        Args:
            chat_id: Идентификатор чата получателя.
            p_id: Идентификатор пациента.
            d_id: Идентификатор врача.
            text: Текст уведомления.
            notify_type: Тип уведомления (empty/available/new/decreased).

        Returns:
            True если отправка успешна, False при ошибке.
        """
        message = TelegramMessage(
            p_id=p_id,
            d_id=d_id,
            text=text,
            photo_path=get_notify_image_path(notify_type),
            reply_markup=get_notification_keyboard(p_id, d_id),
        )
        return await send_telegram_message(self._bot, chat_id, self._store, message)
