import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage

from api.zdrav_client import ZdravClient
from config import settings
from database.database import Database
from database.doctor_manager import DoctorManager
from database.manager import DatabaseManager
from handlers import common, registration
from middleware.ratelimit import UserRateLimitMiddleware
from services.cleanup import cleanup_loop
from services.doctor_discovery import discovery_loop, sync_clinic_names
from services.error_notifier import error_notifier
from services.healthcheck import _safe_set, healthcheck_loop, metrics
from services.monitor import monitor_loop


async def main():
    # Настройка логирования
    if not os.path.exists("logs"):
        os.makedirs("logs")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler("logs/error.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logger = logging.getLogger(__name__)

    # Убедимся, что каталог 'data' существует
    data_dir = os.path.dirname(settings.SQLITE_DB_PATH)
    if data_dir and not os.path.exists(data_dir):
        os.makedirs(data_dir)

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
        from config import load_config_from_db
        from utils.helpers import load_specialty_aliases_from_db

        await load_config_from_db(database)
        await load_specialty_aliases_from_db(database)
        logger.info("Конфиги и псевдонимы специальностей загружены из БД")
    except Exception as e:
        logger.warning(f"Не удалось загрузить данные из БД: {e}")

    # Инициализация бота и диспетчера
    session = None
    if settings.PROXY_URL:
        session = AiohttpSession(proxy=settings.PROXY_URL)

    bot = Bot(token=settings.BOT_TOKEN, session=session)
    dp = Dispatcher(storage=MemoryStorage())

    # Регистрация middleware (порядок важен: outer выполняется первым)
    # 1. Per-user rate limiter (внешний слой — отсекает до обработчиков)
    dp.update.outer_middleware(UserRateLimitMiddleware())

    # Регистрация роутеров
    dp.include_router(common.router)
    dp.include_router(registration.router)

    # Список фоновых задач для graceful shutdown
    background_tasks = []

    # Запуск фонового мониторинга
    background_tasks.append(asyncio.create_task(monitor_loop(bot, api, db)))

    # Запуск фонового discovery для всех активных поликлиник
    doc_manager = DoctorManager(database)
    await doc_manager.load()

    # Получаем список активных клиник из БД
    clinic_ids = await database.get_active_clinic_ids()
    if not clinic_ids:
        logger.warning("Таблица clinics пуста, фоновый discovery не запущен")

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
        background_tasks.append(task)
        await _safe_set("discovery_tasks_alive", metrics.discovery_tasks_alive + 1)

    # Запуск фонового healthcheck
    background_tasks.append(asyncio.create_task(healthcheck_loop(bot, api, db)))

    # Запуск фоновой очистки старых сообщений
    background_tasks.append(asyncio.create_task(cleanup_loop(bot, db)))

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
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен.")
    except Exception as e:
        logging.exception("Необработанная ошибка при запуске")
        # Попытка отправить уведомление (может не сработать на старте)
        try:
            import asyncio as _asyncio

            _asyncio.run(error_notifier.notify(e, context="startup_crash"))
        except Exception:
            pass
