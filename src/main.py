"""
Точка входа в Telegram-бота zdrav.lenreg.

Запускает aiogram-поллинг, фоновые задачи (мониторинг, discovery,
healthcheck, очистка), Prometheus-метрики и веб-дашборд.
"""

from __future__ import annotations

import asyncio
import os
import socket
import threading
import time
from contextlib import suppress
from typing import TYPE_CHECKING

import aiofiles.os
from aiogram import Bot, Dispatcher
from aiohttp import web
from loguru import logger

from src.api.zdrav_client import ZdravClient
from src.config import settings
from src.database.database import Database
from src.database.manager import DatabaseManager
from src.i18n import setup_i18n
from src.middleware.activity import ActivityLogMiddleware
from src.middleware.error_boundary import ErrorBoundaryMiddleware
from src.middleware.ratelimit import UserRateLimitMiddleware
from src.middleware.userdata import UserDataPreloadMiddleware
from src.services.cleanup import cleanup_loop
from src.services.doctor_discovery import discovery_loop, sync_clinic_names
from src.services.error_notifier import error_notifier
from src.services.healthcheck import healthcheck_loop, safe_set
from src.services.healthcheck import metrics as health_metrics
from src.services.metrics import prometheus_metrics
from src.services.monitor import monitor_loop
from src.utils.logging import setup_logging
from src.utils.proxy_discovery import (
    _parse_proxy_host_port,
    check_proxy_connectivity,
    discover_proxy,
)
from src.utils.redis import RedisClient

if TYPE_CHECKING:
    from aiogram.client.session.aiohttp import AiohttpSession

# Константы retry-логики для прокси и Telegram API
_PROXY_RETRIES = 3
_PROXY_RETRY_DELAY = 2.0  # секунд
_TG_RETRIES = 3
_TG_RETRY_DELAY = 3.0  # секунд


async def _bot_me_with_retry(
    bot: Bot, max_retries: int = _TG_RETRIES, delay: float = _TG_RETRY_DELAY
) -> None:
    """
    Проверяет связь с Telegram API через bot.me() с повторными попытками.

    Если прокси временно недоступен, даёт ему шанс восстановиться между попытками.
    """
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                f"Проверка связи с Telegram API (попытка {attempt}/{max_retries})..."
            )
            await bot.me()
            logger.info("Связь с Telegram API установлена")
            return
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(
                    f"Не удалось связаться с Telegram API "
                    f"(попытка {attempt}/{max_retries}): {e}. "
                    f"Повтор через {delay}с..."
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    f"Не удалось связаться с Telegram API "
                    f"после {max_retries} попыток: {e}"
                )
    if last_error is not None:
        raise last_error


async def _start_background_tasks(
    bot: Bot, api: ZdravClient, db: DatabaseManager, database: Database
) -> list[asyncio.Task[object]]:
    """Запускает все фоновые задачи.

    Вызывается ТОЛЬКО после успешной проверки связи с Telegram API,
    чтобы снизить нагрузку на IOCP в момент старта и избежать конкуренции
    с прокси-соединением.
    """
    tasks: list[asyncio.Task[object]] = []

    tasks.append(asyncio.create_task(monitor_loop(bot, api, db)))

    # Один агрегированный discovery_loop вместо N per-clinic задач
    tasks.append(
        asyncio.create_task(
            discovery_loop(
                api,
                database,
                settings.DISCOVERY_PATIENT_ID_ADULT,
                settings.DISCOVERY_PATIENT_ID_CHILD,
            )
        )
    )
    await safe_set("discovery_tasks_alive", 1)

    tasks.append(asyncio.create_task(healthcheck_loop(bot, api, db)))
    tasks.append(asyncio.create_task(cleanup_loop(bot, db)))

    # Статическая валидация схем API выполняется через scripts/generate_api_schemas.py
    # в процессе разработки. Рантайм-проверка схем (schema_check_loop) отключена
    # в пользу статического подхода — см. Задачу 2.8 ROADMAP.

    logger.info(f"Запущено {len(tasks)} фоновых задач")
    return tasks


async def _start_metrics_server(
    db: DatabaseManager,
) -> tuple[web.AppRunner, web.TCPSite]:
    """Запускает aiohttp-сервер с Prometheus /metrics endpoint."""

    app = web.Application()

    async def metrics_handler(request: web.Request) -> web.Response:
        body, content_type = await prometheus_metrics.generate_response(db)
        return web.Response(body=body, content_type=content_type)

    app.router.add_get("/metrics", metrics_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", settings.METRICS_PORT, reuse_address=True)
    await site.start()
    logger.info(f"Prometheus HTTP-сервер запущен на порту {settings.METRICS_PORT}")
    return runner, site


def _run_uvicorn_sync(app, host: str, port: int) -> bool:
    """Запускает uvicorn в daemon-потоке с SO_REUSEADDR.

    Создаёт pre-bound socket с SO_REUSEADDR и передаёт его в uvicorn
    через параметр ``sockets=[sock]``, т.к. ``Config`` не имеет
    атрибута ``sock`` (uvicorn 0.47.0).
    """
    import uvicorn

    result: dict[str, object] = {"success": False, "exception": None}

    def _serve() -> None:
        try:
            config = uvicorn.Config(app, host=host, port=port, log_level="info")
            server = uvicorn.Server(config)

            # Создаём сокет с SO_REUSEADDR до вызова bind()
            # Решает проблему [Errno 10048] на Windows (TIME_WAIT)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))

            # Передаём pre-bound socket — uvicorn использует его
            # вместо создания собственного (см. Server.startup)
            server.run(sockets=[sock])
        except Exception as e:
            result["exception"] = e
            logger.exception("uvicorn Server.run() завершился с ошибкой")

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()

    time.sleep(1.5)

    if thread.is_alive():
        result["success"] = True
        return True

    exc = result["exception"]
    logger.warning("Дашборд не смог занять порт {}: {}", port, exc)
    return False


async def _check_port_available(host: str, port: int) -> bool:
    """Проверяет, свободен ли порт через socket.bind() — кроссплатформенно.

    На Windows попытка connect() к свободному порту может привести к
    TimeoutError вместо ConnectionRefusedError из-за брандмауэра/антивируса,
    дропающего SYN-пакеты. bind() напрямую опрашивает ОС, занят ли порт,
    и работает идентично на Linux, Windows и macOS.

    Важно: SO_REUSEADDR НЕ используется, чтобы bind() честно сообщал
    о занятости порта (на Windows SO_REUSEADDR позволяет повторный bind
    к уже занятому адресу, маскируя проблему).
    """
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        await loop.run_in_executor(None, sock.bind, (host, port))
        return True  # bind успешен — порт свободен
    except OSError:
        return False  # bind не удался — порт занят
    finally:
        sock.close()


async def _run_dashboard_safe(
    web_app,
    port: int,
    fallback_ports: list[int],
    logger,
) -> int | None:
    """Запускает uvicorn-сервер веб-дашборда с retry и fallback-портами."""
    ports_to_try = [port, *fallback_ports]

    for p in ports_to_try:
        for attempt in range(3):
            # Pre-flight проверка порта (адрес должен совпадать с uvicorn)
            if not await _check_port_available("0.0.0.0", p):
                logger.warning(
                    f"Порт {p} занят (попытка {attempt + 1}/3), жду {2**attempt}с..."
                )
                await asyncio.sleep(2**attempt)
                continue

            logger.info(
                f"Пробую запустить дашборд на порту {p} (попытка {attempt + 1}/3)..."
            )
            success = await asyncio.to_thread(_run_uvicorn_sync, web_app, "0.0.0.0", p)
            if success:
                logger.info(f"Веб-дашборд запущен на http://0.0.0.0:{p}")
                return p

            # uvicorn упал — мог занять порт, повтор через exponential backoff
            logger.warning(
                f"uvicorn на порту {p} упал (попытка {attempt + 1}/3), "
                f"повтор через {2**attempt}с..."
            )
            await asyncio.sleep(2**attempt)

    logger.error("Веб-дашборд не запущен: все порты заняты.")
    return None


async def run_dashboard(
    db: DatabaseManager,
    health_metrics,
    prometheus_metrics,
    config,
    api: ZdravClient,
    host: str,
    port: int,
) -> None:
    """Запускает uvicorn-сервер веб-дашборда как asyncio-задачу."""
    from src.web.app import create_app

    try:
        web_app = create_app(db, health_metrics, prometheus_metrics, config, api)
    except Exception:
        logger.exception("Ошибка при создании FastAPI-приложения веб-дашборда")
        return

    try:
        fallback_ports = [8091, 8092, 8093]
        result = await _run_dashboard_safe(web_app, port, fallback_ports, logger)

        if result is None:
            logger.warning(
                "Веб-дашборд не запущен ни на одном порту из: "
                f"{[port, *fallback_ports]}"
            )
    except Exception:
        logger.exception("Ошибка при запуске uvicorn-сервера веб-дашборда")


async def bootstrap_logging() -> None:
    """Настройка логирования (Loguru), Sentry, интернационализации."""
    setup_logging()
    # Инициализация Sentry после логирования — избегаем дедлока между
    # BreadcrumbHandler Sentry и InterceptHandler loguru на Python 3.14
    error_notifier.init_sentry()
    setup_i18n(settings.BOT_LANGUAGE)


async def bootstrap_redis() -> RedisClient:
    """Инициализация Redis клиента (до FSM-хранилища)."""
    return await RedisClient.get_instance()


async def bootstrap_database() -> tuple[Database, DatabaseManager, ZdravClient]:
    """Инициализация БД, API-клиента, сидирование, загрузка конфигов из БД."""
    # Убедимся, что каталог 'data' существует
    data_dir = os.path.dirname(settings.SQLITE_DB_PATH)
    if data_dir and not await aiofiles.os.path.exists(data_dir):
        await aiofiles.os.makedirs(data_dir)

    # Инициализация SQLite + DatabaseManager
    database = Database(settings.SQLITE_DB_PATH)
    db = DatabaseManager(database)
    await db.load()

    # Инициализация API клиента
    api = ZdravClient()

    # Сидирование из fallback-констант (если таблицы пусты)
    await database.seed_specialty_aliases_from_fallback()
    await database.seed_config_from_defaults()

    # Загрузка конфигов из БД (переопределяет значения из settings)
    try:
        from src.config import load_config_from_db
        from src.utils.helpers import load_specialty_aliases_from_db

        await load_config_from_db(database)
        api.base_url = settings.API_BASE_URL
        await load_specialty_aliases_from_db(database)
        logger.info("Конфиги и псевдонимы специальностей загружены из БД")
    except Exception as e:
        logger.warning(f"Не удалось загрузить данные из БД: {e}")

    # Синхронизация названий клиник из API
    await sync_clinic_names(api, database)

    return database, db, api


async def bootstrap_proxy() -> AiohttpSession | None:
    """Разрешение прокси и создание AiohttpSession (если PROXY_URL настроен).

    Returns:
        AiohttpSession с прокси или None, если прокси не настроен.
    """
    if not settings.PROXY_URL:
        return None

    from urllib.parse import urlparse

    # Валидация формата URL прокси
    parsed = urlparse(settings.PROXY_URL)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(
            f"Неверный формат PROXY_URL: {settings.PROXY_URL}. "
            "Ожидается URL вида http://user:pass@host:port"
        )

    # Разрешение прокси: если хост = "auto" — автоопределение IP
    proxy_url = settings.PROXY_URL
    host, port = _parse_proxy_host_port(proxy_url)
    if host == "auto":
        discovered = await discover_proxy(port)
        if discovered is None:
            raise ConnectionError(
                f"Автоопределение прокси не удалось — "
                f"ни один адрес не ответил на порту {port}"
            )
        proxy_url = discovered

    # Проверка доступности прокси до создания сессии
    await check_proxy_connectivity(proxy_url)

    # Создание AiohttpSession с retry при падении прокси
    last_session_error: Exception | None = None
    for attempt in range(1, _PROXY_RETRIES + 1):
        try:
            session = AiohttpSession(proxy=proxy_url)
            logger.info(f"AiohttpSession с прокси создана (попытка {attempt})")
            return session
        except Exception as e:
            last_session_error = e
            if attempt < _PROXY_RETRIES:
                logger.warning(
                    f"Не удалось создать сессию с прокси "
                    f"(попытка {attempt}/{_PROXY_RETRIES}): {e}"
                )
                await asyncio.sleep(_PROXY_RETRY_DELAY)

    logger.error("Не удалось создать сессию с прокси после всех попыток")
    raise last_session_error  # type: ignore[misc]


async def bootstrap_bot(
    session: AiohttpSession | None,
    redis_client: RedisClient,
) -> tuple[Bot, Dispatcher]:
    """Создание бота, FSM-хранилище, middleware, роутеры, проверка связи.

    Returns:
        (bot, dispatcher) — готовые к запуску поллинга.
    """
    bot = Bot(token=settings.BOT_TOKEN, session=session)

    # FSM-хранилище: Redis если доступен, иначе MemoryStorage (graceful degradation)
    # TTL = 30 минут (1800 секунд) для предотвращения утечки ключей
    _fsm_ttl = 1800
    if redis_client.is_available:
        from aiogram.fsm.storage.redis import RedisStorage

        dp = Dispatcher(
            storage=RedisStorage.from_url(
                settings.REDIS_URL,
                state_ttl=_fsm_ttl,
                data_ttl=_fsm_ttl,
            )
        )
        logger.info(
            "FSM-хранилище: Redis (state_ttl={}s, data_ttl={}s)",
            _fsm_ttl,
            _fsm_ttl,
        )
    else:
        from aiogram.fsm.storage.memory import MemoryStorage

        dp = Dispatcher(storage=MemoryStorage())
        logger.warning(
            "FSM-хранилище: MemoryStorage (Redis недоступен, TTL не поддерживается)"
        )

    # Регистрация middleware (порядок важен: outer выполняется первым)
    dp.update.outer_middleware(ErrorBoundaryMiddleware())
    dp.update.outer_middleware(UserRateLimitMiddleware())
    dp.update.outer_middleware(UserDataPreloadMiddleware())
    dp.update.outer_middleware(ActivityLogMiddleware())

    # Регистрация роутеров
    from src.handlers import common, registration

    dp.include_router(common.router)
    dp.include_router(registration.router)

    # Регистрация роутера Mini App (если включено)
    if settings.MINI_APP_ENABLED:
        from src.handlers import mini_app

        dp.include_router(mini_app.router)

    # Проверка связи с Telegram API до запуска фоновых задач
    await _bot_me_with_retry(bot)

    return bot, dp


async def bootstrap_web(
    db: DatabaseManager,
    api: ZdravClient,
) -> tuple[asyncio.Task | None, web.AppRunner | None]:
    """Запуск веб-дашборда и Prometheus-метрик (если включены в настройках).

    Returns:
        (dashboard_task, metrics_runner) — для последующей остановки.
    """
    # Запуск Prometheus HTTP-сервера
    metrics_runner: web.AppRunner | None = None
    try:
        metrics_runner, _ = await _start_metrics_server(db)
    except OSError as e:
        logger.warning(f"Не удалось запустить сервер метрик: {e}")

    # Запуск веб-дашборда
    dashboard_task: asyncio.Task | None = None
    if settings.WEB_DASHBOARD_ENABLED:
        try:
            dashboard_task = asyncio.create_task(
                run_dashboard(
                    db,
                    health_metrics,
                    prometheus_metrics,
                    settings,
                    api,
                    host="0.0.0.0",
                    port=settings.WEB_DASHBOARD_PORT,
                )
            )
            logger.info("Задача веб-дашборда создана")
        except Exception as e:
            logger.error(f"Не удалось создать задачу веб-дашборда: {e}", exc_info=True)
    else:
        logger.info("Веб-дашборд отключен (WEB_DASHBOARD_ENABLED=False)")

    return dashboard_task, metrics_runner


async def main() -> None:
    """Основная функция запуска бота — оркестрирует все bootstrap-этапы."""
    await bootstrap_logging()

    redis_client = await bootstrap_redis()
    database, db, api = await bootstrap_database()
    session = await bootstrap_proxy()
    bot, dp = await bootstrap_bot(session, redis_client)

    # Запуск фоновых задач (только после проверки связи с Telegram)
    background_tasks = await _start_background_tasks(bot, api, db, database)

    # Запуск веб-инфраструктуры (дашборд + метрики)
    dashboard_task, metrics_runner = await bootstrap_web(db, api)

    logger.info("Бот запущен и готов помогать!")

    try:
        await dp.start_polling(bot, db=db, api=api)
    except asyncio.CancelledError:
        logger.info("Поллинг остановлен (cancelled)")
    except Exception as e:
        logger.exception("Критическая ошибка в поллинге")
        await error_notifier.notify(e, context="polling_crash")
    finally:
        logger.info("Остановка фоновых задач...")
        for task in background_tasks:
            task.cancel()
        await asyncio.gather(*background_tasks, return_exceptions=True)

        # Остановка веб-дашборда
        if dashboard_task is not None:
            dashboard_task.cancel()
            await asyncio.gather(dashboard_task, return_exceptions=True)
            logger.info("Веб-дашборд остановлен")

        # Остановка Prometheus HTTP-сервера
        if metrics_runner is not None:
            await metrics_runner.cleanup()
            logger.info("Prometheus HTTP-сервер остановлен")

        await api.close()

        if bot.session and not getattr(bot.session, "closed", False):
            await bot.session.close()

        # Закрытие Redis
        await RedisClient.shutdown()

        logger.info("Бот остановлен.")


async def _shutdown_notify(error_notifier, exc: Exception, context: str) -> None:
    """Аварийное уведомление с таймаутом, исключающим deadlock при shutdown."""
    with suppress(asyncio.TimeoutError, Exception):
        await asyncio.wait_for(
            error_notifier.notify(exc, context=context),
            timeout=5.0,
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен.")
    except SystemExit:
        logger.info("Бот остановлен.")
    except Exception as e:
        logger.exception("Необработанная ошибка при запуске")
        # Попытка отправить уведомление с таймаутом — без риска deadlock
        try:
            asyncio.run(_shutdown_notify(error_notifier, e, "startup_crash"))
        except Exception:
            logger.debug("Не удалось отправить уведомление об ошибке старта")
        finally:
            os._exit(1)
