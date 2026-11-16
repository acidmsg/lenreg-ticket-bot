"""
Сервис обновления единого экрана чата (single screen message).

Единственная точка применения состояния экрана к чату. Сервис не знает ни о
Telegram, ни о слое ``src.database``: хранилище и транспорт приходят через
порты (:class:`~src.services.screen_port.ScreenStore`,
:class:`~src.services.notification_port.ScreenTransport`).

Стратегия:

- hash совпал → :attr:`UpdateOutcome.NOOP`, обращения к транспорту нет;
- записи экрана нет → отправка нового сообщения (:attr:`UpdateOutcome.SENT`);
- есть новые события либо тип вложения не текстовый → замена: удалить прежнее
  сообщение и отправить новое (:attr:`UpdateOutcome.REPLACED`). Именно замена
  доставляет push;
- новых событий нет и экран текстовый → тихая правка
  (:attr:`UpdateOutcome.EDITED`). Ответ ``NOT_MODIFIED`` считается успехом,
  ``NOT_FOUND``/``CANNOT_EDIT`` откатываются на замену, ``FAILED`` оставляет
  запись экрана неизменной.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from loguru import logger

from src.config import settings
from src.services.notification_port import ScreenTransport
from src.services.screen_port import (
    CONTENT_TYPE_TEXT,
    KIND_MONITOR,
    ScreenStore,
    StoredScreen,
)
from src.services.screen_render import RenderedScreen, ScreenItem, render_screen
from src.services.telegram_sender import EditOutcome


class UpdateOutcome(StrEnum):
    """Итог применения состояния экрана к чату."""

    NOOP = "noop"
    """Состояние не изменилось: транспорт не вызывался."""

    SENT = "sent"
    """Экран отправлен впервые (записи не было)."""

    REPLACED = "replaced"
    """Прежний экран заменён новым сообщением (push)."""

    EDITED = "edited"
    """Тихое обновление текста существующего экрана (push не доставляется)."""

    FAILED = "failed"
    """Отправка не удалась: запись экрана не изменена."""


@dataclass(frozen=True, slots=True)
class _ScreenKey:
    """Адресация экрана: пользователь и чат."""

    uid: int
    chat_id: int


class ScreenService:
    """Сервис обновления экрана чата; владелец per-chat локов экземпляра."""

    def __init__(
        self,
        store: ScreenStore,
        transport: ScreenTransport,
        clock: Callable[[], int],
        on_outcome: Callable[[str], None] | None = None,
        keyboard_builder: Callable[[Sequence[tuple[int, int]]], Any] | None = None,
    ) -> None:
        """Сохраняет зависимости сервиса.

        Args:
            store: Хранилище записей экрана.
            transport: Транспорт отправки, правки и удаления сообщения.
            clock: Часы в Unix-секундах (тесты подменяют монотонным счётчиком).
            on_outcome: Необязательный приёмник исходов (телеметрия); вызывается
                со строковым значением :class:`UpdateOutcome`.
            keyboard_builder: Билдер ``reply_markup`` по показанным парам
                ``(p_id, d_id)``. Передаётся снаружи (слой ``handlers``), потому
                что сервис не импортирует ``src.keyboards`` (дизайн §10.3).
        """
        self._store = store
        self._transport = transport
        self._clock = clock
        self._render: Callable[..., RenderedScreen] = render_screen
        self._on_outcome = on_outcome
        self._keyboard_builder = keyboard_builder
        self._locks: dict[int, asyncio.Lock] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    async def update_screen(
        self, uid: int, chat_id: int, items: list[ScreenItem]
    ) -> UpdateOutcome:
        """Применяет состояние экрана к чату и возвращает исход операции.

        Вызовы для одного чата сериализуются локом экземпляра сервиса, поэтому
        два параллельных обновления не могут отправить два экрана.
        """
        key = _ScreenKey(uid=uid, chat_id=chat_id)
        async with self._chat_lock(chat_id):
            outcome = await self._apply(key, items)
        return self._report(outcome)

    async def _apply(self, key: _ScreenKey, items: list[ScreenItem]) -> UpdateOutcome:
        """Выбирает стратегию обновления по состоянию экрана и наличию событий."""
        rendered = self._render(list(items))
        if len(rendered.text) > settings.SCREEN_TEXT_LIMIT:
            # Защита от 400 "message is too long": рендерер усекает по мягкому
            # лимиту, но жёсткий проверяется здесь — отправлять такой текст нельзя.
            logger.warning(
                "Текст экрана {} символов превышает лимит Telegram {} — "
                "обновление пропущено (uid={} chat_id={})",
                len(rendered.text),
                settings.SCREEN_TEXT_LIMIT,
                key.uid,
                key.chat_id,
            )
            return UpdateOutcome.FAILED
        stored = await self._store.get(key.uid, KIND_MONITOR)
        if stored is not None and stored.render_hash == rendered.render_hash:
            return UpdateOutcome.NOOP
        notification = _has_new_events(items)
        if stored is None:
            return await self._send(key, rendered, notification=notification)
        if notification or stored.content_type != CONTENT_TYPE_TEXT:
            return await self._replace(stored, key, rendered, notification=notification)
        return await self._edit(stored, key, rendered)

    def _report(self, outcome: UpdateOutcome) -> UpdateOutcome:
        """Передаёт исход в приёмник телеметрии (если он инъектирован)."""
        if self._on_outcome is not None:
            self._on_outcome(outcome.value)
        return outcome

    def _chat_lock(self, chat_id: int) -> asyncio.Lock:
        """Лок чата; создаётся лениво внутри корутины, реестр — атрибут сервиса.

        Реестр сбрасывается при смене event loop'а: лок, созданный в прежнем
        loop'е, непригоден в новом (тесты и перезапуск сервиса).
        """
        loop = asyncio.get_running_loop()
        if self._loop is not loop:
            self._locks.clear()
            self._loop = loop
        lock = self._locks.get(chat_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[chat_id] = lock
        return lock

    async def _send(
        self, key: _ScreenKey, rendered: RenderedScreen, *, notification: bool
    ) -> UpdateOutcome:
        """Отправляет новый экран и сохраняет запись о нём."""
        message_id = await self._transport.send_text(
            key.chat_id,
            rendered.text,
            reply_markup=self._markup(rendered),
            disable_notification=not notification,
        )
        if message_id is None:
            logger.warning(
                "Экран чата не отправлен: uid={} chat_id={}", key.uid, key.chat_id
            )
            return UpdateOutcome.FAILED
        await self._store.save(self._build_record(key, rendered, message_id))
        return UpdateOutcome.SENT

    async def _edit(
        self, stored: StoredScreen, key: _ScreenKey, rendered: RenderedScreen
    ) -> UpdateOutcome:
        """Тихо правит текст экрана; ошибки правки разрешаются по классу ответа.

        Правила (дизайн §5.1, §12):

        - ``EDITED`` — успех, запись получает новый ``render_hash``;
        - ``NOT_MODIFIED`` — экран уже актуален, hash всё равно перезаписываем;
        - ``NOT_FOUND`` и ``CANNOT_EDIT`` — сообщение непригодно, нужен replace;
        - ``FAILED`` — запись не меняется, повтор на следующей итерации.
        """
        outcome = await self._transport.edit_text(
            stored.chat_id,
            stored.msg_id,
            rendered.text,
            reply_markup=self._markup(rendered),
        )
        if outcome is EditOutcome.EDITED:
            await self._store.save(
                self._edited_record(stored, rendered, keep_last_seen=False)
            )
            return UpdateOutcome.EDITED
        if outcome is EditOutcome.NOT_MODIFIED:
            await self._store.save(
                self._edited_record(stored, rendered, keep_last_seen=True)
            )
            return UpdateOutcome.EDITED
        if outcome in (EditOutcome.NOT_FOUND, EditOutcome.CANNOT_EDIT):
            logger.info(
                "Правка экрана невозможна (uid={} chat_id={} msg_id={}, исход={}) "
                "— заменяю сообщение",
                key.uid,
                key.chat_id,
                stored.msg_id,
                outcome.value,
            )
            return await self._replace(stored, key, rendered, notification=False)
        logger.error(
            "Правка экрана не удалась (uid={} chat_id={} msg_id={}) — "
            "запись оставлена без изменений",
            key.uid,
            key.chat_id,
            stored.msg_id,
        )
        return UpdateOutcome.FAILED

    def _edited_record(
        self, stored: StoredScreen, rendered: RenderedScreen, *, keep_last_seen: bool
    ) -> StoredScreen:
        """Запись после успешной правки: тот же ``msg_id``, новый hash и время.

        При ``NOT_MODIFIED`` метка ``last_seen_ts`` сохраняется: новых событий
        не было, момент последнего учтённого события не сдвигается.
        """
        now = self._clock()
        return StoredScreen(
            uid=stored.uid,
            kind=stored.kind,
            chat_id=stored.chat_id,
            msg_id=stored.msg_id,
            content_type=stored.content_type,
            render_hash=rendered.render_hash,
            last_seen_ts=stored.last_seen_ts if keep_last_seen else now,
            updated_at=now,
        )

    async def _replace(
        self,
        stored: StoredScreen,
        key: _ScreenKey,
        rendered: RenderedScreen,
        *,
        notification: bool,
    ) -> UpdateOutcome:
        """Удаляет прежний экран и отправляет новый (push на новом событии).

        Ошибка удаления не прерывает обновление: прежнее сообщение могло быть
        удалено пользователем или ботом потерять права. Случай логируется на
        уровне WARNING, новое сообщение отправляется всегда.
        """
        deleted = await self._transport.delete_message(stored.chat_id, stored.msg_id)
        if not deleted:
            logger.warning(
                "Прежний экран не удалён (uid={} chat_id={} msg_id={}) — "
                "отправляю новое сообщение",
                key.uid,
                key.chat_id,
                stored.msg_id,
            )
        outcome = await self._send(key, rendered, notification=notification)
        if outcome is UpdateOutcome.SENT:
            return UpdateOutcome.REPLACED
        return outcome

    def _markup(self, rendered: RenderedScreen) -> Any:
        """Клавиатура экрана: строится билдером по показанным парам врачей.

        Без инъектированного билдера разметка не передаётся (``None``): пустую
        клавиатуру Telegram не принимает.
        """
        if self._keyboard_builder is None:
            return None
        return self._keyboard_builder(rendered.items)

    async def drop_screen(self, uid: int, kind: str = KIND_MONITOR) -> None:
        """Снимает запись экрана без обращения к Telegram (сброс состояния).

        Нужен там, где сообщение уже удалено или его нужно пересоздать с нуля:
        следующий :meth:`update_screen` отправит новый экран.
        """
        await self._store.forget(uid, kind)

    async def discard_screen(self, uid: int, kind: str = KIND_MONITOR) -> bool:
        """Удаляет сообщение экрана и запись о нём; возвращает ``True``.

        Удаление сообщения — best effort: ручное удаление пользователем или
        отсутствие прав не мешают снять запись (иначе экран остался бы
        «висящим» до бесконечности). Ошибка логируется на уровне WARNING.
        """
        stored = await self._store.get(uid, kind)
        if stored is not None:
            deleted = await self._transport.delete_message(
                stored.chat_id, stored.msg_id
            )
            if not deleted:
                logger.warning(
                    "Сообщение экрана не удалено (uid={} chat_id={} msg_id={}) — "
                    "запись всё равно снимается",
                    uid,
                    stored.chat_id,
                    stored.msg_id,
                )
        await self._store.forget(uid, kind)
        return True

    def _build_record(
        self, key: _ScreenKey, rendered: RenderedScreen, message_id: int
    ) -> StoredScreen:
        """Собирает запись экрана для сохранения; время берётся из ``clock``."""
        now = self._clock()
        return StoredScreen(
            uid=key.uid,
            kind=KIND_MONITOR,
            chat_id=key.chat_id,
            msg_id=message_id,
            content_type=CONTENT_TYPE_TEXT,
            render_hash=rendered.render_hash,
            last_seen_ts=now,
            updated_at=now,
        )


def _has_new_events(items: Sequence[ScreenItem]) -> bool:
    """Есть ли в наборе событие новее уже показанного."""
    return any(item.has_new_events for item in items)
