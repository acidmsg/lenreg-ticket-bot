"""Middleware бейджа неподтверждённых алертов (DASH-5).

Кладёт число неподтверждённых записей в ``scope["state"]``, откуда его
читает базовый шаблон (``request.state.unacked_alerts``). Счётчик нужен
всем страницам, поэтому он считается в одном месте, а не в каждом
обработчике.

Реализация — чистый ASGI: ``BaseHTTPMiddleware`` работает через
``StreamingResponse`` и несовместим со статикой и SSE-потоком
(см. ``StaticNoCacheMiddleware``).
"""

from __future__ import annotations

import time
from typing import Any

from loguru import logger


class AlertsBadgeMiddleware:
    """Подсчёт неподтверждённых алертов для бейджа в сайдбаре.

    Счётчик нужен только HTML-страницам (бейдж в сайдбаре), поэтому статика,
    health-пробы, API и SSE-поток запрос к БД не делают. Значение кэшируется
    на ``CACHE_TTL_SECONDS``: при переходе между страницами не нужен новый
    ``COUNT(*)``, а свежесть бейджа остаётся приемлемой.
    """

    CACHE_TTL_SECONDS = 5.0

    def __init__(self, app: Any, db: Any) -> None:
        self.app = app
        self.db = db
        self._cache: tuple[float, int] | None = None

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if self._wants_html(scope):
            state = scope.setdefault("state", {})
            try:
                state["unacked_alerts"] = await self._count()
            except Exception:
                logger.debug(
                    "Бейдж алертов: не удалось получить счётчик", exc_info=True
                )
                state["unacked_alerts"] = 0

        await self.app(scope, receive, send)

    @staticmethod
    def _wants_html(scope: dict) -> bool:
        """Запрос ждёт HTML (браузер), а не статику/API/SSE."""
        for name, value in scope.get("headers", []):
            if name == b"accept":
                return b"text/html" in value
        return False

    async def _count(self) -> int:
        """Счётчик из кэша или из БД (не чаще раза в ``CACHE_TTL_SECONDS``)."""
        now = time.monotonic()
        if self._cache is not None and now - self._cache[0] < self.CACHE_TTL_SECONDS:
            return self._cache[1]
        count = await self.db.unacked_alerts_count()
        self._cache = (now, count)
        return count
