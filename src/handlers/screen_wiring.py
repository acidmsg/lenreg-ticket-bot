"""Сборка сервиса экрана чата: мост ``database`` → ``services``.

Слой ``handlers`` вправе импортировать и ``database``, и ``services`` (границы
``import-linter``), поэтому адаптер хранилища живёт здесь: сервис экрана работает
со структурой :class:`~src.services.screen_port.StoredScreen`, а таблица
``user_chat_screen`` отдаёт :class:`~src.database.types.ScreenRecord`.

Здесь же сервис получает билдер клавиатуры: ``get_screen_keyboard`` импортируется
в ``handlers`` и передаётся в сервис аргументом, поэтому ``src.services`` не
зависит от ``src.keyboards`` (дизайн §10.3). Фабрика вызывается из ``main``
(фоновые задачи мониторинга и очистки, зависимость хендлера ``/start``).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from aiogram import Bot

from src.database.manager import DatabaseManager
from src.database.types import ScreenRecord
from src.handlers.screen_transport import TelegramScreenTransport
from src.keyboards.inline import get_screen_keyboard
from src.services.screen_port import ScreenStore, StoredScreen
from src.services.screen_render import RenderedScreen
from src.services.screen_service import ScreenService, ScreenServiceOptions
from src.services.telegram_health import telegram_health


def _to_stored(record: ScreenRecord) -> StoredScreen:
    """Преобразует запись таблицы ``user_chat_screen`` в структуру порта."""
    return StoredScreen(
        uid=record["uid"],
        kind=record["kind"],
        chat_id=record["chat_id"],
        msg_id=record["msg_id"],
        content_type=record["content_type"],
        render_hash=record["render_hash"],
        last_seen_ts=record["last_seen_ts"],
        updated_at=record["updated_at"],
        last_check_at=record["last_check_at"],
        check_count=record["check_count"],
        error_count=record["error_count"],
        last_event_at=record["last_event_at"],
        new_events_count=record["new_events_count"],
    )


def _to_record(screen: StoredScreen) -> ScreenRecord:
    """Преобразует структуру порта в запись таблицы ``user_chat_screen``."""
    return {
        "uid": screen.uid,
        "kind": screen.kind,
        "chat_id": screen.chat_id,
        "msg_id": screen.msg_id,
        "content_type": screen.content_type,
        "render_hash": screen.render_hash,
        "last_seen_ts": screen.last_seen_ts,
        "updated_at": screen.updated_at,
        "last_check_at": screen.last_check_at,
        "check_count": screen.check_count,
        "error_count": screen.error_count,
        "last_event_at": screen.last_event_at,
        "new_events_count": screen.new_events_count,
    }


class DatabaseScreenStore:
    """Адаптер :class:`~src.services.screen_port.ScreenStore` над ``DatabaseManager``.

    Attributes:
        _db: Менеджер базы данных (единственный владелец соединения).
    """

    def __init__(self, db: DatabaseManager) -> None:
        """Сохраняет менеджер базы данных."""
        self._db = db

    async def get(self, uid: int, kind: str) -> StoredScreen | None:
        """Возвращает запись экрана или ``None``, если экрана нет."""
        record = await self._db.get_screen(uid, kind)
        if record is None:
            return None
        return _to_stored(record)

    async def save(self, screen: StoredScreen) -> None:
        """Создаёт или перезаписывает запись экрана."""
        await self._db.set_screen(_to_record(screen))

    async def forget(self, uid: int, kind: str) -> None:
        """Удаляет запись экрана; отсутствие записи ошибкой не считается."""
        await self._db.drop_screen(uid, kind)


def _unix_seconds() -> int:
    """Текущее Unix-время в секундах — часы по умолчанию для сервиса экрана."""
    return int(time.time())


def build_screen_service(
    bot: Bot,
    db: DatabaseManager,
    clock: Callable[[], int] = _unix_seconds,
) -> ScreenService:
    """Собирает сервис экрана: хранилище БД, транспорт, клавиатура, телеметрия.

    Args:
        bot: Экземпляр Telegram-бота для отправки и правки экрана.
        db: Менеджер базы данных (хранилище записей ``user_chat_screen``).
        clock: Часы в Unix-секундах; по умолчанию системное время.

    Returns:
        Готовый :class:`~src.services.screen_service.ScreenService`, у которого
        счётчики исходов пишутся в общую телеметрию Telegram-шлюза, а
        ``reply_markup`` собирает :func:`src.keyboards.inline.get_screen_keyboard`
        по состоянию :class:`~src.services.screen_render.RenderedScreen`.

    Билдер оборачивается явной функцией: ``get_screen_keyboard`` принимает
    рендер целиком, а сервис передаёт его по контракту
    ``Callable[[RenderedScreen], Any]``.
    """
    store: ScreenStore = DatabaseScreenStore(db)

    def build_keyboard(rendered: RenderedScreen) -> Any:
        """Собирает клавиатуру S2 по состоянию рендера."""
        return get_screen_keyboard(rendered)

    return ScreenService(
        store=store,
        transport=TelegramScreenTransport(bot),
        clock=clock,
        options=ScreenServiceOptions(
            on_outcome=telegram_health.record_screen_outcome,
            keyboard_builder=build_keyboard,
        ),
    )
