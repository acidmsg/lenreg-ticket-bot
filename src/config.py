import sqlite3
from collections.abc import Callable
from typing import Any

from loguru import logger
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Ключи конфигов, которые можно хранить в таблице config
CONFIG_KEY_API_TIMEOUT = "api_timeout"
CONFIG_KEY_CHECK_INTERVAL = "check_interval"
CONFIG_KEY_DISCOVERY_INTERVAL = "discovery_interval"
CONFIG_KEY_MESSAGE_TTL_SECONDS = "message_ttl_seconds"
CONFIG_KEY_CLEANUP_INTERVAL = "cleanup_interval"
CONFIG_KEY_SLOT_THRESHOLD_ABSOLUTE = "slot_threshold_absolute"
CONFIG_KEY_SLOT_THRESHOLD_PERCENTAGE = "slot_threshold_percentage"
CONFIG_KEY_SLOT_DETAIL_THRESHOLD = "slot_detail_threshold"
CONFIG_KEY_SLOT_COMPACT_THRESHOLD = "slot_compact_threshold"
CONFIG_KEY_DISCOVERY_PATIENT_ADULT = "discovery_patient_adult"
CONFIG_KEY_DISCOVERY_PATIENT_CHILD = "discovery_patient_child"
CONFIG_KEY_DEFAULT_CLINIC_ID = "default_clinic_id"
CONFIG_KEY_DEFAULT_BIRTHDAY = "default_birthday"
CONFIG_KEY_API_BASE_URL = "api_base_url"
CONFIG_KEY_REFERER_URL = "referer_url"
CONFIG_KEY_CSRF_TOKEN = "csrf_token"
CONFIG_KEY_ADMIN_IDS = "admin_ids"
CONFIG_KEY_ERROR_NOTIFY_ENABLED = "error_notify_enabled"
CONFIG_KEY_ENVIRONMENT = "environment"
CONFIG_KEY_USER_RATE_LIMIT_MAX = "user_rate_limit_max"
CONFIG_KEY_USER_RATE_LIMIT_PERIOD = "user_rate_limit_period"
CONFIG_KEY_METRICS_PORT = "metrics_port"
CONFIG_KEY_DENTAL_CLINIC_ID = "dental_clinic_id"
CONFIG_KEY_ORIGIN_URL = "origin_url"
CONFIG_KEY_DISTRICT_ID = "district_id"
CONFIG_KEY_SIGNUP_URL = "signup_url"
CONFIG_KEY_API_VERSION = "api_version"
CONFIG_KEY_API_VALIDATE_RESPONSES = "api_validate_responses"
CONFIG_KEY_SCHEMA_CHECK_INTERVAL = "schema_check_interval"
CONFIG_KEY_SCHEMA_CHECK_ENABLED = "schema_check_enabled"
CONFIG_KEY_WEB_DASHBOARD_ENABLED = "web_dashboard_enabled"
CONFIG_KEY_WEB_DASHBOARD_PORT = "web_dashboard_port"


class Settings(BaseSettings):
    BOT_TOKEN: str = "MUST_BE_OVERRIDDEN_IN_ENV"

    @field_validator("BOT_TOKEN")
    @classmethod
    def validate_bot_token(cls, v: str) -> str:
        """Отбрасывает плейсхолдер и пустые значения — падение на старте."""
        if not v or v == "MUST_BE_OVERRIDDEN_IN_ENV":
            raise ValueError(
                "BOT_TOKEN не задан! Укажите реальный токен бота в .env "
                "(см. .env.example)"
            )
        if not v[0].isdigit():
            raise ValueError(
                f"BOT_TOKEN не похож на токен Telegram (должен начинаться с цифры): "
                f"{v[:10]}..."
            )
        return v

    SQLITE_DB_PATH: str = "data/bot.db"
    CACHE_PATH: str = "data/monitoring_cache.json"
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: str = ""

    # === Qdrant (Codebase Indexing) ===
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: str | None = None

    # Прокси для Telegram
    PROXY_URL: str | None = None

    # Интервал проверки в секундах
    CHECK_INTERVAL: int = 300
    DISCOVERY_INTERVAL: int = 1800  # 30 минут

    # Таймаут запросов к API
    API_TIMEOUT: float = 10.0

    # Пороги для уведомлений об уменьшении номерков
    SLOT_THRESHOLD_ABSOLUTE: int = 5
    SLOT_THRESHOLD_PERCENTAGE: float = 0.25

    # Пороги для форматирования списка номерков
    # Если слотов на одну дату > этого порога — показываем диапазон (с HH:MM до HH:MM)
    SLOT_DETAIL_THRESHOLD: int = 10
    # Если всего слотов > этого порога — показываем компактно по датам
    SLOT_COMPACT_THRESHOLD: int = 15

    # ID пациентов для discovery (используются для получения списка специальностей)
    # Задаются через .env: DISCOVERY_PATIENT_ID_ADULT, DISCOVERY_PATIENT_ID_CHILD
    DISCOVERY_PATIENT_ID_ADULT: str = ""
    DISCOVERY_PATIENT_ID_CHILD: str = ""

    # === Вынесенные хардкоды ===

    # Базовый URL API zdrav.lenreg.ru
    API_BASE_URL: str = "https://zdrav.lenreg.ru/api"

    # Referer для HTTP-заголовков
    REFERER_URL: str = "https://zdrav.lenreg.ru/signup/free/"

    # CSRF-токен (технический, всегда одинаковый)
    # Default — пустая строка (будет WARNING в логах, если не задан).
    # Переопределяется через .env (значение NOTPROVIDED — корректное).
    CSRF_TOKEN: str = ""

    # Клиника по умолчанию для первичного поиска пациента
    DEFAULT_CLINIC_ID: str = "272"

    # ID стоматологической клиники (для фильтрации детских/взрослых специальностей)
    DENTAL_CLINIC_ID: str = "272"

    # Origin для HTTP-заголовков
    ORIGIN_URL: str = "https://zdrav.lenreg.ru"

    # ID района по умолчанию для получения списка клиник
    DISTRICT_ID: str = "4"

    # Дефолтная дата рождения для новых пациентов без даты
    DEFAULT_BIRTHDAY: str = "1990-01-01"

    # Публичная ссылка для записи (отображается в уведомлениях)
    SIGNUP_URL: str = "https://zdrav.lenreg.ru/signup/free/"

    # ID админов с доступом к /status (через запятую, напр.: 123456789,987654321)
    ADMIN_IDS: str = ""

    # Автоудаление сообщений: TTL в секундах (7 дней по умолчанию)
    MESSAGE_TTL_SECONDS: int = 604800
    CLEANUP_INTERVAL: int = 3600  # Проверять каждые 1 час

    # === Error notifications (M2) ===
    # Enable/disable error notifications globally (synced to DB)
    ERROR_NOTIFY_ENABLED: bool = True

    # NTFY topic URL — SECRET, .env only (e.g. https://ntfy.sh/your-topic)
    NTFY_TOPIC_URL: str = ""

    # Sentry DSN — SECRET, .env only
    SENTRY_DSN: str = ""

    # Environment tag for Sentry (synced to DB)
    ENVIRONMENT: str = "production"

    # === Аутентификация Mini App ===
    # Принудительно включает/отключает проверку initData для Mini App API.
    # True — проверка всегда включена (независимо от ENVIRONMENT).
    # False — проверка отключена (только для локальной разработки).
    MINI_APP_AUTH_ENABLED: bool = True

    # === Rate limiting (M3) ===
    # Max messages per user per time period (handler-level, synced to DB)
    USER_RATE_LIMIT_MAX: int = 30
    USER_RATE_LIMIT_PERIOD: int = 60  # seconds

    # === Prometheus Metrics ===
    # Порт для HTTP-endpoint /metrics
    METRICS_PORT: int = 9090

    # === API Versioning ===
    # Версия API-клиента (передаётся в заголовке X-Client-Version)
    API_VERSION: str = "1.0.0"
    # Валидация ответов API через Pydantic-схемы
    API_VALIDATE_RESPONSES: bool = True

    # === i18n ===
    # Язык интерфейса бота (ru, en)
    BOT_LANGUAGE: str = "ru"

    # === API Schema Change Detection (F8) ===
    # Интервал проверки схем API (секунды, по умолчанию 1 час)
    SCHEMA_CHECK_INTERVAL: int = 3600
    # Включить/выключить проверку схем API
    SCHEMA_CHECK_ENABLED: bool = True

    # === Web Dashboard (F5) ===
    WEB_DASHBOARD_ENABLED: bool = True
    WEB_DASHBOARD_PORT: int = 8080
    WEB_DASHBOARD_API_KEY: str = ""

    # === Mini App (F10) ===
    MINI_APP_ENABLED: bool = True
    MINI_APP_URL: str = ""  # Полный URL Mini App (например, https://example.com/app/)
    MINI_APP_INITDATA_MAX_AGE: int = 86400  # 24 часа (в секундах)

    # === Backup (F13) ===
    # Корневая директория для хранения бэкапов
    backup_dir: str = "data/backups"
    # Количество хранимых daily-бэкапов
    backup_daily_retention: int = 7
    # Количество хранимых weekly-бэкапов
    backup_weekly_retention: int = 4
    # Количество хранимых monthly-бэкапов
    backup_monthly_retention: int = 3
    # NTFY-топик для алертов системы бэкапов (опционально)
    ntfy_backup_topic: str = ""
    # Режим восстановления: True — в контейнере (без docker compose), False — на хосте
    restore_in_container: bool = False

    def model_post_init(self, __context: Any) -> None:
        """
        Пост-инициализация: если задан REDIS_PASSWORD, встраивает его в REDIS_URL.

        Пароль вставляется по схеме redis:// → redis://:password@, чтобы клиент
        Redis (redis-py) автоматически использовал его при аутентификации.
        Если пароль не задан или REDIS_URL уже содержит `@` (т.е. пароль уже
        встроен), URL не изменяется.
        """
        # Проверка ENVIRONMENT: development-режим опасен в production
        if self.ENVIRONMENT == "development":
            logger.warning(
                "⚠️ ENVIRONMENT=development! Это отключает некоторые проверки "
                "безопасности. Убедитесь, что это не production-окружение. "
                "Аутентификация Mini App управляется флагом MINI_APP_AUTH_ENABLED "
                "независимо от ENVIRONMENT."
            )

        if not self.REDIS_PASSWORD:
            logger.warning(
                "REDIS_PASSWORD не задан! Redis-подключение будет без аутентификации. "
                "Если Redis настроен с `requirepass`, подключение упадёт с NOAUTH."
            )
            return

        if "://" not in self.REDIS_URL:
            logger.error(
                "REDIS_URL имеет нестандартный формат (нет '://'): %s — "
                "пропускаем встраивание пароля",
                self.REDIS_URL,
            )
            return

        scheme, rest = self.REDIS_URL.split("://", 1)

        if "@" in rest:
            logger.debug(
                "REDIS_URL уже содержит пароль или имя пользователя (@): %s — "
                "пропускаем встраивание",
                self.REDIS_URL,
            )
            return

        self.REDIS_URL = f"{scheme}://:{self.REDIS_PASSWORD}@{rest}"
        logger.info(
            "Пароль Redis встроен в REDIS_URL (схема: %s, хост сокрыт)",
            scheme,
        )

    # Валидация: если CSRF_TOKEN пустой — логируем WARNING
    @field_validator("CSRF_TOKEN")
    @classmethod
    def warn_empty_csrf(cls, v: str) -> str:
        if not v:
            logger.warning(
                "CSRF_TOKEN не задан! Укажите его в .env для корректной работы API. "
                "Допустимое значение: NOTPROVIDED"
            )
        return v

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()


async def load_config_from_db(database) -> None:
    """
    Загружает настройки из таблицы config БД и переопределяет значения settings.
    Вызывается при старте бота после инициализации БД.

    При недоступности БД логирует WARNING и продолжает работу
    с default-значениями из .env.
    """
    try:
        mapping: dict[str, tuple[str, Callable[[str], Any]]] = {
            CONFIG_KEY_API_TIMEOUT: ("API_TIMEOUT", float),
            CONFIG_KEY_CHECK_INTERVAL: ("CHECK_INTERVAL", int),
            CONFIG_KEY_DISCOVERY_INTERVAL: ("DISCOVERY_INTERVAL", int),
            CONFIG_KEY_MESSAGE_TTL_SECONDS: ("MESSAGE_TTL_SECONDS", int),
            CONFIG_KEY_CLEANUP_INTERVAL: ("CLEANUP_INTERVAL", int),
            CONFIG_KEY_SLOT_THRESHOLD_ABSOLUTE: ("SLOT_THRESHOLD_ABSOLUTE", int),
            CONFIG_KEY_SLOT_THRESHOLD_PERCENTAGE: ("SLOT_THRESHOLD_PERCENTAGE", float),
            CONFIG_KEY_SLOT_DETAIL_THRESHOLD: ("SLOT_DETAIL_THRESHOLD", int),
            CONFIG_KEY_SLOT_COMPACT_THRESHOLD: ("SLOT_COMPACT_THRESHOLD", int),
            CONFIG_KEY_DISCOVERY_PATIENT_ADULT: ("DISCOVERY_PATIENT_ID_ADULT", str),
            CONFIG_KEY_DISCOVERY_PATIENT_CHILD: ("DISCOVERY_PATIENT_ID_CHILD", str),
            CONFIG_KEY_DEFAULT_CLINIC_ID: ("DEFAULT_CLINIC_ID", str),
            CONFIG_KEY_DENTAL_CLINIC_ID: ("DENTAL_CLINIC_ID", str),
            CONFIG_KEY_ORIGIN_URL: ("ORIGIN_URL", str),
            CONFIG_KEY_DISTRICT_ID: ("DISTRICT_ID", str),
            CONFIG_KEY_DEFAULT_BIRTHDAY: ("DEFAULT_BIRTHDAY", str),
            CONFIG_KEY_SIGNUP_URL: ("SIGNUP_URL", str),
            CONFIG_KEY_API_BASE_URL: ("API_BASE_URL", str),
            CONFIG_KEY_REFERER_URL: ("REFERER_URL", str),
            CONFIG_KEY_CSRF_TOKEN: ("CSRF_TOKEN", str),
            CONFIG_KEY_ADMIN_IDS: ("ADMIN_IDS", str),
            CONFIG_KEY_ENVIRONMENT: ("ENVIRONMENT", str),
            CONFIG_KEY_ERROR_NOTIFY_ENABLED: (
                "ERROR_NOTIFY_ENABLED",
                lambda v: v.lower() in ("1", "true", "yes"),
            ),
            CONFIG_KEY_USER_RATE_LIMIT_MAX: ("USER_RATE_LIMIT_MAX", int),
            CONFIG_KEY_USER_RATE_LIMIT_PERIOD: ("USER_RATE_LIMIT_PERIOD", int),
            CONFIG_KEY_METRICS_PORT: ("METRICS_PORT", int),
            CONFIG_KEY_API_VERSION: ("API_VERSION", str),
            CONFIG_KEY_API_VALIDATE_RESPONSES: (
                "API_VALIDATE_RESPONSES",
                lambda v: v.lower() in ("1", "true", "yes"),
            ),
            CONFIG_KEY_SCHEMA_CHECK_INTERVAL: (
                "SCHEMA_CHECK_INTERVAL",
                int,
            ),
            CONFIG_KEY_SCHEMA_CHECK_ENABLED: (
                "SCHEMA_CHECK_ENABLED",
                lambda v: v.lower() in ("1", "true", "yes"),
            ),
            CONFIG_KEY_WEB_DASHBOARD_ENABLED: (
                "WEB_DASHBOARD_ENABLED",
                lambda v: v.lower() in ("1", "true", "yes"),
            ),
            CONFIG_KEY_WEB_DASHBOARD_PORT: (
                "WEB_DASHBOARD_PORT",
                int,
            ),
        }

        # Ключи, для которых требуется дополнительная валидация значения
        _validators: dict[str, Callable[[str], bool]] = {
            CONFIG_KEY_CSRF_TOKEN: lambda v: "***" not in v and v != "",
        }

        all_config = await database.get_all_config()
        loaded = 0
        for key, value in all_config.items():
            if key in mapping:
                attr_name, cast_type = mapping[key]

                # Дополнительная валидация для критичных ключей
                if key in _validators and not _validators[key](value):
                    logger.error(
                        "config[%s] содержит мусорное значение '%s' — "
                        "используется дефолтное значение из .env",
                        key,
                        value,
                    )
                    continue

                try:
                    setattr(settings, attr_name, cast_type(value))
                    loaded += 1
                except (ValueError, TypeError):
                    logger.warning(
                        "Не удалось преобразовать config[%s]='%s' в %s",
                        key,
                        value,
                        cast_type.__name__,
                    )

        if loaded:
            logger.info(f"Загружено {loaded} настроек из таблицы config")
    except RuntimeError:
        logger.warning(
            "Соединение с БД не установлено — загрузка конфигурации из БД "
            "пропущена, используются default-значения из .env"
        )
    except sqlite3.DatabaseError as e:
        logger.warning(
            "Ошибка БД при загрузке конфигурации: {} — используются "
            "default-значения из .env",
            e,
        )
    except Exception as e:
        logger.warning(
            "Не удалось загрузить настройки из config: {} — используются "
            "default-значения из .env",
            e,
        )
