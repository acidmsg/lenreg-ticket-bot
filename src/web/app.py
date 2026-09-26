"""
Создание FastAPI-приложения для веб-дашборда и Telegram Mini App.

Фабрика create_app() регистрирует middleware, статику, шаблоны и роутеры.
Приложение запускается как ``asyncio.Task`` (``uvicorn.Server.serve()``) в том же
event loop'е, что и aiogram-бот, фоновые задачи и Prometheus-сервер: loop-bound
ресурсы (``api``, ``db``, метрики) используются без перехода между потоками.

Единый event loop процесса — TD-009, этап 2:
[`event-loop-ownership.md`](../../specs/design/event-loop-ownership.md:1).
"""

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger

from src.config import Settings
from src.database.manager import DatabaseManager
from src.services.healthcheck import HealthMetrics
from src.services.metrics import PrometheusMetrics

if TYPE_CHECKING:
    from src.api.zdrav_client import ZdravClient


class StaticNoCacheMiddleware:
    """
    Чистый ASGI middleware для отключения кэширования ВСЕХ ответов сервера.

    В отличие от BaseHTTPMiddleware (который работает через StreamingResponse
    и не совместим со StaticFiles, смонтированными через app.mount()),
    этот middleware работает напрямую с ASGI scope/receive/send
    и гарантированно добавляет заголовки ко всем HTTP-ответам.

    Cloudflare CDN и браузеры агрессивно кэшируют HTML-страницы, JS и CSS,
    из-за чего обновления фронтенда (как дашборда, так и Mini App)
    не доходят до пользователей даже после пересборки Docker-образа.
    В частности, отсутствие Cache-Control на HTML-страницах дашборда
    приводит к тому, что Cloudflare отдаёт закэшированную версию sidebar'а
    без новых ссылок (например, /settings).

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


# Параметры запроса, которые безопасно писать в журнал длительности:
# идентификаторы клиник/пациентов/врачей нужны для разбора инцидентов и не
# являются секретами. initData, токены и прочие чувствительные значения
# в журнал не попадают.
_LOGGED_QUERY_PARAMS = frozenset(
    {"clinic_id", "patient_id", "doctor_id", "monitoring_id", "specialty_id"}
)


def _format_logged_params(query_string: bytes) -> str:
    """Собирает безопасную часть query-строки для журнала длительности.

    Args:
        query_string: сырая query-строка ASGI-scope (bytes).

    Returns:
        Строка вида ``" clinic_id=62 patient_id=2343192"`` (с ведущим пробелом)
        либо пустая строка, если логировать нечего.
    """
    if not query_string:
        return ""
    try:
        pairs = parse_qsl(query_string.decode("latin-1"), keep_blank_values=False)
    except (UnicodeDecodeError, ValueError):
        return ""

    filtered = [
        (key, value) for key, value in pairs if key in _LOGGED_QUERY_PARAMS and value
    ]
    if not filtered:
        return ""
    return " " + " ".join(f"{key}={value}" for key, value in sorted(filtered))


class RequestDurationMiddleware:
    """Логирует длительность обработки запросов к API.

    В access-логе uvicorn нет длительностей, а запрос, оборванный клиентом
    (например, 20-секундным таймаутом Mini App), в журнал не попадает вовсе —
    поэтому «сервер не отвечает» нельзя отличить от «сервер отвечал медленно».
    Middleware замеряет время от входа до ``http.response.start`` и пишет
    метод, путь, безопасные параметры, статус и длительность; запросы дольше
    :attr:`SLOW_THRESHOLD_MS` поднимаются до WARNING с пометкой «МЕДЛЕННО»,
    чтобы их было видно без грепа по числам.

    Логируются только прикладные пути (``/api/``): статика дашборда и Mini App
    журнал не засоряет.
    """

    SLOW_THRESHOLD_MS = 3000.0

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()

        async def _send(message: dict) -> None:
            if message["type"] == "http.response.start":
                duration_ms = (time.perf_counter() - started) * 1000
                self._log(
                    scope,
                    status=message.get("status", 0),
                    duration_ms=duration_ms,
                )
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except Exception:
            duration_ms = (time.perf_counter() - started) * 1000
            logger.opt(exception=True).warning(
                "HTTP {} {}{} → исключение за {:.0f} мс",
                scope.get("method", ""),
                scope.get("path", ""),
                _format_logged_params(scope.get("query_string", b"")),
                duration_ms,
            )
            raise

    @classmethod
    def _log(cls, scope: dict, status: int, duration_ms: float) -> None:
        """Пишет строку о длительности запроса.

        Args:
            scope: ASGI-scope запроса.
            status: HTTP-статус ответа.
            duration_ms: длительность обработки в миллисекундах.
        """
        method = scope.get("method", "")
        path = scope.get("path", "")
        params = _format_logged_params(scope.get("query_string", b""))
        if duration_ms >= cls.SLOW_THRESHOLD_MS:
            logger.warning(
                "МЕДЛЕННО: HTTP {} {}{} → {} за {:.0f} мс",
                method,
                path,
                params,
                status,
                duration_ms,
            )
        else:
            logger.info(
                "HTTP {} {}{} → {} за {:.0f} мс",
                method,
                path,
                params,
                status,
                duration_ms,
            )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # startup: singleton'ы уже созданы в main.py, ничего не делаем.
    # Создавать здесь ресурсы запрещено: они принадлежат процессу и его event
    # loop'у, а не HTTP-приложению (см. event-loop-ownership.md, вариант C).
    yield
    # shutdown: остановкой управляет Server.serve() — main() выставляет
    # server.should_exit = True и дренирует задачу; task.cancel() не используется.


def create_app(
    db: DatabaseManager,
    health_metrics: HealthMetrics,
    prometheus_metrics: PrometheusMetrics,
    config: Settings,
    zdrav_client: "ZdravClient | None" = None,
) -> FastAPI:
    """Фабрика FastAPI-приложения веб-дашборда и Mini App."""
    app = FastAPI(
        title="LenReg Ticket Bot Dashboard",
        description="Веб-дашборд мониторинга zdrav.lenreg.ru",
        version="1.4.0",
        lifespan=lifespan,
    )

    # Singleton'ы в app.state
    app.state.db = db
    app.state.health_metrics = health_metrics
    app.state.prometheus_metrics = prometheus_metrics
    app.state.config = config
    app.state.zdrav_client = zdrav_client  # API-клиент для Mini App

    # Session-based аутентификация дашборда (как в x-ui)
    # Заменяет Caddy basic auth и APIKeyMiddleware.
    # Middleware авторегистрируется через set_session_middleware() в __init__.
    from src.web.auth_session import SessionAuthMiddleware, hash_password

    password_hash = ""
    if config.WEB_DASHBOARD_PASSWORD:
        password_hash = hash_password(config.WEB_DASHBOARD_PASSWORD)

    app.add_middleware(
        SessionAuthMiddleware,
        username=config.WEB_DASHBOARD_USERNAME,
        password_hash=password_hash,
        secret=config.WEB_DASHBOARD_SECRET_KEY,
    )

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
    def _strftime_filter(ts: float, fmt: str = "%d.%m.%Y %H:%M:%S") -> str:
        """Преобразует Unix timestamp в строку по формату.

        По умолчанию — дата и время: журналы и история живут неделями, и одно
        время в строке не отвечает на вопрос «когда это было». Компактные
        блоки передают свой формат явно (``{{ ts|strftime('%d.%m %H:%M') }}``).
        """
        try:
            return time_module.strftime(fmt, time_module.localtime(ts))
        except (OSError, ValueError, OverflowError, TypeError):
            return str(ts)

    templates.env.filters["strftime"] = _strftime_filter
    app.state.templates = templates

    # Роутеры
    from src.web.routers import api, auth_pages, backup_api, pages, stream

    # auth_pages — до pages, чтобы /login не перехватывался
    app.include_router(auth_pages.router)
    app.include_router(pages.router)  # HTML-страницы
    app.include_router(api.router, prefix="/api")  # JSON API дашборда
    app.include_router(stream.router, prefix="/api")  # SSE-поток сводки (DASH-1)
    app.include_router(backup_api.router)  # JSON API бэкапов (/api/backups/*)

    # Отключаем кэширование ВСЕХ ответов сервера на уровне HTTP-заголовков.
    # Cloudflare CDN и браузеры агрессивно кэшируют HTML, JS и CSS,
    # из-за чего обновления фронтенда (и дашборда, и Mini App)
    # не доходят до пользователей после пересборки образа.
    app.add_middleware(StaticNoCacheMiddleware)
    logger.debug("StaticNoCacheMiddleware: включен для всех ответов сервера")

    # Замер длительности запросов к API: без него в access-логе нет
    # длительностей, а оборванный клиентом запрос не попадает в журнал вовсе.
    app.add_middleware(RequestDurationMiddleware)
    logger.debug("RequestDurationMiddleware: замер длительности /api/* включён")

    # Роутер Mini App API (/api/user/*)
    if config.MINI_APP_ENABLED:
        from src.web.routers import export_api, user_api

        app.include_router(user_api.router)
        # Скачивание файлов экспорта по подписанной ссылке (/api/export/*):
        # путь вне /api/user/*, поэтому middleware initData его не трогает.
        app.include_router(export_api.router)

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
                "Mini App static: директория {} не найдена — "
                "статика /app/ не смонтирована!",
                _app_static_dir,
            )

    return app
