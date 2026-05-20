"""
Модуль аутентификации веб-дашборда.

Проверяет X-API-Key заголовок через middleware.
Если WEB_DASHBOARD_API_KEY пуст — аутентификация отключена.
"""

from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Middleware для проверки X-API-Key заголовка."""

    def __init__(self, app, api_key: str = ""):
        super().__init__(app)
        self._api_key = api_key

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Если ключ не задан — пропускаем все запросы
        if not self._api_key:
            return await call_next(request)

        # Проверяем заголовок X-API-Key
        api_key = request.headers.get("X-API-Key")
        if api_key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API-ключ не предоставлен",
            )
        if api_key != self._api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный API-ключ",
            )

        return await call_next(request)
