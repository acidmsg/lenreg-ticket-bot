"""Порт отправки уведомлений.

Сервис мониторинга сообщает данные уведомления через :class:`NotificationPort`;
представление (клавиатура, картинка) и транспорт живут в слое `handlers`
(реализация — `src.handlers.notifications.TelegramNotifier`).

:class:`ScreenTransport` — отдельный порт для единого экрана чата: сервис
экрана умеет отправить текст, отредактировать его и удалить сообщение.
Реализация — ``src.handlers.screen_transport.TelegramScreenTransport``;
``NotificationPort`` при этом не меняется.
"""

from __future__ import annotations

from typing import Any, Protocol

from src.services.telegram_sender import EditOutcome


class NotificationPort(Protocol):
    """Порт отправки уведомления; реализация — в слое транспорта."""

    async def notify(
        self,
        chat_id: int,
        p_id: str,
        d_id: str,
        text: str,
        notify_type: str,
    ) -> bool:
        """Отправляет уведомление; возвращает False при ошибке отправки."""
        ...


class ScreenTransport(Protocol):
    """Транспорт экрана чата: отправка, правка и удаление одного сообщения."""

    async def send_text(
        self,
        chat_id: int,
        text: str,
        reply_markup: Any = None,
        disable_notification: bool = False,
    ) -> int | None:
        """Отправляет текст; возвращает ``message_id`` либо ``None`` при ошибке."""
        ...

    async def edit_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: Any = None,
    ) -> EditOutcome:
        """Правит текст экрана; возвращает исход операции, исключений не бросает."""
        ...

    async def delete_message(self, chat_id: int, message_id: int) -> bool:
        """Удаляет сообщение; ``False`` — удалить не удалось."""
        ...
