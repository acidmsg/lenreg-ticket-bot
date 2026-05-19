import asyncio
import os
import threading
import time

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.redis import RedisStorage
from aiohttp import web
from loguru import logger

from src.api.zdrav_client import ZdravClient
from src.config import settings
from src.database.database import Database
from src.database.manager import DatabaseManager
from src.handlers import common, registration
from src.i18n import setup_i18n
from src.middleware.activity import ActivityLogMiddleware
from src.middleware.error_boundary import ErrorBoundaryMiddleware
from src.middleware.ratelimit import UserRateLimitMiddleware
from src.middleware.userdata import UserDataPreloadMiddleware
from src.services.cleanup import cleanup_loop
from src.services.doctor_discovery import discovery_loop, sync_clinic_names
from src.services.error_notifier import error_notifier
from src.services.healthcheck import (
    _safe_set,
    healthcheck_loop,
)
from src.services.healthcheck import (
    metrics as health_metrics,
)
from src.services.metrics import prometheus_metrics
from src.services.monitor import monitor_loop
from src.services.schema_watcher import schema_check_loop
from src.utils.logging import setup_logging
from src.utils.proxy_discovery import (
    check_proxy_connectivity,
    discover_proxy,
)
from src.utils.redis import RedisClient

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
    raise last_error  # type: ignore[misc]


async def _start_background_tasks(
    bot: Bot, api: ZdravClient, db: DatabaseManager, database: Database
) -> list[asyncio.Task[object]]:
    """
    Запускает все фоновые задачи (monitor, discovery, healthcheck, cleanup).

    Вызывается ТОЛЬКО после успешной проверки связи с Telegram API,
    чтобы снизить нагрузку на IOCP в момент старта и избежать конкуренции
    с прокси-соединением.

    Discovery теперь запускается как один агрегированный цикл, который сам
    итерирует активные clinic_ids из БД (вместо N per-clinic задач).
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
    await _safe_set("discovery_tasks_alive", 1)

    tasks.append(asyncio.create_task(healthcheck_loop(bot, api, db)))
    tasks.append(asyncio.create_task(cleanup_loop(bot, db)))

    # API Schema Change Detection (F8)
    if settings.SCHEMA_CHECK_ENABLED:
        tasks.append(
            asyncio.create_task(
                schema_check_loop(
                    api,
                    error_notifier,
                    prometheus_metrics,
                    interval=settings.SCHEMA_CHECK_INTERVAL,
                )
            )
        )
        logger.info(
            "Запущена проверка схем API (интервал: {}с)",
            settings.SCHEMA_CHECK_INTERVAL,
        )
    else:
        logger.info("Проверка схем API отключена (SCHEMA_CHECK_ENABLED=False)")

    logger.info(f"Запущено {len(tasks)} фоновых задач")
    return tasks


async def _start_metrics_server(
    db: DatabaseManager,
) -> tuple[web.AppRunner, web.TCPSite]:
    """
    Запускает aiohttp-сервер с Prometheus /metrics endpoint.

    Возвращает (runner, site) для корректной остановки в finally.
    """
    app = web.Application()

    async def metrics_handler(request: web.Request) -> web.Response:
        body, content_type = await prometheus_metrics.generate_response(db)
        return web.Response(body=body, content_type=content_type)

    app.router.add_get("/metrics", metrics_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", settings.METRICS_PORT)
    await site.start()
    logger.info(f"Prometheus HTTP-сервер запущен на порту {settings.METRICS_PORT}")
    return runner, site


def _run_uvicorn_sync(app, host: str, port: int) -> bool:
    """
    Запускает uvicorn в daemon-потоке. Возвращает True, если сервер成功но запущен.

    Внутри потока все исключения перехватываются, чтобы предотвратить
    завершение основного процесса при ошибке привязки порта (например,
    [WinError 10013] на Windows).
    """
    result: dict[str, object] = {"success": False, "exception": None}

    def _serve() -> None:
        try:
            config = uvicorn.Config(app, host=host, port=port, log_level="info")
            server = uvicorn.Server(config)
            server.run()  # синхронный run(), блокирует поток навсегда при успехе
        except Exception as e:
            result["exception"] = e
            logger.exception("uvicorn Server.run() завершился с ошибкой")

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()

    # Ждём 1.5 секунды — если поток жив, значит bind прошёл успешно
    time.sleep(1.5)

    if thread.is_alive():
        result["success"] = True
        return True

    # Поток умер — bind не удался
    exc = result["exception"]
    logger.warning("Дашборд не смог занять порт {}: {}", port, exc)
    return False


async def _run_dashboard_safe(
    web_app,
    port: int,
    fallback_ports: list[int],
    logger,
) -> int | None:
    """
    Запускает uvicorn-сервер веб-дашборда с перебором портов при ошибке привязки.

    Uvicorn запускается через asyncio.to_thread в отдельном потоке (daemon),
    чтобы не вмешиваться в основной event loop aiogram (критично для Windows/IOCP).

    Все исключения внутри потока перехватываются — процесс не падает.
    """
    ports_to_try = [port, *fallback_ports]

    for p in ports_to_try:
        logger.info("Пробую запустить дашборд на порту {}...", p)
        success = await asyncio.to_thread(_run_uvicorn_sync, web_app, "0.0.0.0", p)
        if success:
            logger.info("Веб-дашборд запущен на порту {}", p)
            return p

    logger.warning("Веб-дашборд не запущен: все порты заняты.")
    return None


async def run_dashboard(
    db: DatabaseManager,
    health_metrics,
    prometheus_metrics,
    config,
    host: str = "0.0.0.0",
    port: int = 8080,
):
    """
    Запускает uvicorn-сервер веб-дашборда как asyncio-задачу (автоподбор порта).

    Uvicorn работает в отдельном daemon-потоке, поэтому run_dashboard()
    возвращает управление сразу после успешного запуска сервера.
    """
    from src.web.app import create_app

    web_app = create_app(db, health_metrics, prometheus_metrics, config)

    fallback_ports = [8091, 8092, 8093]
    result = await _run_dashboard_safe(web_app, port, fallback_ports, logger)

    if result is None:
        logger.warning(
            f"Веб-дашборд не запущен ни на одном порту из: {[port, *fallback_ports]}"
        )


async def main():
    # Настройка логирования (Loguru)
    setup_logging()

    # Инициализация интернационализации (i18n)
    setup_i18n(settings.BOT_LANGUAGE)

    # Убедимся, что каталог 'data' существует
    data_dir = os.path.dirname(settings.SQLITE_DB_PATH)
    if data_dir and not os.path.exists(data_dir):  # noqa: ASYNC240
        os.makedirs(data_dir)

    # Инициализация Redis (до FSM-хранилища)
    # Не падает при недоступности Redis: переходит в режим graceful degradation
    redis_client = await RedisClient.get_instance()

    # Инициализация SQLite
    database = Database(settings.SQLITE_DB_PATH)
    db = DatabaseManager(database)
    await db.load()

    # Инициализация API клиента
    api = ZdravClient()

    # Сидирование псевдонимов специальностей из fallback (если таблица пуста)
    await database.seed_specialty_aliases_from_fallback()

    # Сидирование конфигов из defaults settings (если таблица config пуста)
    await database.seed_config_from_defaults()

    # Загрузка конфигов из БД (переопределяет значения из settings).
    # Выполняется ДО sync_clinic_names, чтобы переопределённый в БД API_BASE_URL
    # применился до первого обращения к API.
    try:
        from src.config import load_config_from_db
        from src.utils.helpers import load_specialty_aliases_from_db

        await load_config_from_db(database)
        # Обновляем base_url у API-клиента после загрузки из БД
        api.base_url = settings.API_BASE_URL
        await load_specialty_aliases_from_db(database)
        logger.info("Конфиги и псевдонимы специальностей загружены из БД")
    except Exception as e:
        logger.warning(f"Не удалось загрузить данные из БД: {e}")

    # Синхронизация названий клиник из API (обновляет только имя)
    await sync_clinic_names(api, database)

    # --- Инициализация бота с прокси (если настроен) ---
    session = None
    if settings.PROXY_URL:
        from urllib.parse import urlparse

        # Валидация формата URL прокси
        parsed = urlparse(settings.PROXY_URL)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(
                f"Неверный формат PROXY_URL: {settings.PROXY_URL}. "
                "Ожидается URL вида http://user:pass@host:port"
            )

        from src.utils.proxy_discovery import _parse_proxy_host_port

        # Разрешение прокси: если хост = "auto" — автоопределение IP
        proxy_url = settings.PROXY_URL
        host, port = _parse_proxy_host_port(proxy_url)
        if host == "auto":
            discovered = await discover_proxy(port)
            if discovered is None:
                raise ConnectionError(
                    "Автоопределение прокси не удалось — "
                    "ни один адрес не ответил на порту "
                    f"{port}"
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
                last_session_error = None
                break
            except Exception as e:
                last_session_error = e
                if attempt < _PROXY_RETRIES:
                    logger.warning(
                        f"Не удалось создать сессию с прокси "
                        f"(попытка {attempt}/{_PROXY_RETRIES}): {e}"
                    )
                    await asyncio.sleep(_PROXY_RETRY_DELAY)

        if last_session_error is not None:
            logger.error("Не удалось создать сессию с прокси после всех попыток")
            raise last_session_error

    bot = Bot(token=settings.BOT_TOKEN, session=session)

    # FSM-хранилище: Redis если доступен, иначе MemoryStorage (graceful degradation)
    if redis_client.is_available:
        dp = Dispatcher(storage=RedisStorage.from_url(settings.REDIS_URL))
        logger.info("FSM-хранилище: Redis")
    else:
        from aiogram.fsm.storage.memory import MemoryStorage

        dp = Dispatcher(storage=MemoryStorage())
        logger.warning("FSM-хранилище: MemoryStorage (Redis недоступен)")

    # Регистрация middleware (порядок важен: outer выполняется первым)
    # 1. Error boundary — самая внешняя, ловит все исключения
    dp.update.outer_middleware(ErrorBoundaryMiddleware())
    # 2. Rate limiter — отсекает спам до всей остальной обработки
    dp.update.outer_middleware(UserRateLimitMiddleware())
    # 3. User data preload — загружает user_data один раз для всех handler'ов
    dp.update.outer_middleware(UserDataPreloadMiddleware())
    # 4. Activity log — логирует каждое событие (DEBUG)
    dp.update.outer_middleware(ActivityLogMiddleware())

    # Регистрация роутеров
    dp.include_router(common.router)
    dp.include_router(registration.router)

    # Проверка связи с Telegram API до запуска фоновых задач
    # (снижает нагрузку на IOCP и даёт понятную ошибку при недоступности прокси)
    await _bot_me_with_retry(bot)

    # Запуск фоновых задач только после подтверждения связи с Telegram
    background_tasks = await _start_background_tasks(bot, api, db, database)

    # Запуск Prometheus HTTP-сервера
    metrics_runner, _metrics_site = await _start_metrics_server(db)

    # Запуск веб-дашборда (F5)
    dashboard_task: asyncio.Task | None = None
    if settings.WEB_DASHBOARD_ENABLED:
        dashboard_task = asyncio.create_task(
            run_dashboard(
                db,
                health_metrics,
                prometheus_metrics,
                settings,
                port=settings.WEB_DASHBOARD_PORT,
            )
        )
        # Логирование результата — внутри run_dashboard / _run_dashboard_safe
    else:
        logger.info("Веб-дашборд отключен (WEB_DASHBOARD_ENABLED=False)")

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
        await metrics_runner.cleanup()
        logger.info("Prometheus HTTP-сервер остановлен")

        await api.close()

        if bot.session and not getattr(bot.session, "closed", False):
            await bot.session.close()

        # Закрытие Redis
        await RedisClient.shutdown()

        logger.info("Бот остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен.")
    except SystemExit:
        logger.info("Бот остановлен.")
    except Exception as e:
        logger.exception("Необработанная ошибка при запуске")
        # Попытка отправить уведомление (может не сработать на старте)
        try:
            asyncio.run(error_notifier.notify(e, context="startup_crash"))
        except Exception:
            logger.debug("Не удалось отправить уведомление об ошибке старта")
