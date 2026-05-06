import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp_socks import ProxyConnector

from config import settings
from database.manager import DatabaseManager
from api.zdrav_client import ZdravClient
from handlers import common, registration
from services.monitor import monitor_loop

async def main():
    # Настройка логирования
    import os
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

    # Запуск фонового мониторинга
    asyncio.create_task(monitor_loop(bot, api, db))

    # Запуск фонового discovery для всех поликлиник
    from services.doctor_discovery import discovery_loop
    from database.doctor_manager import DoctorManager

    doc_manager = DoctorManager(settings.DOCTORS_PATH)
    await doc_manager.load()

    # Запуск фонового discovery для всех поликлиник
    # Используем разных пациентов для разных типов клиник для корректного получения специальностей
    patient_id_adult = "2343192"
    patient_id_child = "2509768"

    for clinic_id in settings.CLINICS:
        asyncio.create_task(discovery_loop(api, doc_manager, str(clinic_id), patient_id_adult, patient_id_child))

    logger.info("Бот запущен и готов помогать! 🚀")

    try:
        await dp.start_polling(bot, db=db, api=api)
    finally:
        if bot.session:
            await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен. До скорой встречи! 👋")
