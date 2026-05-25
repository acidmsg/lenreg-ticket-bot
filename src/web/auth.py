"""
Модуль аутентификации веб-дашборда.

Проверяет X-API-Key заголовок через middleware только для путей дашборда:
``/``, ``/users``, ``/logs``, ``/clinics``, ``/api-status``, ``/api/*``
(кроме ``/api/user/*``).

Публичные пути (``/app/``, ``/static/``, ``/api/user/``) не проверяются.
Если WEB_DASHBOARD_API_KEY пуст — аутентификация отключена.
"""

from collections.abc import Awaitable, Callable

from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

# Пути, которые НЕ требуют API-ключа (публичные)
_PUBLIC_PATH_PREFIXES = (
    "/app",
    "/static",
    "/api/user",
)


def _is_dashboard_path(path: str) -> bool:
    """Возвращает True, если путь относится к дашборду и требует API-ключ."""
    return all(not path.startswith(prefix) for prefix in _PUBLIC_PATH_PREFIXES)


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Middleware для проверки X-API-Key заголовка на путях дашборда."""

    def __init__(self, app, api_key: str = ""):
        super().__init__(app)
        self._api_key = api_key

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Если ключ не задан — пропускаем все запросы
        if not self._api_key:
            return await call_next(request)

        # Публичные пути (/app/, /static/, /api/user/) — пропускаем без проверки
        if not _is_dashboard_path(request.url.path):
            return await call_next(request)

        # Проверяем заголовок X-API-Key
        api_key = request.headers.get("X-API-Key")
        if api_key is None:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "API-ключ не предоставлен"},
            )
        if api_key != self._api_key:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Неверный API-ключ"},
            )

        return await call_next(request)
