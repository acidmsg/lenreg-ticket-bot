"""Отправка уведомлений в Telegram: rate limiting, обработка 429, телеметрия.

Перенесено из `src.services.monitor` без изменения логики: сервис мониторинга
больше не знает о Telegram-транспорте, отправка вынесена в отдельный модуль
слоя services. Полезная нагрузка передаётся dataclass-объектом
:class:`TelegramMessage`, чтобы не нарушать порог `PLR0913` (max-args = 5).
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, TypeVar

import aiolimiter
from aiogram import Bot
from aiogram import exceptions as tg_exceptions
from loguru import logger

from src.services.telegram_health import (
    TELEGRAM_SEND_RATE_LIMIT,
    TELEGRAM_SEND_RATE_PERIOD,
    telegram_health,
)
from src.utils.protocols import LastMessageStore
from src.utils.telegram_utils import send_or_update_message

# ── Rate limiter уведомлений Telegram (per-loop) ──────────────────────
# Telegram Bot API: ≤ 25 сообщений/сек суммарно — параметры лимита сохраняются.
_TELEGRAM_MAX_RATE = TELEGRAM_SEND_RATE_LIMIT
_TELEGRAM_TIME_PERIOD = TELEGRAM_SEND_RATE_PERIOD

# Реестр лимитеров по event loop'у. Ключ — сам loop (не id): id переиспользуется
# после сборки мусора, что привело бы к ложному попаданию в чужой лимитер.
_telegram_limiters: dict[asyncio.AbstractEventLoop, aiolimiter.AsyncLimiter] = {}


def _prune_closed_loops() -> None:
    """Удаляет из реестра лимитеры закрытых event loop'ов.

    ``WeakKeyDictionary`` здесь неприменим: ``aiolimiter.AsyncLimiter`` хранит в
    слоте ``_event_loop`` **сильную** ссылку на loop, поэтому значение удерживает
    свой ключ и слабое связывание не освобождает записи. Явная очистка по
    ``is_closed()`` делает рост структуры ограниченным числом живых loop'ов:
    в production loop ровно один, в тестах записи прежних loop'ов удаляются при
    следующем обращении.
    """
    for loop in [item for item in _telegram_limiters if item.is_closed()]:
        del _telegram_limiters[loop]


def _get_telegram_limiter() -> aiolimiter.AsyncLimiter:
    """Возвращает лимитер отправки уведомлений для текущего event loop.

    Лимитер — это пропускной шлюз, а не защита разделяемого состояния, поэтому
    его допустимо создавать per-loop (в отличие от ``Lock`` и ``Event``).
    Общая семантика 25 сообщений/с не нарушается: в production отправитель
    уведомлений ровно один — фоновая задача мониторинга в главном event loop,
    и она получает из реестра единственный экземпляр. В тестах каждый loop
    получает свежий лимитер, что устраняет перепривязку ``aiolimiter`` и
    ``RuntimeWarning`` о переиспользовании экземпляра между loop'ами.

    Вызывается только из корутины: без running loop ``get_running_loop()``
    возбуждает ``RuntimeError`` — это контракт, а не ошибка.
    """
    loop = asyncio.get_running_loop()
    _prune_closed_loops()
    limiter = _telegram_limiters.get(loop)
    if limiter is None:
        limiter = aiolimiter.AsyncLimiter(
            max_rate=_TELEGRAM_MAX_RATE,
            time_period=_TELEGRAM_TIME_PERIOD,
        )
        _telegram_limiters[loop] = limiter
    return limiter


@dataclass(frozen=True)
class TelegramMessage:
    """Полезная нагрузка одной отправки в Telegram."""

    p_id: str
    d_id: str
    text: str
    photo_path: Path | None = None
    reply_markup: Any = None


async def send_telegram_message(
    bot: Bot,
    chat_id: int,
    store: LastMessageStore,
    message: TelegramMessage,
) -> bool:
    """Отправка уведомления в Telegram с rate limiting и обработкой 429.

    Обёртка над :func:`send_or_update_message`, которая:
    - Применяет per-loop лимитер ``_get_telegram_limiter()`` (≤25 сообщений/сек
      суммарно для отправителя).
    - Перехватывает ``TelegramRetryAfter`` (429), ждёт ``retry_after``
      и повторяет отправку один раз.
    - Логирует все ошибки отправки.
    - Пишет результат в :data:`~src.services.telegram_health.telegram_health`:
      глубина очереди, успешные/неудачные отправки, паузы по 429 (UX-7).

    Returns:
        True если отправка успешна, False при ошибке.
    """
    telegram_health.queue_enter()
    try:
        async with _get_telegram_limiter():
            try:
                await send_or_update_message(
                    bot,
                    chat_id,
                    store,
                    message.p_id,
                    message.d_id,
                    message.text,
                    photo_path=message.photo_path,
                    reply_markup=message.reply_markup,
                )
            except tg_exceptions.TelegramRetryAfter as e:
                logger.warning(
                    "Telegram 429: retry after {:.1f}s for chat {}",
                    e.retry_after,
                    chat_id,
                )
                telegram_health.record_retry_after(e.retry_after)
                await asyncio.sleep(e.retry_after)
                try:
                    await send_or_update_message(
                        bot,
                        chat_id,
                        store,
                        message.p_id,
                        message.d_id,
                        message.text,
                        photo_path=message.photo_path,
                        reply_markup=message.reply_markup,
                    )
                except Exception as e2:
                    logger.opt(exception=True).error(
                        "Telegram retry failed for chat {}: {}",
                        chat_id,
                        e2,
                    )
                    telegram_health.record_send_error()
                    return False
            except Exception as e:
                logger.opt(exception=True).error(
                    "Telegram send failed for chat {}: {}",
                    chat_id,
                    e,
                )
                telegram_health.record_send_error()
                return False

        telegram_health.record_send_ok()
        return True
    finally:
        telegram_health.queue_exit()


# ── Операции единого экрана чата ─────────────────────────────────────

_ScreenResult = TypeVar("_ScreenResult")


async def _run_with_retry(
    chat_id: int,
    action: str,
    operation: Callable[[], Awaitable[_ScreenResult]],
) -> _ScreenResult | None:
    """Выполняет операцию Telegram под лимитером с одним повтором после 429.

    Повторяет правила :func:`send_telegram_message` для операций экрана:
    общий per-loop лимитер, ``TelegramRetryAfter`` → пауза и один retry,
    прочие ``TelegramAPIError`` → WARNING и ``None`` (исключения не выходят за
    пределы транспорта).
    """
    try:
        async with _get_telegram_limiter():
            try:
                return await operation()
            except tg_exceptions.TelegramRetryAfter as e:
                logger.warning(
                    "Telegram 429 ({}): retry after {:.1f}s for chat {}",
                    action,
                    e.retry_after,
                    chat_id,
                )
                telegram_health.record_retry_after(e.retry_after)
                await asyncio.sleep(e.retry_after)
                return await operation()
    except tg_exceptions.TelegramAPIError as e:
        logger.opt(exception=True).warning(
            "Telegram {} failed for chat {}: {}", action, chat_id, e
        )
        return None


async def send_text(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_markup: Any = None,
    disable_notification: bool = False,
) -> int | None:
    """Отправляет текстовое сообщение и возвращает ``message_id``.

    Используется единым экраном чата: ``disable_notification`` включается для
    отправок без новых событий (создание экрана, восстановление после
    удаления сообщения пользователем).
    """
    message = await _run_with_retry(
        chat_id,
        "send_text",
        lambda: bot.send_message(
            chat_id,
            text,
            reply_markup=reply_markup,
            disable_notification=disable_notification,
        ),
    )
    if message is None:
        return None
    return message.message_id


async def delete_message(bot: Bot, chat_id: int, message_id: int) -> bool:
    """Удаляет сообщение; ошибка подавляется с WARNING, результат — флаг успеха."""
    result = await _run_with_retry(
        chat_id, "delete_message", lambda: bot.delete_message(chat_id, message_id)
    )
    return result is not None


# ── Правка сообщения-экрана ──────────────────────────────────────────


class EditOutcome(StrEnum):
    """Исход правки сообщения-экрана через ``editMessageText``."""

    EDITED = "edited"
    """Текст успешно изменён."""

    NOT_MODIFIED = "not_modified"
    """Telegram отклонил правку: содержимое уже совпадает (штатный сценарий)."""

    NOT_FOUND = "not_found"
    """Сообщения нет (удалено пользователем) — нужен fallback на replace."""

    CANNOT_EDIT = "cannot_edit"
    """Сообщение нельзя править (тип вложения, нет текста) — нужен replace."""

    FAILED = "failed"
    """Прочая ошибка: сеть, права доступа, неизвестный 400."""


# Маркеры ответа Telegram: сравнение идёт по вхождению в нижнем регистре,
# поэтому формулировки бота и префикс «Bad Request:» не влияют на разбор.
_NOT_MODIFIED_MARKERS: tuple[str, ...] = ("message is not modified",)
_NOT_FOUND_MARKERS: tuple[str, ...] = ("message to edit not found",)
_CANNOT_EDIT_MARKERS: tuple[str, ...] = (
    "message can't be edited",
    "message can not be edited",
    "there is no text in the message to edit",
)


def _classify_bad_request(message: str) -> EditOutcome:
    """Сопоставляет текст ``TelegramBadRequest`` с исходом правки.

    Args:
        message: Текст исключения ``TelegramBadRequest``.

    Returns:
        :class:`EditOutcome`; неизвестный текст — ``FAILED``.
    """
    text = message.lower()
    if any(marker in text for marker in _NOT_MODIFIED_MARKERS):
        return EditOutcome.NOT_MODIFIED
    if any(marker in text for marker in _NOT_FOUND_MARKERS):
        return EditOutcome.NOT_FOUND
    if any(marker in text for marker in _CANNOT_EDIT_MARKERS):
        return EditOutcome.CANNOT_EDIT
    return EditOutcome.FAILED


def _log_edit_rejection(
    outcome: EditOutcome, chat_id: int, message_id: int, detail: str
) -> None:
    """Логирует отклонённую правку: штатные случаи — INFO, прочие — ERROR."""
    if outcome is EditOutcome.NOT_MODIFIED:
        logger.info("Экран уже актуален (chat_id={} msg_id={})", chat_id, message_id)
    elif outcome is EditOutcome.NOT_FOUND:
        logger.info(
            "Сообщение-экран не найдено (chat_id={} msg_id={}): {}",
            chat_id,
            message_id,
            detail,
        )
    elif outcome is EditOutcome.CANNOT_EDIT:
        logger.warning(
            "Экран нельзя отредактировать (chat_id={} msg_id={}): {}",
            chat_id,
            message_id,
            detail,
        )
    else:
        logger.error(
            "Правка экрана отклонена (chat_id={} msg_id={}): {}",
            chat_id,
            message_id,
            detail,
        )


async def edit_text(
    bot: Bot,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: Any = None,
) -> EditOutcome:
    """Правит текст сообщения-экрана и классифицирует ответ Telegram.

    Общий per-loop лимитер и общий ретрай :func:`_run_with_retry` используются
    как есть: обработка 429 не дублируется, повтор выполняется один раз.
    ``TelegramBadRequest`` перехватывается внутри операции, поэтому наружу
    выходит не исключение, а :class:`EditOutcome`.

    Args:
        bot: Экземпляр Telegram-бота.
        chat_id: Чат, в котором живёт сообщение-экран.
        message_id: Идентификатор правимого сообщения.
        text: Новый текст экрана.
        reply_markup: Клавиатура экрана (``None`` — оставить прежнюю).

    Returns:
        Исход правки; ``FAILED`` при сетевой ошибке, ошибке прав доступа или
        неизвестном 400.
    """

    async def _edit() -> EditOutcome:
        try:
            await bot.edit_message_text(
                text=text,
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=reply_markup,
            )
        except tg_exceptions.TelegramBadRequest as exc:
            outcome = _classify_bad_request(str(exc))
            _log_edit_rejection(outcome, chat_id, message_id, str(exc))
            return outcome
        return EditOutcome.EDITED

    outcome = await _run_with_retry(chat_id, "edit_text", _edit)
    if outcome is None:
        return EditOutcome.FAILED
    return outcome
