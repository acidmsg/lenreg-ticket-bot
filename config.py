import os
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ClinicInfo:
    """Информация о поликлинике."""

    def __init__(self, name: str, clinic_type: str):
        self.name = name
        self.type = clinic_type


# Единый справочник клиник -- используется везде в проекте
CLINICS_REGISTRY: dict[str, ClinicInfo] = {
    "272": ClinicInfo(name="Стоматологическая", clinic_type="all"),
    "271": ClinicInfo(name="Взрослая", clinic_type="adult"),
    "161": ClinicInfo(name="Детская", clinic_type="child"),
}


class Settings(BaseSettings):
    BOT_TOKEN: str = "MUST_BE_OVERRIDDEN_IN_ENV"
    SQLITE_DB_PATH: str = "data/bot.db"
    CACHE_PATH: str = "data/monitoring_cache.json"

    # Прокси для Telegram
    PROXY_URL: Optional[str] = None

    # Интервал проверки в секундах
    CHECK_INTERVAL: int = 300
    DISCOVERY_INTERVAL: int = 1800  # 30 минут
    CLINICS: list = [272, 271, 161]

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

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
