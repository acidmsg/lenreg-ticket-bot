"""Порт отправки уведомлений.

Сервис мониторинга сообщает данные уведомления через :class:`NotificationPort`;
представление (клавиатура, картинка) и транспорт живут в слое `handlers`
(реализация — `src.handlers.notifications.TelegramNotifier`).
"""

from __future__ import annotations

from typing import Protocol


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
