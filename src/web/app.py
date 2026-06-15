"""
Создание FastAPI-приложения для веб-дашборда и Telegram Mini App.

Фабрика create_app() регистрирует middleware, статику, шаблоны и роутеры.
Запускается как asyncio.Task в том же event loop, что и aiogram-бот.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.config import Settings
from src.database.manager import DatabaseManager
from src.services.healthcheck import HealthMetrics
from src.services.metrics import PrometheusMetrics

if TYPE_CHECKING:
    from src.api.zdrav_client import ZdravClient

logger = logging.getLogger(__name__)


class StaticNoCacheMiddleware:
    """
    Чистый ASGI middleware для отключения кэширования статики (/app/* и /static/*).

    В отличие от BaseHTTPMiddleware (который работает через StreamingResponse
    и не совместим со StaticFiles, смонтированными через app.mount()),
    этот middleware работает напрямую с ASGI scope/receive/send
    и гарантированно добавляет заголовки ко всем ответам /app/* и /static/*.

    Cloudflare CDN и браузеры агрессивно кэшируют JS/CSS,
    из-за чего обновления фронтенда (как дашборда, так и Mini App)
    не доходят до пользователей даже после пересборки Docker-образа.

    Устанавливает:
    - Cache-Control: no-cache, no-store, must-revalidate
    - CDN-Cache-Control: no-cache (специфичный для Cloudflare)
    - Pragma: no-cache (обратная совместимость с HTTP/1.0)
    - Expires: 0 (немедленное истечение)
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        if not (path.startswith("/app/") or path.startswith("/static/")):
            await self.app(scope, receive, send)
            return

        async def _send(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers: dict[bytes, bytes] = dict(message.get("headers", []))
                headers[b"cache-control"] = b"no-cache, no-store, must-revalidate"
                headers[b"cdn-cache-control"] = b"no-cache"
                headers[b"pragma"] = b"no-cache"
                headers[b"expires"] = b"0"
                message["headers"] = list(headers.items())
            await send(message)

        await self.app(scope, receive, _send)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # startup: singleton'ы уже созданы в main.py, ничего не делаем
    yield
    # shutdown: uvicorn.Server остановит себя сам при task.cancel()


def create_app(
    db: DatabaseManager,
    health_metrics: HealthMetrics,
    prometheus_metrics: PrometheusMetrics,
    config: Settings,
    zdrav_client: "ZdravClient | None" = None,
) -> FastAPI:
    """Фабрика FastAPI-приложения веб-дашборда и Mini App."""
    app = FastAPI(
        title="ZdravLenReg Dashboard",
        description="Веб-дашборд мониторинга zdrav.lenreg.ru",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Singleton'ы в app.state
    app.state.db = db
    app.state.health_metrics = health_metrics
    app.state.prometheus_metrics = prometheus_metrics
    app.state.config = config
    app.state.zdrav_client = zdrav_client  # API-клиент для Mini App

    # Middleware аутентификации дашборда (только для путей /, /users, /logs и т.д.)
    from src.web.auth import APIKeyMiddleware

    if config.WEB_DASHBOARD_API_KEY:
        logger.info("APIKeyMiddleware: включен (API-ключ задан)")
        app.add_middleware(APIKeyMiddleware, api_key=config.WEB_DASHBOARD_API_KEY)
    else:
        logger.debug("APIKeyMiddleware: отключен (API-ключ не задан)")

    # Middleware аутентификации Mini App (initData) — только для /api/user/*
    if config.MINI_APP_ENABLED:
        from src.web.auth_initdata import TelegramInitDataMiddleware

        app.add_middleware(TelegramInitDataMiddleware)
        logger.debug("TelegramInitDataMiddleware: включен (MINI_APP_ENABLED=True)")

    # Статика и шаблоны
    import os
    import time as time_module

    _static_dir = os.path.join(os.path.dirname(__file__), "static")
    _templates_dir = os.path.join(os.path.dirname(__file__), "templates")

    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

    templates = Jinja2Templates(directory=_templates_dir)

    # Кастомные фильтры Jinja2
    def _strftime_filter(ts: float) -> str:
        """Преобразует Unix timestamp в строку ЧЧ:ММ:СС."""
        try:
            return time_module.strftime("%H:%M:%S", time_module.localtime(ts))
        except (OSError, ValueError, OverflowError):
            return str(ts)

    templates.env.filters["strftime"] = _strftime_filter
    app.state.templates = templates

    # Роутеры
    from src.web.routers import api, backup_api, pages

    app.include_router(pages.router)  # HTML-страницы
    app.include_router(api.router, prefix="/api")  # JSON API дашборда
    app.include_router(backup_api.router)  # JSON API бэкапов (/api/backups/*)

    # Отключаем кэширование ВСЕХ статических файлов (/app/* и /static/*)
    # на уровне HTTP-заголовков. Cloudflare CDN и браузеры агрессивно
    # кэшируют JS/CSS, из-за чего обновления фронтенда (и дашборда,
    # и Mini App) не доходят до пользователей после пересборки образа.
    app.add_middleware(StaticNoCacheMiddleware)
    logger.debug("StaticNoCacheMiddleware: включен для /app/* и /static/*")

    # Роутер Mini App API (/api/user/*)
    if config.MINI_APP_ENABLED:
        from src.web.routers import user_api

        app.include_router(user_api.router)

    # Mount статики Mini App (/app/) — после роутеров, чтобы StaticFiles
    # не перехватывал запросы к /api/user/*
    if config.MINI_APP_ENABLED:
        _app_static_dir = os.path.join(_static_dir, "app")
        if os.path.isdir(_app_static_dir):
            app.mount(
                "/app",
                StaticFiles(directory=_app_static_dir, html=True),
                name="mini_app",
            )
        else:
            logger.error(
                "Mini App static: директория %s не найдена — "
                "статика /app/ не смонтирована!",
                _app_static_dir,
            )

    return app
