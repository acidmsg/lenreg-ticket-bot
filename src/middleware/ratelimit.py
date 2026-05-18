"""
Per-user rate limiting middleware for aiogram (Redis-backed).

Использует Redis Sorted Sets для реализации sliding window rate limiting.
Ключи: ratelimit:msg:{user_id} и ratelimit:cb:{user_id}
Временные метки хранятся в ZSET, автоматически очищаются по TTL.

При недоступности Redis пропускает запросы без ограничений (graceful degradation).
"""

import time

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message
from loguru import logger

from src.config import settings
from src.utils.redis import get_redis


class UserRateLimitMiddleware(BaseMiddleware):
    """
    Per-user sliding window rate limiter на Redis Sorted Sets.

    Каждый запрос добавляет текущий timestamp в ZSET пользователя.
    При проверке удаляются устаревшие записи и подсчитывается количество
    оставшихся в окне. При превышении лимита запросы молча отбрасываются.

    Callback-запросы лимитируются отдельно от сообщений.
    """

    def __init__(self) -> None:
        super().__init__()
        self.max_req: int = settings.USER_RATE_LIMIT_MAX
        self.period: int = settings.USER_RATE_LIMIT_PERIOD

    async def _is_limited(self, user_id: int, is_callback: bool = False) -> bool:
        """
        Проверяет, превышен ли лимит для пользователя.

        Использует атомарную Redis-операцию: ZREMRANGEBYSCORE + ZADD + ZCARD
        через pipeline для обеспечения консистентности sliding window.

        При недоступности Redis пропускает запросы без ограничений
        (graceful degradation).
        """
        redis = await get_redis()

        # Graceful degradation: если Redis недоступен, пропускаем без лимитов
        if not redis.is_available:
            return False

        now = time.time()
        cutoff = now - self.period

        key = f"ratelimit:{'cb' if is_callback else 'msg'}:{user_id}"

        async with await redis.pipeline() as pipe:
            # 1. Удаляем устаревшие записи (старше cutoff)
            await pipe.zremrangebyscore(key, 0, cutoff)
            # 2. Добавляем текущий запрос
            await pipe.zadd(key, {str(now): now})
            # 3. Считаем оставшиеся в окне
            await pipe.zcard(key)
            # 4. Устанавливаем TTL на ключ (период + запас)
            await pipe.expire(key, self.period + 10)

            results = await pipe.execute()

        # results[2] — ZCARD (количество записей после добавления)
        count: int = results[2]

        if count > self.max_req:
            logger.warning(
                f"Rate limit exceeded for user {user_id} "
                f"({'callback' if is_callback else 'message'}): "
                f"{count}/{self.max_req} in {self.period}s"
            )
            return True

        return False

    async def __call__(self, handler, event, data):
        # Determine user_id and event type
        if isinstance(event, Message):
            if not event.from_user:
                return await handler(event, data)
            user_id = event.from_user.id
            is_callback = False
        elif isinstance(event, CallbackQuery):
            if not event.from_user:
                return await handler(event, data)
            user_id = event.from_user.id
            is_callback = True
        else:
            # Pass through non-message/callback updates
            return await handler(event, data)

        if await self._is_limited(user_id, is_callback):
            # Silently drop (or optionally answer callback to dismiss spinner)
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer("⏳ Слишком много запросов, подождите...")
                except Exception:
                    pass
            return

        return await handler(event, data)
