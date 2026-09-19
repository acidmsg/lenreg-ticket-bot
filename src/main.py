"""
Точка входа в Telegram-бота lenreg-ticket-bot.

Запускает aiogram-поллинг, фоновые задачи (мониторинг, discovery,
healthcheck, очистка), Prometheus-метрики и веб-дашборд.
"""

from __future__ import annotations

import asyncio
import os
import socket
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING

import aiofiles.os
import uvicorn
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
from src.services.background import (
    BackgroundTaskManager,
    RetryConfig,
    ScheduleConfig,
    publish_active_manager,
)
from src.services.cleanup import _cleanup_iteration
from src.services.dns_watchdog import DnsWatchdogState, dns_watchdog_loop
from src.services.doctor_discovery import (
    _discovery_iteration,
    sync_clinic_names,
)
from src.services.error_notifier import error_notifier
from src.services.healthcheck import _healthcheck_iteration
from src.services.healthcheck import metrics as health_metrics
from src.services.metrics import prometheus_metrics
from src.services.monitor import _monitor_iteration
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

# Константы веб-дашборда (TD-009, этап 2): дашборд живёт в главном event loop'е
_DASHBOARD_PORT_RETRIES = 3
_DASHBOARD_STARTUP_TIMEOUT = 10.0  # ожидание готовности server.started, секунд
_DASHBOARD_STARTUP_POLL_INTERVAL = 0.05  # период опроса server.started, секунд
_DASHBOARD_DRAIN_TIMEOUT = 10.0  # дренаж in-flight HTTP-запросов при остановке, секунд
_DASHBOARD_SOCKET_BACKLOG = 2048  # совпадает с uvicorn.Config.backlog по умолчанию


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
) -> BackgroundTaskManager:
    """Запускает все фоновые задачи через BackgroundTaskManager.

    Вызывается ТОЛЬКО после успешной проверки связи с Telegram API,
    чтобы снизить нагрузку на IOCP в момент старта и избежать конкуренции
    с прокси-соединением.
    """
    manager = BackgroundTaskManager()
    # Публикуем менеджер: дашборд, /status и Prometheus берут статус задач только отсюда
    publish_active_manager(manager)

    # ── Мониторинг слотов ────────────────────────────────────────────
    monitor_state: dict = {
        "initial_sync": True,
        "semaphore": asyncio.Semaphore(10),
        "empty_counts": {},
        "empty_counts_lock": asyncio.Lock(),
    }
    manager.add(
        _monitor_iteration,
        name="monitor",
        schedule=ScheduleConfig(interval=60, jitter=(42, 85)),
        retry=RetryConfig(max_retries=3, backoff_min=2.0, backoff_max=300),
        bot=bot,
        api=api,
        db=db,
        state=monitor_state,
    )

    # ── Discovery врачей ─────────────────────────────────────────────
    manager.add(
        _discovery_iteration,
        name="discovery",
        schedule=ScheduleConfig(interval=settings.DISCOVERY_INTERVAL),
        retry=RetryConfig(max_retries=3),
        api=api,
        database=database,
        patient_id_adult=settings.DISCOVERY_PATIENT_ID_ADULT,
        patient_id_child=settings.DISCOVERY_PATIENT_ID_CHILD,
    )

    # ── Healthcheck ──────────────────────────────────────────────────
    manager.add(
        _healthcheck_iteration,
        name="healthcheck",
        schedule=ScheduleConfig(interval=settings.CHECK_INTERVAL),
        retry=RetryConfig(max_retries=3, backoff_min=10.0),
        bot=bot,
        api=api,
        db=db,
        health_metrics=health_metrics,
    )

    # ── Очистка сообщений ────────────────────────────────────────────
    manager.add(
        _cleanup_iteration,
        name="cleanup",
        schedule=ScheduleConfig(interval=settings.CLEANUP_INTERVAL),
        retry=RetryConfig(max_retries=3),
        bot=bot,
        db=db,
    )

    # ── Детектор расхождения DNS (пиннинг IP API) ─────────────────────
    # Пиннинг имени через /etc/hosts (extra_hosts в docker-compose.yml) —
    # основной путь разрешения имени; задача проверяет, не разошёлся ли пин
    # с реальным DNS (минуя /etc/hosts), и уведомляет администраторов.
    # Инфраструктуру детектор не изменяет.
    manager.add(
        dns_watchdog_loop,
        name="dns_watchdog",
        schedule=ScheduleConfig(interval=settings.dns_watchdog_interval_sec),
        retry=RetryConfig(max_retries=3),
        state=DnsWatchdogState(),
    )

    # Статическая валидация схем API выполняется через scripts/generate_api_schemas.py
    # в процессе разработки. Рантайм-проверка схем (schema_check_loop) отключена
    # в пользу статического подхода — см. Задачу 2.8 ROADMAP.

    await manager.start_all()
    logger.info(
        f"Запущено {len(manager.status())} фоновых задач через BackgroundTaskManager"
    )
    return manager


async def _start_metrics_server(
    db: DatabaseManager,
    *,
    host: str = "0.0.0.0",
    port: int | None = None,
) -> tuple[web.AppRunner, web.TCPSite]:
    """Запускает aiohttp-сервер с Prometheus /metrics endpoint.

    Args:
        db: менеджер БД для генерации метрик.
        host: адрес прослушивания; тесты передают loopback.
        port: порт прослушивания; ``None`` — значение из настроек,
            ``0`` — эфемерный порт (тесты).
    """

    app = web.Application()

    async def metrics_handler(request: web.Request) -> web.Response:
        body, content_type = await prometheus_metrics.generate_response(db)
        # charset — отдельный аргумент: aiohttp запрещает charset внутри
        # content_type (ValueError: charset must not be in content_type argument).
        return web.Response(body=body, content_type=content_type, charset="utf-8")

    app.router.add_get("/metrics", metrics_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    metrics_port = settings.METRICS_PORT if port is None else port
    site = web.TCPSite(runner, host, metrics_port, reuse_address=True)
    await site.start()
    logger.info(f"Prometheus HTTP-сервер запущен на порту {metrics_port}")
    return runner, site


def _bind_socket(host: str, port: int, *, reuse_address: bool) -> socket.socket:
    """Базовый хелпер: создаёт сокет и привязывает его к адресу.

    При ``reuse_address=True`` включается ``SO_REUSEADDR`` — это снимает проблему
    ``[Errno 10048]`` на Windows (адрес в состоянии TIME_WAIT). При
    ``reuse_address=False`` bind честно сообщает о занятости порта (на Windows
    ``SO_REUSEADDR`` позволяет повторный bind к занятому адресу, маскируя проблему).

    Raises:
        OSError: сокет не удалось создать или привязать. Дескриптор закрывается
            перед пробросом исключения, утечки не остаётся.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if reuse_address:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
    except OSError:
        sock.close()
        raise
    return sock


def _create_dashboard_socket(host: str, port: int) -> socket.socket:
    """Фабрика: bound+listening сокет для uvicorn с ``SO_REUSEADDR``.

    Сокет занимается до старта uvicorn и передаётся в ``Server.serve(sockets=[sock])``
    (``uvicorn.Config`` не имеет атрибута ``sock``). Это исключает гонку за порт и
    позволяет освободить его при неудачном старте сервера.

    Raises:
        OSError: порт занят или сокет не удалось перевести в режим listening.
    """
    sock = _bind_socket(host, port, reuse_address=True)
    try:
        sock.listen(_DASHBOARD_SOCKET_BACKLOG)
    except OSError:
        sock.close()
        raise
    return sock


class _DashboardServer(uvicorn.Server):
    """uvicorn-сервер дашборда без перехвата сигналов процесса.

    uvicorn 0.47.0 (проверено установленной версией; диапазон проекта
    ``uvicorn>=0.34,<1.0``) в ``Server.serve()`` выполняет
    ``with self.capture_signals():`` — метод является ``@contextlib.contextmanager``.
    В главном потоке ``capture_signals()`` подменяет обработчики SIGINT/SIGTERM на
    ``self.handle_exit``. После перехода дашборда в главный event loop (TD-009,
    этап 2) это лишило бы ``asyncio.run(main())`` штатного Ctrl+C, поэтому перехват
    отключён: остановкой управляет ``main()`` через ``server.should_exit``.
    """

    @contextmanager
    def capture_signals(self) -> Iterator[None]:
        """No-op замена ``uvicorn.Server.capture_signals``."""
        yield


def _log_dashboard_task_result(task: asyncio.Task) -> None:
    """Логирует падение задачи веб-дашборда, изолируя его от поллинга.

    Callback навешивается при создании задачи: исключение веб-слоя не должно
    пробрасываться в aiogram-поллинг, но обязано попасть в логи.
    """
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        logger.opt(exception=error).error("Задача веб-дашборда завершилась с ошибкой")


async def _wait_dashboard_started(
    server: uvicorn.Server, dashboard_task: asyncio.Task
) -> None:
    """Ожидает готовности uvicorn-сервера по флагу ``server.started``.

    Заменяет ``time.sleep(1.5)`` и проверку ``thread.is_alive()`` из прежней потоковой
    реализации: опрос идёт в том же event loop'е и не блокирует поллинг.

    Raises:
        RuntimeError: задача сервера завершилась, так и не выставив ``started``.
    """
    while not server.started:
        if dashboard_task.done():
            raise RuntimeError("uvicorn-сервер завершился до готовности")
        await asyncio.sleep(_DASHBOARD_STARTUP_POLL_INTERVAL)


async def _stop_dashboard_server(
    server: uvicorn.Server,
    dashboard_task: asyncio.Task,
    drain_timeout: float,
) -> None:
    """Останавливает uvicorn-задачу: ``should_exit`` + дренаж, при таймауте — отмена.

    Дренаж завершает in-flight HTTP-запросы до закрытия ``api`` и БД.
    """
    server.should_exit = True
    try:
        await asyncio.wait_for(dashboard_task, timeout=drain_timeout)
    except TimeoutError:
        logger.warning(
            f"Дренаж веб-дашборда не завершился за {drain_timeout}с — отменяю задачу"
        )
        dashboard_task.cancel()
        await asyncio.gather(dashboard_task, return_exceptions=True)
    except Exception:
        logger.exception("Задача веб-дашборда завершилась с ошибкой")


async def _start_dashboard_on_port(
    web_app,
    port: int,
    logger,
    host: str = "0.0.0.0",
) -> tuple[uvicorn.Server, asyncio.Task] | None:
    """Запускает uvicorn на конкретном порту в текущем event loop'е.

    Args:
        web_app: ASGI-приложение дашборда.
        port: порт прослушивания; ``0`` — эфемерный порт (тесты).
        logger: логгер вызывающего модуля.
        host: адрес прослушивания; тесты передают loopback.

    Returns:
        (server, task) при успешном старте; ``None`` — если порт занять не удалось
        либо сервер не стал готов за ``_DASHBOARD_STARTUP_TIMEOUT``.
    """
    try:
        sock = _create_dashboard_socket(host, port)
    except OSError as exc:
        logger.warning(f"Не удалось занять порт {port}: {exc}")
        return None

    config = uvicorn.Config(web_app, host=host, port=port, log_level="info")
    server = _DashboardServer(config)
    dashboard_task = asyncio.create_task(server.serve(sockets=[sock]), name="dashboard")
    dashboard_task.add_done_callback(_log_dashboard_task_result)

    try:
        await asyncio.wait_for(
            _wait_dashboard_started(server, dashboard_task),
            timeout=_DASHBOARD_STARTUP_TIMEOUT,
        )
    except Exception as exc:
        logger.warning(f"Дашборд не запустился на порту {port}: {exc}")
        await _stop_dashboard_server(server, dashboard_task, _DASHBOARD_DRAIN_TIMEOUT)
        sock.close()  # освобождаем порт, если uvicorn не успел забрать сокет
        return None

    logger.info(f"Веб-дашборд запущен на http://{host}:{port}")
    return server, dashboard_task


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

    def _probe() -> bool:
        """Пробный bind в executor'е: True — порт свободен."""
        try:
            probe = _bind_socket(host, port, reuse_address=False)
        except OSError:
            return False
        probe.close()
        return True

    return await loop.run_in_executor(None, _probe)


async def _run_dashboard_safe(
    web_app,
    port: int,
    fallback_ports: list[int],
    logger,
) -> tuple[uvicorn.Server, asyncio.Task] | None:
    """Запускает uvicorn-сервер веб-дашборда с retry и fallback-портами.

    Returns:
        (server, task) — сервер и его задача в главном event loop'е, либо ``None``,
        если ни один порт из цепочки занять не удалось.
    """
    ports_to_try = [port, *fallback_ports]

    for p in ports_to_try:
        for attempt in range(_DASHBOARD_PORT_RETRIES):
            # Pre-flight проверка порта (адрес должен совпадать с uvicorn)
            if not await _check_port_available("0.0.0.0", p):
                logger.warning(
                    f"Порт {p} занят (попытка {attempt + 1}/"
                    f"{_DASHBOARD_PORT_RETRIES}), жду {2**attempt}с..."
                )
                await asyncio.sleep(2**attempt)
                continue

            logger.info(
                f"Пробую запустить дашборд на порту {p} "
                f"(попытка {attempt + 1}/{_DASHBOARD_PORT_RETRIES})..."
            )
            dashboard = await _start_dashboard_on_port(web_app, p, logger)
            if dashboard is not None:
                return dashboard

            # uvicorn упал — мог занять порт, повтор через exponential backoff
            logger.warning(
                f"uvicorn на порту {p} упал "
                f"(попытка {attempt + 1}/{_DASHBOARD_PORT_RETRIES}), "
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
) -> tuple[uvicorn.Server, asyncio.Task] | None:
    """Запускает uvicorn-сервер веб-дашборда в главном event loop'е.

    Сервер создаётся как ``asyncio.Task`` (``Server.serve()``) и остаётся в том же
    loop'е, что и aiogram-поллинг, фоновые задачи и Prometheus-сервер (TD-009, этап 2).

    Returns:
        (server, task) для управления остановкой, либо ``None`` при неудаче.
    """
    from src.web.app import create_app

    try:
        web_app = create_app(db, health_metrics, prometheus_metrics, config, api)
    except Exception:
        logger.exception("Ошибка при создании FastAPI-приложения веб-дашборда")
        return None

    try:
        fallback_ports = [8091, 8092, 8093]
        result = await _run_dashboard_safe(web_app, port, fallback_ports, logger)

        if result is None:
            logger.warning(
                "Веб-дашборд не запущен ни на одном порту из: "
                f"{[port, *fallback_ports]}"
            )
        return result
    except Exception:
        logger.exception("Ошибка при запуске uvicorn-сервера веб-дашборда")
        return None


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

    # Сидирование клиник и врачей из JSON (если таблица clinics пуста)
    await database.seed_clinics_and_doctors_from_file()

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

    # Регистрация роутеров.
    # filter_setup — первым: его state-scoped хендлеры ввода фильтра должны иметь
    # приоритет над общими текстовыми хендлерами остальных роутеров (T-21, §9.9).
    from src.handlers import common, filter_setup, registration

    dp.include_router(filter_setup.router)
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
) -> tuple[uvicorn.Server | None, asyncio.Task | None, web.AppRunner | None]:
    """Запуск веб-дашборда и Prometheus-метрик (если включены в настройках).

    Returns:
        (dashboard_server, dashboard_task, metrics_runner) — для последующей
        остановки. Первые два элемента равны ``None``, если дашборд отключён
        или не поднялся ни на одном порту.
    """
    # Запуск Prometheus HTTP-сервера
    metrics_runner: web.AppRunner | None = None
    try:
        metrics_runner, _ = await _start_metrics_server(db)
    except OSError as e:
        logger.warning(f"Не удалось запустить сервер метрик: {e}")

    # Запуск веб-дашборда
    if not settings.WEB_DASHBOARD_ENABLED:
        logger.info("Веб-дашборд отключен (WEB_DASHBOARD_ENABLED=False)")
        return None, None, metrics_runner

    dashboard = await run_dashboard(
        db,
        health_metrics,
        prometheus_metrics,
        settings,
        api,
        host="0.0.0.0",
        port=settings.WEB_DASHBOARD_PORT,
    )
    if dashboard is None:
        return None, None, metrics_runner

    dashboard_server, dashboard_task = dashboard
    return dashboard_server, dashboard_task, metrics_runner


async def shutdown_services(
    *,
    dashboard_server: uvicorn.Server | None,
    dashboard_task: asyncio.Task | None,
    manager: BackgroundTaskManager,
    metrics_runner: web.AppRunner | None,
    api: ZdravClient,
    bot: Bot | None,
    db: DatabaseManager,
) -> None:
    """Штатная остановка всех ресурсов процесса — тело ``finally`` в ``main()``.

    Вынесено в отдельную корутину ради тестируемости: порядок остановки
    проверяется регресс-тестами без запуска Telegram-поллинга. Наблюдаемое
    поведение и сообщения логов при этом не меняются.

    Порядок строго детерминирован:

    1. веб-дашборд (дренаж in-flight HTTP-запросов);
    2. фоновые задачи;
    3. aiohttp-сервер метрик;
    4. API-клиент и сессия бота;
    5. соединение с БД;
    6. Redis.

    Args:
        dashboard_server: uvicorn-сервер дашборда; ``None`` — дашборд отключён.
        dashboard_task: задача ``Server.serve()``; ``None`` — дашборд отключён.
        manager: реестр фоновых задач.
        metrics_runner: aiohttp-сервер метрик; ``None`` — не запущен.
        api: клиент zdrav API.
        bot: бот aiogram; ``None`` — сессия отсутствует (например, в тестах).
        db: менеджер БД — закрывается последним среди потребителей данных.
    """
    # Дашборд останавливается первым: in-flight веб-запросы должны завершиться
    # до закрытия api и БД, иначе они обратятся к уже закрытым ресурсам.
    if dashboard_server is not None and dashboard_task is not None:
        logger.info("Остановка веб-дашборда...")
        await _stop_dashboard_server(
            dashboard_server, dashboard_task, _DASHBOARD_DRAIN_TIMEOUT
        )
        logger.info("Веб-дашборд остановлен")

    logger.info("Остановка фоновых задач...")
    await manager.stop_all(shutdown_timeout=30.0)
    publish_active_manager(None)

    # Остановка Prometheus HTTP-сервера
    if metrics_runner is not None:
        await metrics_runner.cleanup()
        logger.info("Prometheus HTTP-сервер остановлен")

    await api.close()

    if bot is not None and bot.session and not getattr(bot.session, "closed", False):
        await bot.session.close()

    # Закрытие БД — после остановки всех потребителей: дашборд и фоновые задачи
    # к этому моменту не работают, поэтому к закрытому соединению никто не обратится.
    # Вызов обязателен: aiosqlite удерживает non-daemon воркер-поток до close(),
    # без него процесс не завершается на выходе из ``asyncio.run(main())``.
    await db.close()
    logger.info("Соединение с БД закрыто")

    # Закрытие Redis
    await RedisClient.shutdown()


async def main() -> None:
    """Основная функция запуска бота — оркестрирует все bootstrap-этапы."""
    await bootstrap_logging()

    redis_client = await bootstrap_redis()
    database, db, api = await bootstrap_database()
    session = await bootstrap_proxy()
    bot, dp = await bootstrap_bot(session, redis_client)

    # Запуск фоновых задач (только после проверки связи с Telegram)
    manager = await _start_background_tasks(bot, api, db, database)

    # Запуск веб-инфраструктуры (дашборд + метрики)
    dashboard_server, dashboard_task, metrics_runner = await bootstrap_web(db, api)

    logger.info("Бот запущен и готов помогать!")

    try:
        await dp.start_polling(bot, db=db, api=api)
    except asyncio.CancelledError:
        logger.info("Поллинг остановлен (cancelled)")
    except Exception as e:
        logger.exception("Критическая ошибка в поллинге")
        await error_notifier.notify(e, context="polling_crash")
    finally:
        await shutdown_services(
            dashboard_server=dashboard_server,
            dashboard_task=dashboard_task,
            manager=manager,
            metrics_runner=metrics_runner,
            api=api,
            bot=bot,
            db=db,
        )

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
