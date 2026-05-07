import asyncio
import logging
import os
import sys
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.session.aiohttp import AiohttpSession

from config import settings
from database.manager import DatabaseManager
from database.doctor_manager import DoctorManager
from api.zdrav_client import ZdravClient
from handlers import common, registration
from services.monitor import monitor_loop
from services.doctor_discovery import discovery_loop

async def main():
    # Настройка логирования
    if not os.path.exists('logs'):
        os.makedirs('logs')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
        handlers=[
            logging.FileHandler("logs/error.log", encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    logger = logging.getLogger(__name__)

    # Инициализация базы данных
    db = DatabaseManager(settings.DB_PATH)
    await db.load()

    # Инициализация API клиента
    api = ZdravClient()

    # Инициализация бота и диспетчера
    session = None
    if settings.PROXY_URL:
        session = AiohttpSession(proxy=settings.PROXY_URL)

    bot = Bot(token=settings.BOT_TOKEN, session=session)
    dp = Dispatcher(storage=MemoryStorage())

    # Регистрация роутеров
    dp.include_router(common.router)
    dp.include_router(registration.router)

    # Список фоновых задач для graceful shutdown
    background_tasks = []

    # Запуск фонового мониторинга
    background_tasks.append(asyncio.create_task(monitor_loop(bot, api, db)))

    # Запуск фонового discovery для всех поликлиник
    doc_manager = DoctorManager(settings.DOCTORS_PATH)
    await doc_manager.load()

    for clinic_id in settings.CLINICS:
        task = asyncio.create_task(
            discovery_loop(
                api, doc_manager, str(clinic_id),
                settings.DISCOVERY_PATIENT_ID_ADULT,
                settings.DISCOVERY_PATIENT_ID_CHILD
            )
        )
        background_tasks.append(task)

    logger.info("Бот запущен и готов помогать!")

    try:
        await dp.start_polling(bot, db=db, api=api)
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
