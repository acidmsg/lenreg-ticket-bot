"""Отправка уведомлений в Telegram: rate limiting, обработка 429, телеметрия.

Перенесено из `src.services.monitor` без изменения логики: сервис мониторинга
больше не знает о Telegram-транспорте, отправка вынесена в отдельный модуль
слоя services. Полезная нагрузка передаётся dataclass-объектом
:class:`TelegramMessage`, чтобы не нарушать порог `PLR0913` (max-args = 5).
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
