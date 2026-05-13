import asyncio
import os
import re
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger

from src.api.zdrav_client import ZdravClient
from src.config import settings
from src.database.database import Database
from src.database.doctor_manager import DoctorManager
from src.database.manager import DatabaseManager
from src.handlers import common, registration
from src.middleware.ratelimit import UserRateLimitMiddleware
from src.services.cleanup import cleanup_loop
from src.services.doctor_discovery import discovery_loop, sync_clinic_names
from src.services.error_notifier import error_notifier
from src.services.healthcheck import _safe_set, healthcheck_loop, metrics
from src.services.monitor import monitor_loop
from src.utils.logging import setup_logging

# Константы retry-логики для прокси и Telegram API
_PROXY_RETRIES = 3
_PROXY_RETRY_DELAY = 2.0  # секунд
_TG_RETRIES = 3
_TG_RETRY_DELAY = 3.0  # секунд
_PROXY_CHECK_TIMEOUT = 5.0  # секунд


def _parse_proxy_host_port(proxy_url: str) -> tuple[str, int]:
    """Извлекает host:port из socks5://host:port строки."""
    # Убираем схему (socks5://, socks4://, http://)
    stripped = re.sub(r"^[a-z0-9]+://", "", proxy_url)
    host, _, port_str = stripped.partition(":")
    return host, int(port_str) if port_str else 1080


async def _check_proxy_connectivity(proxy_url: str) -> None:
    """
    Предварительная проверка TCP-соединения с прокси-сервером.

    Быстрый healthcheck, чтобы дать понятную ошибку до того, как начнём
    создавать сессию и запускать фоновые задачи.
    """
    host, port = _parse_proxy_host_port(proxy_url)
    logger.info(f"Проверка соединения с прокси {host}:{port}...")
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=_PROXY_CHECK_TIMEOUT,
        )
        writer.close()
        await writer.wait_closed()
        logger.info(f"Прокси {host}:{port} доступен")
    except asyncio.TimeoutError:
        msg = f"Таймаут соединения с прокси {host}:{port} ({_PROXY_CHECK_TIMEOUT}с)"
        logger.error(msg)
        raise ConnectionError(msg)
    except OSError as e:
        msg = f"Прокси {host}:{port} недоступен: {e}"
        logger.error(msg)
        raise ConnectionError(msg)


async def _bot_me_with_retry(
    bot: Bot, max_retries: int = _TG_RETRIES, delay: float = _TG_RETRY_DELAY
) -> None:
    """
    Проверяет связь с Telegram API через bot.me() с повторными попытками.

    Если прокси временно недоступен, даёт ему шанс восстановиться между попытками.
    """
    last_error: Optional[Exception] = None
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
    """
    tasks: list[asyncio.Task[object]] = []

    tasks.append(asyncio.create_task(monitor_loop(bot, api, db)))

    doc_manager = DoctorManager(database)
    await doc_manager.load()

    clinic_ids = await database.get_active_clinic_ids()
    if not clinic_ids:
        logger.warning("Таблица clinics пуста, фоновый discovery не запущен")
    else:
        for clinic_id in clinic_ids:
            task = asyncio.create_task(
                discovery_loop(
                    api,
                    doc_manager,
                    str(clinic_id),
                    settings.DISCOVERY_PATIENT_ID_ADULT,
                    settings.DISCOVERY_PATIENT_ID_CHILD,
                )
            )
            tasks.append(task)
            await _safe_set("discovery_tasks_alive", metrics.discovery_tasks_alive + 1)

    tasks.append(asyncio.create_task(healthcheck_loop(bot, api, db)))
    tasks.append(asyncio.create_task(cleanup_loop(bot, db)))

    logger.info(f"Запущено {len(tasks)} фоновых задач")
    return tasks


async def main():
    # Настройка логирования (Loguru)
    setup_logging()

    # Убедимся, что каталог 'data' существует
    data_dir = os.path.dirname(settings.SQLITE_DB_PATH)
    if data_dir and not os.path.exists(data_dir):  # noqa: ASYNC240
        os.makedirs(data_dir)  # noqa: ASYNC240

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

    # Синхронизация названий клиник из API (обновляет только имя)
    await sync_clinic_names(api, database)

    # Загрузка конфигов из БД (переопределяет значения из settings)
    try:
        from src.config import load_config_from_db
        from src.utils.helpers import load_specialty_aliases_from_db

        await load_config_from_db(database)
        await load_specialty_aliases_from_db(database)
        logger.info("Конфиги и псевдонимы специальностей загружены из БД")
    except Exception as e:
        logger.warning(f"Не удалось загрузить данные из БД: {e}")

    # === Инициализация бота с прокси (если настроен) ===
    session = None
    if settings.PROXY_URL:
        # Проверка доступности прокси до создания сессии
        await _check_proxy_connectivity(settings.PROXY_URL)

        # Создание AiohttpSession с retry при падении прокси
        last_session_error: Optional[Exception] = None
        for attempt in range(1, _PROXY_RETRIES + 1):
            try:
                session = AiohttpSession(proxy=settings.PROXY_URL)
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
    dp = Dispatcher(storage=MemoryStorage())

    # Регистрация middleware (порядок важен: outer выполняется первым)
    dp.update.outer_middleware(UserRateLimitMiddleware())

    # Регистрация роутеров
    dp.include_router(common.router)
    dp.include_router(registration.router)

    # Проверка связи с Telegram API до запуска фоновых задач
    # (снижает нагрузку на IOCP и даёт понятную ошибку при недоступности прокси)
    await _bot_me_with_retry(bot)

    # Запуск фоновых задач только после подтверждения связи с Telegram
    background_tasks = await _start_background_tasks(bot, api, db, database)

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

        await api.close()

        if bot.session:
            await bot.session.close()
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
            pass
