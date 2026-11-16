"""
Порт хранилища экранов чата.

Сервис экрана работает со структурой :class:`StoredScreen` и не знает о слое
``src.database``: адаптер к таблице ``user_chat_screen`` подключается выше
(слой ``handlers`` / ``main``). Это сохраняет направление зависимостей
``services`` → порт, без импорта БД из сервиса.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.services.screen_render import ScreenContext, ScreenItem

# Вид экрана мониторинга: на чат допускается не более одного такого экрана.
KIND_MONITOR = "monitor"

# Тип вложения экрана: поддерживается только текст; иные форматы — за рамками задачи.
CONTENT_TYPE_TEXT = "text"


@dataclass(frozen=True, slots=True)
class StoredScreen:
    """Сохранённый экран чата: данные без привязки к способу хранения."""

    uid: int
    """ID пользователя Telegram."""

    kind: str
    """Вид экрана (``'monitor'``)."""

    chat_id: int
    """ID чата, в котором живёт сообщение-экран."""

    msg_id: int
    """ID сообщения-экрана в Telegram."""

    content_type: str
    """Тип вложения экрана (``'text'``)."""

    render_hash: str
    """SHA-256 канонического состояния последнего рендера."""

    last_seen_ts: int
    """Unix-время (секунды) последнего учтённого события."""

    updated_at: int
    """Unix-время (секунды) последней записи — база TTL-выборки."""

    last_check_at: int = 0
    """Unix-время (секунды) последней итерации проверки пар."""

    check_count: int = 0
    """Число проверок пар с момента создания записи экрана."""

    error_count: int = 0
    """Число неуспешных проверок пар."""

    last_event_at: int = 0
    """Unix-время (секунды) последнего события, попавшего в экран."""

    new_events_count: int = 0
    """Сколько новых событий показано в экране с прошлого визита пользователя."""


class ScreenStore(Protocol):
    """Хранилище экранов: минимум операций для сервиса обновления."""

    async def get(self, uid: int, kind: str) -> StoredScreen | None:
        """Возвращает запись экрана или ``None``, если экрана нет."""
        ...

    async def save(self, screen: StoredScreen) -> None:
        """Создаёт или перезаписывает запись экрана."""
        ...

    async def forget(self, uid: int, kind: str) -> None:
        """Удаляет запись экрана; отсутствие записи ошибкой не считается."""
        ...


class ScreenServicePort(Protocol):
    """Минимум сервиса экрана для его потребителей (монитор, очистка, ``/start``).

    Позволяет слою ``services`` и хендлерам зависеть от узкого контракта, а не
    от конкретного класса: в тестах достаточно структурной заглушки.
    """

    async def update_screen(
        self, uid: int, chat_id: int, items: list[ScreenItem]
    ) -> object:
        """Применяет состояние экрана к чату и возвращает исход операции."""
        ...

    async def ensure_screen(
        self, uid: int, chat_id: int, context: ScreenContext
    ) -> object:
        """Гарантирует живой экран: отправка, проверка живости или замена."""
        ...

    async def discard_screen(self, uid: int, kind: str = KIND_MONITOR) -> bool:
        """Удаляет сообщение экрана и запись о нём."""
        ...
