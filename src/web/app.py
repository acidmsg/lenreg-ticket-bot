"""
Создание FastAPI-приложения для веб-дашборда.

Фабрика create_app() регистрирует middleware, статику, шаблоны и роутеры.
Запускается как asyncio.Task в том же event loop, что и aiogram-бот.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.config import Settings
from src.database.manager import DatabaseManager
from src.services.healthcheck import HealthMetrics
from src.services.metrics import PrometheusMetrics


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: singleton'ы уже созданы в main.py, ничего не делаем
    yield
    # shutdown: uvicorn.Server остановит себя сам при task.cancel()


def create_app(
    db: DatabaseManager,
    health_metrics: HealthMetrics,
    prometheus_metrics: PrometheusMetrics,
    config: Settings,
) -> FastAPI:
    """Фабрика FastAPI-приложения веб-дашборда."""
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

    # Middleware аутентификации
    from src.web.auth import APIKeyMiddleware

    if config.WEB_DASHBOARD_API_KEY:
        app.add_middleware(APIKeyMiddleware, api_key=config.WEB_DASHBOARD_API_KEY)

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
    app.include_router(api.router, prefix="/api")  # JSON API

    return app
