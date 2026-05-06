import os
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional

class Settings(BaseSettings):
    BOT_TOKEN: str = "MUST_BE_OVERRIDDEN_IN_ENV"
    DB_PATH: str = "data/users_config.json"
    DOCTORS_PATH: str = "data/doctors.json"
    CACHE_PATH: str = "data/monitoring_cache.json"

    # Прокси для Telegram
    PROXY_URL: Optional[str] = None

    # Интервал проверки в секундах
    CHECK_INTERVAL: int = 300
    DISCOVERY_INTERVAL: int = 1800  # 30 минут
    CLINICS: list = [272, 271, 161]

    # Таймаут запросов к API
    API_TIMEOUT: float = 10.0

    class Config:
        env_file = ".env"

settings = Settings()
