import logging
import os
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


# Ключи конфигов, которые можно хранить в таблице config
CONFIG_KEY_API_TIMEOUT = "api_timeout"
CONFIG_KEY_CHECK_INTERVAL = "check_interval"
CONFIG_KEY_DISCOVERY_INTERVAL = "discovery_interval"
CONFIG_KEY_MESSAGE_TTL_SECONDS = "message_ttl_seconds"
CONFIG_KEY_CLEANUP_INTERVAL = "cleanup_interval"
CONFIG_KEY_SLOT_THRESHOLD_ABSOLUTE = "slot_threshold_absolute"
CONFIG_KEY_SLOT_THRESHOLD_PERCENTAGE = "slot_threshold_percentage"
CONFIG_KEY_DISCOVERY_PATIENT_ADULT = "discovery_patient_adult"
CONFIG_KEY_DISCOVERY_PATIENT_CHILD = "discovery_patient_child"
CONFIG_KEY_DEFAULT_CLINIC_ID = "default_clinic_id"
CONFIG_KEY_DEFAULT_BIRTHDAY = "default_birthday"
CONFIG_KEY_API_BASE_URL = "api_base_url"
CONFIG_KEY_REFERER_URL = "referer_url"
CONFIG_KEY_CSRF_TOKEN = "csrf_token"
CONFIG_KEY_ADMIN_IDS = "admin_ids"


class Settings(BaseSettings):
    BOT_TOKEN: str = "MUST_BE_OVERRIDDEN_IN_ENV"
    SQLITE_DB_PATH: str = "data/bot.db"
    CACHE_PATH: str = "data/monitoring_cache.json"

    # Прокси для Telegram
    PROXY_URL: Optional[str] = None

    # Интервал проверки в секундах
    CHECK_INTERVAL: int = 300
    DISCOVERY_INTERVAL: int = 1800  # 30 минут

    # Таймаут запросов к API
    API_TIMEOUT: float = 10.0

    # Пороги для уведомлений об уменьшении номерков
    SLOT_THRESHOLD_ABSOLUTE: int = 5
    SLOT_THRESHOLD_PERCENTAGE: float = 0.25

    # ID пациентов для discovery (используются для получения списка специальностей)
    DISCOVERY_PATIENT_ID_ADULT: str = "2343192"
    DISCOVERY_PATIENT_ID_CHILD: str = "2509768"

    # === Вынесенные хардкоды ===

    # Базовый URL API zdrav.lenreg.ru
    API_BASE_URL: str = "https://zdrav.lenreg.ru/api"

    # Referer для HTTP-заголовков
    REFERER_URL: str = "https://zdrav.lenreg.ru/signup/free/"

    # CSRF-токен (технический, всегда одинаковый)
    CSRF_TOKEN: str = "NOTPROVIDED"

    # Клиника по умолчанию для первичного поиска пациента
    DEFAULT_CLINIC_ID: str = "272"

    # Дефолтная дата рождения для новых пациентов без даты
    DEFAULT_BIRTHDAY: str = "1990-01-01"

    # ID администраторов, имеющих доступ к команде /status (через запятую, например: 123456789 или 123456789,987654321)
    ADMIN_IDS: str = ""

    # Автоудаление сообщений: TTL в секундах (7 дней по умолчанию)
    MESSAGE_TTL_SECONDS: int = 604800
    CLEANUP_INTERVAL: int = 3600  # Проверять каждые 1 час

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()


async def load_config_from_db(database):
    """
    Загружает настройки из таблицы config БД и переопределяет значения settings.
    Вызывается при старте бота после инициализации БД.
    """
    try:
        mapping = {
            CONFIG_KEY_API_TIMEOUT: ("API_TIMEOUT", float),
            CONFIG_KEY_CHECK_INTERVAL: ("CHECK_INTERVAL", int),
            CONFIG_KEY_DISCOVERY_INTERVAL: ("DISCOVERY_INTERVAL", int),
            CONFIG_KEY_MESSAGE_TTL_SECONDS: ("MESSAGE_TTL_SECONDS", int),
            CONFIG_KEY_CLEANUP_INTERVAL: ("CLEANUP_INTERVAL", int),
            CONFIG_KEY_SLOT_THRESHOLD_ABSOLUTE: ("SLOT_THRESHOLD_ABSOLUTE", int),
            CONFIG_KEY_SLOT_THRESHOLD_PERCENTAGE: ("SLOT_THRESHOLD_PERCENTAGE", float),
            CONFIG_KEY_DISCOVERY_PATIENT_ADULT: ("DISCOVERY_PATIENT_ID_ADULT", str),
            CONFIG_KEY_DISCOVERY_PATIENT_CHILD: ("DISCOVERY_PATIENT_ID_CHILD", str),
            CONFIG_KEY_DEFAULT_CLINIC_ID: ("DEFAULT_CLINIC_ID", str),
            CONFIG_KEY_DEFAULT_BIRTHDAY: ("DEFAULT_BIRTHDAY", str),
            CONFIG_KEY_API_BASE_URL: ("API_BASE_URL", str),
            CONFIG_KEY_REFERER_URL: ("REFERER_URL", str),
            CONFIG_KEY_CSRF_TOKEN: ("CSRF_TOKEN", str),
            CONFIG_KEY_ADMIN_IDS: ("ADMIN_IDS", str),
        }

        all_config = await database.get_all_config()
        loaded = 0
        for key, value in all_config.items():
            if key in mapping:
                attr_name, cast_type = mapping[key]
                try:
                    setattr(settings, attr_name, cast_type(value))
                    loaded += 1
                except (ValueError, TypeError):
                    logger.warning(
                        f"Не удалось преобразовать config[{key}]='{value}' в {cast_type.__name__}"
                    )

        if loaded:
            logger.info(f"Загружено {loaded} настроек из таблицы config")
    except Exception as e:
        logger.warning(f"Не удалось загрузить настройки из config: {e}")
