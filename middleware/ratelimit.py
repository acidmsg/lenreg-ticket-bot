"""
Per-user rate limiting middleware for aiogram.

Uses a sliding window approach with TTLCache to track per-user
message timestamps. Users exceeding the limit get their messages
silently dropped (or optionally warned).
"""

import logging
import time

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message
from cachetools import TTLCache

from config import settings

logger = logging.getLogger(__name__)


class UserRateLimitMiddleware(BaseMiddleware):
    """
    Per-user sliding window rate limiter.

    Tracks timestamps of each user's messages. If the user exceeds
    USER_RATE_LIMIT_MAX messages in USER_RATE_LIMIT_PERIOD seconds,
    subsequent messages are silently ignored.

    Callback queries are also rate-limited (separately from messages).
    """

    def __init__(self):
        super().__init__()

        # Per-user message timestamps: {user_id: [timestamp, ...]}
        self._messages: dict[int, list[float]] = {}

        # Per-user callback timestamps
        self._callbacks: dict[int, list[float]] = {}

        # Cache for rate-limited users to avoid repeated logging
        self._warned: TTLCache = TTLCache(
            maxsize=5000, ttl=settings.USER_RATE_LIMIT_PERIOD
        )

        self.max_req = settings.USER_RATE_LIMIT_MAX
        self.period = settings.USER_RATE_LIMIT_PERIOD

    def _is_limited(self, user_id: int, is_callback: bool = False) -> bool:
        """Check if user exceeded rate limit. Prunes old timestamps."""
        now = time.time()
        store = self._callbacks if is_callback else self._messages

        if user_id not in store:
            store[user_id] = [now]
            return False

        timestamps = store[user_id]

        # Prune timestamps outside the window
        cutoff = now - self.period
        timestamps[:] = [t for t in timestamps if t > cutoff]

        if len(timestamps) >= self.max_req:
            if user_id not in self._warned:
                logger.warning(
                    f"Rate limit exceeded for user {user_id} "
                    f"({len(timestamps)}/{self.max_req} in {self.period}s)"
                )
                self._warned[user_id] = True
            return True

        timestamps.append(now)
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

        if self._is_limited(user_id, is_callback):
            # Silently drop (or optionally answer callback to dismiss spinner)
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer("⏳ Слишком много запросов, подождите...")
                except Exception:
                    pass
            return

        return await handler(event, data)
