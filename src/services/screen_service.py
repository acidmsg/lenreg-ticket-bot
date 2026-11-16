"""
Сервис обновления единого экрана чата (single screen message), вариант B.

Единственная точка применения состояния экрана к чату. Сервис не знает ни о
Telegram, ни о слое ``src.database``: хранилище и транспорт приходят через
порты (:class:`~src.services.screen_port.ScreenStore`,
:class:`~src.services.notification_port.ScreenTransport`).

Стратегия:

- записи экрана нет → отправка нового сообщения (:attr:`UpdateOutcome.SENT`);
- hash совпал → проверка живости сообщения не чаще раза в
  ``probe_interval_sec``: эхо-правка тем же текстом. ``NOT_MODIFIED``
  подтверждает живость (:attr:`UpdateOutcome.NOOP`),
  ``NOT_FOUND``/``CANNOT_EDIT`` означают ручную очистку чата — экран
  пересоздаётся без звука (:attr:`UpdateOutcome.REPLACED`), ``FAILED``
  оставляет запись и возвращает ``NOOP`` с предупреждением;
- есть новые события либо тип вложения не текстовый → замена: удалить прежнее
  сообщение и отправить новое (:attr:`UpdateOutcome.REPLACED`). Именно замена
  доставляет push;
- новых событий нет и экран текстовый → тихая правка
  (:attr:`UpdateOutcome.EDITED`).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
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
from src.services.screen_render import RenderedScreen, ScreenContext, ScreenItem
from src.services.screen_render import render_screen as _render_screen
from src.services.telegram_sender import EditOutcome


class UpdateOutcome(StrEnum):
    """Итог применения состояния экрана к чату."""

    NOOP = "noop"
    """Состояние не изменилось: транспорт не вызывался либо сообщение живо."""

    SENT = "sent"
    """Экран отправлен впервые (записи не было)."""

    REPLACED = "replaced"
    """Прежний экран заменён новым сообщением (push или восстановление)."""

    EDITED = "edited"
    """Тихое обновление текста существующего экрана (push не доставляется)."""

    FAILED = "failed"
    """Отправка не удалась: запись экрана не изменена."""


@dataclass(frozen=True, slots=True)
class _ScreenKey:
    """Адресация экрана: пользователь и чат."""

    uid: int
    chat_id: int


def _screen_stats(
    stored: StoredScreen | None, context: ScreenContext, now: int
) -> dict[str, int]:
    """Счётчики проверок: инкремент по контексту текущего обновления.

    Одно сохранение записи — одно обновление экрана, поэтому ``check_count``
    растёт на единицу за сохранение. ``error_count`` аккумулирует число пар,
    чей запрос слотов завершился ошибкой (``context.iter_errors``);
    ``last_event_at`` сдвигается только при событиях, ``new_events_count``
    всегда равен числу событий текущей итерации. ``last_check_at`` берётся из
    контекста и нулём не затирает прежнее значение: ``/start`` проверок не
    выполняет.
    """
    if stored is None:
        base = {
            "last_check_at": 0,
            "check_count": 0,
            "error_count": 0,
            "last_event_at": 0,
            "new_events_count": 0,
        }
    else:
        base = {
            "last_check_at": stored.last_check_at,
            "check_count": stored.check_count,
            "error_count": stored.error_count,
            "last_event_at": stored.last_event_at,
            "new_events_count": stored.new_events_count,
        }
    return {
        "last_check_at": context.last_check_at or base["last_check_at"],
        "check_count": base["check_count"] + 1,
        "error_count": base["error_count"] + max(context.iter_errors, 0),
        "last_event_at": now if context.event_count > 0 else base["last_event_at"],
        "new_events_count": context.event_count,
    }


def _with_last_check(
    context: ScreenContext, stored: StoredScreen | None
) -> ScreenContext:
    """Дополняет контекст временем последней проверки из записи экрана.

    Монитор передаёт время актуальной итерации, а ``/start`` проверок не делает
    и передаёт ``0``. В этом случае показывается время из записи, иначе строка
    «Проверено …» превращалась бы в «проверка ещё не выполнялась» после каждого
    возврата в чат.
    """
    if context.last_check_at > 0 or stored is None or stored.last_check_at <= 0:
        return context
    return replace(context, last_check_at=stored.last_check_at)


@dataclass(frozen=True, slots=True)
class ScreenServiceOptions:
    """Необязательные зависимости сервиса экрана.

    Собраны в одну структуру, чтобы конструктор сервиса оставался коротким:
    все три параметра попадают в один аргумент ``options``.
    """

    on_outcome: Callable[[str], None] | None = None
    """Приёмник исходов (телеметрия); вызывается со строкой ``UpdateOutcome``."""

    keyboard_builder: Callable[[RenderedScreen], Any] | None = None
    """Билдер ``reply_markup`` по состоянию рендера (слой ``handlers``)."""

    probe_interval_sec: int | None = None
    """Интервал проверки живости; ``None`` — ``SCREEN_PROBE_INTERVAL_SEC``."""


class ScreenService:
    """Сервис обновления экрана чата; владелец per-chat локов экземпляра."""

    def __init__(
        self,
        store: ScreenStore,
        transport: ScreenTransport,
        clock: Callable[[], int],
        options: ScreenServiceOptions | None = None,
    ) -> None:
        """Сохраняет зависимости сервиса.

        Args:
            store: Хранилище записей экрана.
            transport: Транспорт отправки, правки и удаления сообщения.
            clock: Часы в Unix-секундах (тесты подменяют монотонным счётчиком).
            options: Необязательные зависимости: телеметрия, билдер клавиатуры
                (передаётся снаружи, потому что сервис не импортирует
                ``src.keyboards`` — дизайн §10.3) и интервал проверки живости.
        """
        active = options or ScreenServiceOptions()
        self._store = store
        self._transport = transport
        self._clock = clock
        self._render: Callable[..., RenderedScreen] = _render_screen
        self._on_outcome = active.on_outcome
        self._keyboard_builder = active.keyboard_builder
        self._probe_interval_sec = (
            settings.SCREEN_PROBE_INTERVAL_SEC
            if active.probe_interval_sec is None
            else active.probe_interval_sec
        )
        self._locks: dict[int, asyncio.Lock] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    async def update_screen(
        self, uid: int, chat_id: int, items: Sequence[ScreenItem]
    ) -> UpdateOutcome:
        """Применяет состояние экрана, собранное из одних пар, к чату.

        Узкая совместимая точка: персональный контекст (пациенты, записи, время
        проверки) не передаётся и остаётся дефолтным. Из пар выводится только
        число событий — оно нужно счётчикам записи экрана.
        """
        context = ScreenContext(
            items=tuple(items),
            monitored_pairs_count=len(items),
            event_count=sum(1 for item in items if item.has_new_events),
        )
        return await self.ensure_screen(uid, chat_id, context)

    async def ensure_screen(
        self, uid: int, chat_id: int, context: ScreenContext
    ) -> UpdateOutcome:
        """Гарантирует живой экран по полному состоянию и возвращает исход.

        Вызовы для одного чата сериализуются локом экземпляра сервиса, поэтому
        два параллельных обновления не могут отправить два экрана.
        """
        key = _ScreenKey(uid=uid, chat_id=chat_id)
        async with self._chat_lock(chat_id):
            outcome = await self._ensure(key, context)
        return self._report(outcome)

    async def _ensure(self, key: _ScreenKey, context: ScreenContext) -> UpdateOutcome:
        """Выбирает стратегию обновления по состоянию экрана и наличию событий.

        Запись читается до рендера: из неё берётся время последней проверки,
        если контекст его не передал (``/start``). Одно сохранение записи
        соответствует одному обновлению экрана — на этом построены счётчики.
        """
        stored = await self._store.get(key.uid, KIND_MONITOR)
        context = _with_last_check(context, stored)
        rendered = self._render(replace(context, now=context.now or self._clock()))
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
        notification = _has_new_events(context.items)
        if stored is None:
            return await self._send(key, rendered, context, notification=notification)
        if stored.render_hash == rendered.render_hash:
            return await self._ensure_alive(stored, key, rendered, context)
        if notification or stored.content_type != CONTENT_TYPE_TEXT:
            return await self._replace(
                stored, key, rendered, context, notification=notification
            )
        return await self._edit(stored, key, rendered, context)

    async def _ensure_alive(
        self,
        stored: StoredScreen,
        key: _ScreenKey,
        rendered: RenderedScreen,
        context: ScreenContext,
    ) -> UpdateOutcome:
        """Проверяет живость сообщения эхо-правкой; восстанавливает при потере.

        Проверка выполняется не чаще ``probe_interval_sec``: моментом
        последней проверки служит ``updated_at`` записи.
        """
        now = self._clock()
        if now - stored.updated_at < self._probe_interval_sec:
            return UpdateOutcome.NOOP
        outcome = await self._transport.edit_text(
            stored.chat_id,
            stored.msg_id,
            rendered.text,
            reply_markup=self._markup(rendered),
        )
        if outcome is EditOutcome.EDITED:
            await self._store.save(
                self._edited_record(
                    stored, rendered, context, keep_last_seen=True, updated_at=now
                )
            )
            return UpdateOutcome.EDITED
        if outcome is EditOutcome.NOT_MODIFIED:
            await self._store.save(
                self._edited_record(
                    stored, rendered, context, keep_last_seen=True, updated_at=now
                )
            )
            return UpdateOutcome.NOOP
        if outcome in (EditOutcome.NOT_FOUND, EditOutcome.CANNOT_EDIT):
            logger.info(
                "Проверка живости: сообщение экрана недоступно "
                "(uid={} chat_id={} msg_id={}, исход={}) — восстанавливаю",
                key.uid,
                key.chat_id,
                stored.msg_id,
                outcome.value,
            )
            return await self._replace(
                stored, key, rendered, context, notification=False
            )
        logger.warning(
            "Проверка живости экрана не удалась (uid={} chat_id={} msg_id={}) — "
            "запись оставлена без изменений",
            key.uid,
            key.chat_id,
            stored.msg_id,
        )
        return UpdateOutcome.NOOP

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
        self,
        key: _ScreenKey,
        rendered: RenderedScreen,
        context: ScreenContext,
        *,
        notification: bool,
        previous: StoredScreen | None = None,
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
        record = self._build_record(key, rendered, context, message_id, previous)
        if notification:
            # Событие доставлено push'ем: момент учтённого события сдвигается.
            record = replace(record, last_seen_ts=record.updated_at)
        await self._store.save(record)
        return UpdateOutcome.SENT

    async def _edit(
        self,
        stored: StoredScreen,
        key: _ScreenKey,
        rendered: RenderedScreen,
        context: ScreenContext,
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
                self._edited_record(stored, rendered, context, keep_last_seen=False)
            )
            return UpdateOutcome.EDITED
        if outcome is EditOutcome.NOT_MODIFIED:
            await self._store.save(
                self._edited_record(stored, rendered, context, keep_last_seen=True)
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
            return await self._replace(
                stored, key, rendered, context, notification=False
            )
        logger.error(
            "Правка экрана не удалась (uid={} chat_id={} msg_id={}) — "
            "запись оставлена без изменений",
            key.uid,
            key.chat_id,
            stored.msg_id,
        )
        return UpdateOutcome.FAILED

    def _edited_record(
        self,
        stored: StoredScreen,
        rendered: RenderedScreen,
        context: ScreenContext,
        *,
        keep_last_seen: bool,
        updated_at: int | None = None,
    ) -> StoredScreen:
        """Запись после успешной правки: тот же ``msg_id``, новый hash и время.

        При ``NOT_MODIFIED`` метка ``last_seen_ts`` сохраняется: новых событий
        не было, момент последнего учтённого события не сдвигается.
        """
        now = self._clock() if updated_at is None else updated_at
        return StoredScreen(
            uid=stored.uid,
            kind=stored.kind,
            chat_id=stored.chat_id,
            msg_id=stored.msg_id,
            content_type=stored.content_type,
            render_hash=rendered.render_hash,
            last_seen_ts=stored.last_seen_ts if keep_last_seen else now,
            updated_at=now,
            **_screen_stats(stored, context, now),
        )

    async def _replace(
        self,
        stored: StoredScreen,
        key: _ScreenKey,
        rendered: RenderedScreen,
        context: ScreenContext,
        *,
        notification: bool,
    ) -> UpdateOutcome:
        """Удаляет прежний экран и отправляет новый (push на новом событии).

        Ошибка удаления не прерывает обновление: прежнее сообщение могло быть
        удалено пользователем или бот потерять права. Случай логируется на
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
        outcome = await self._send(
            key, rendered, context, notification=notification, previous=stored
        )
        if outcome is UpdateOutcome.SENT:
            return UpdateOutcome.REPLACED
        return outcome

    def _markup(self, rendered: RenderedScreen) -> Any:
        """Клавиатура экрана: строится билдером по состоянию рендера.

        Без инъектированного билдера разметка не передаётся (``None``): пустую
        клавиатуру Telegram не принимает.
        """
        if self._keyboard_builder is None:
            return None
        return self._keyboard_builder(rendered)

    async def drop_screen(self, uid: int, kind: str = KIND_MONITOR) -> None:
        """Снимает запись экрана без обращения к Telegram (сброс состояния).

        Нужен там, где сообщение уже удалено или его нужно пересоздать с нуля:
        следующий :meth:`ensure_screen` отправит новый экран.
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
        self,
        key: _ScreenKey,
        rendered: RenderedScreen,
        context: ScreenContext,
        message_id: int,
        previous: StoredScreen | None,
    ) -> StoredScreen:
        """Собирает запись экрана для сохранения; время берётся из ``clock``.

        ``last_seen_ts`` переносится из прежней записи, когда новых событий не
        было: пересоздание сообщения не должно обнулять маркер новизны.
        """
        now = self._clock()
        return StoredScreen(
            uid=key.uid,
            kind=KIND_MONITOR,
            chat_id=key.chat_id,
            msg_id=message_id,
            content_type=CONTENT_TYPE_TEXT,
            render_hash=rendered.render_hash,
            last_seen_ts=now if previous is None else previous.last_seen_ts,
            updated_at=now,
            **_screen_stats(previous, context, now),
        )


def _has_new_events(items: Sequence[ScreenItem]) -> bool:
    """Есть ли в наборе событие новее уже показанного."""
    return any(item.has_new_events for item in items)
