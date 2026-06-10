"""
Репозиторий конфигурации: key-value хранилище (таблица config).
"""

from __future__ import annotations

from loguru import logger

from src.database.base_repo import BaseRepository


class ConfigRepository(BaseRepository):
    """CRUD-операции с конфигурацией (таблица config)."""

    async def get_config(self, key: str, default: str = "") -> str:
        """Возвращает значение конфига по ключу."""
        try:
            c = self._db_conn.conn
            if c is None:
                return default
            cursor = await c.execute("SELECT value FROM config WHERE key = ?", (key,))
            row = await cursor.fetchone()
            return row["value"] if row else default
        except Exception:
            logger.debug("Ошибка при get_config key={}", key, exc_info=True)
            return default

    async def set_config(self, key: str, value: str) -> None:
        """Устанавливает значение конфига."""
        await self._c.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            (key, value),
        )
        await self._c.commit()

    async def get_all_config(self) -> dict[str, str]:
        """Возвращает все конфиги как dict."""
        cursor = await self._c.execute("SELECT key, value FROM config")
        rows = await cursor.fetchall()
        return {row["key"]: row["value"] for row in rows}

    async def seed_config_from_defaults(self) -> None:
        """
        Заполняет таблицу config дефолтными значениями из settings,
        если она пуста.
        """
        try:
            c = self._db_conn.conn
            if c is None:
                return
            cursor = await c.execute("SELECT COUNT(*) as cnt FROM config")
            row = await cursor.fetchone()
            if row and row["cnt"] > 0:
                return  # уже есть данные

            from src.config import settings as s

            defaults = {
                "api_timeout": str(s.API_TIMEOUT),
                "check_interval": str(s.CHECK_INTERVAL),
                "discovery_interval": str(s.DISCOVERY_INTERVAL),
                "message_ttl_seconds": str(s.MESSAGE_TTL_SECONDS),
                "cleanup_interval": str(s.CLEANUP_INTERVAL),
                "slot_threshold_absolute": str(s.SLOT_THRESHOLD_ABSOLUTE),
                "slot_threshold_percentage": str(s.SLOT_THRESHOLD_PERCENTAGE),
                "slot_detail_threshold": str(s.SLOT_DETAIL_THRESHOLD),
                "slot_compact_threshold": str(s.SLOT_COMPACT_THRESHOLD),
                "discovery_patient_adult": str(s.DISCOVERY_PATIENT_ID_ADULT),
                "discovery_patient_child": str(s.DISCOVERY_PATIENT_ID_CHILD),
                "default_clinic_id": str(s.DEFAULT_CLINIC_ID),
                "default_birthday": str(s.DEFAULT_BIRTHDAY),
                "api_base_url": s.API_BASE_URL,
                "referer_url": s.REFERER_URL,
                "csrf_token": s.CSRF_TOKEN,
                "admin_ids": s.ADMIN_IDS,
                "error_notify_enabled": str(s.ERROR_NOTIFY_ENABLED),
                "environment": s.ENVIRONMENT,
                "user_rate_limit_max": str(s.USER_RATE_LIMIT_MAX),
                "user_rate_limit_period": str(s.USER_RATE_LIMIT_PERIOD),
            }

            for key, value in defaults.items():
                await self.set_config(key, value)
            logger.info(
                "Таблица config заполнена дефолтными значениями (%s записей)",
                len(defaults),
            )
        except Exception as e:
            logger.error(
                "Не удалось заполнить config из defaults: {}",
                e,
                exc_info=True,
            )
