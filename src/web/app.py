"""
Создание FastAPI-приложения для веб-дашборда и Telegram Mini App.

Фабрика create_app() регистрирует middleware, статику, шаблоны и роутеры.
Запускается как asyncio.Task в том же event loop, что и aiogram-бот.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.config import Settings
from src.database.manager import DatabaseManager
from src.services.healthcheck import HealthMetrics
from src.services.metrics import PrometheusMetrics

if TYPE_CHECKING:
    from src.api.zdrav_client import ZdravClient

logger = logging.getLogger(__name__)


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

    # ── Глобальный exception handler ──
    @app.exception_handler(Exception)
    async def _global_exception_handler(request, exc):
        """Ловит необработанные исключения и логирует полный трейсбек."""
        from starlette.exceptions import HTTPException as StarletteHTTPException

        # HTTPException (401, 403, 404 и т.д.) — не перехватываем,
        # FastAPI сам возвращает правильный статус-код
        if isinstance(exc, StarletteHTTPException):
            raise exc

        from starlette.requests import Request as StarletteRequest

        if isinstance(request, StarletteRequest):
            logger.error(
                "Необработанное исключение для %s %s: %s",
                request.method,
                request.url.path,
                exc,
                exc_info=True,
            )
        else:
            logger.error("Необработанное исключение: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Внутренняя ошибка сервера"},
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
    from src.web.routers import api, pages

    app.include_router(pages.router)  # HTML-страницы
    app.include_router(api.router, prefix="/api")  # JSON API дашборда

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
