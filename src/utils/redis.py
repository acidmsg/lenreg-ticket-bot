"""
Модуль управления подключением к Redis.

Предоставляет singleton-клиент RedisClient с asyncio-поддержкой,
пулом соединений и корректным завершением работы.
"""

# pyright: reportGeneralTypeIssues=false, reportAttributeAccessIssue=false, reportReturnType=false
# mypy: ignore-errors
# redis-py 7.x использует Protocol для Redis.asyncio.Redis — pyright и mypy
# некорректно разрешают Awaitable[X] | X при await и не видят атрибут client.
# Сигнатуры методов возвращают Awaitable[X] | X, из-за чего статические
# анализаторы не могут сузить возвращаемый тип до bool/int/list[str].

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from src.config import settings

if TYPE_CHECKING:
    pass


class RedisClient:
    """
    Singleton-клиент Redis с asyncio-поддержкой и graceful degradation.

    Управляет пулом соединений, предоставляет атомарные операции
    и корректное завершение работы. При недоступности Redis возвращает
    безопасные значения по умолчанию, не прерывая работу бота.

    Использование:
        redis = await RedisClient.get_instance()
        if redis.is_available:
            await redis.set("key", "value", ex=60)
            value = await redis.get("key")
    """

    _instance: RedisClient | None = None
    _lock: Any = None  # asyncio.Lock, инициализируется при первом вызове

    def __init__(self) -> None:
        self._redis: Any = None  # aioredis.Redis (ленивый импорт)
        self._url: str = settings.REDIS_URL
        self._available: bool = False

    @classmethod
    async def get_instance(cls) -> RedisClient:
        """
        Возвращает singleton-экземпляр RedisClient.

        Если Redis недоступен, экземпляр всё равно создаётся, но переходит
        в режим graceful degradation (is_available = False). Все методы
        возвращают безопасные значения по умолчанию.
        """
        if cls._instance is None:
            import asyncio

            if cls._lock is None:
                cls._lock = asyncio.Lock()

            async with cls._lock:
                if cls._instance is None:
                    instance = cls()
                    await instance._connect()
                    cls._instance = instance
                    if instance._available:
                        logger.info("Redis-клиент инициализирован")
                    else:
                        logger.warning(
                            "Redis недоступен — бот работает в режиме "
                            "graceful degradation (без кэша и rate limiting)"
                        )
        return cls._instance

    async def _connect(self) -> None:
        """Устанавливает соединение с Redis. При неудаче переходит в fallback-режим."""
        import redis.asyncio as aioredis

        try:
            self._redis = aioredis.from_url(
                self._url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=10,
                socket_connect_timeout=5,
                socket_keepalive=True,
                health_check_interval=30,
            )
            await self._redis.ping()
            self._available = True
        except Exception as e:
            logger.warning(f"Не удалось подключиться к Redis ({self._url}): {e}")
            self._available = False
            # Закрываем неудачное соединение, если оно было создано
            if self._redis is not None:
                try:
                    await self._redis.aclose()
                except Exception:
                    logger.debug("Не удалось закрыть неудачное Redis-соединение")
                self._redis = None

    @property
    def is_available(self) -> bool:
        """True, если Redis доступен и готов к использованию."""
        return self._available

    @property
    def client(self) -> Any:  # aioredis.Redis
        """
        Возвращает экземпляр aioredis.Redis.

        Вызывает RuntimeError, если клиент не инициализирован (Redis был доступен,
        но _redis = None) или если Redis недоступен. Перед обращением к client
        всегда проверяйте is_available.
        """
        if self._redis is None:
            raise RuntimeError(
                "Redis-клиент недоступен. Проверьте is_available перед вызовом."
            )
        return self._redis

    async def get(self, key: str) -> str | None:
        """Получает значение по ключу. Возвращает None при недоступности Redis."""
        if not self._available:
            return None
        return await self.client.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        """Устанавливает значение. Возвращает False при недоступности Redis."""
        if not self._available:
            return False
        return await self.client.set(key, value, ex=ex)

    async def delete(self, *keys: str) -> int:
        """Удаляет ключи. Возвращает 0 при недоступности Redis."""
        if not self._available:
            return 0
        return await self.client.delete(*keys)

    async def exists(self, *keys: str) -> int:
        """Проверяет существование ключей. Возвращает 0 при недоступности Redis."""
        if not self._available:
            return 0
        return await self.client.exists(*keys)

    async def expire(self, key: str, seconds: int) -> bool:
        """Устанавливает TTL. Возвращает False при недоступности Redis."""
        if not self._available:
            return False
        return await self.client.expire(key, seconds)

    async def ttl(self, key: str) -> int:
        """
        Возвращает оставшееся время жизни ключа.
        Возвращает -2 (ключ не существует) при недоступности Redis.
        """
        if not self._available:
            return -2
        return await self.client.ttl(key)

    async def keys(self, pattern: str) -> list[str]:
        """Возвращает список ключей. Возвращает [] при недоступности Redis."""
        if not self._available:
            return []
        return await self.client.keys(pattern)

    async def incr(self, key: str) -> int:
        """Атомарно инкрементирует значение. Возвращает 0 при недоступности Redis."""
        if not self._available:
            return 0
        return await self.client.incr(key)

    async def rpush(self, key: str, *values: str) -> int:
        """Добавляет значения в список. Возвращает 0 при недоступности Redis."""
        if not self._available:
            return 0
        return await self.client.rpush(key, *values)

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        """Возвращает срез списка. Возвращает [] при недоступности Redis."""
        if not self._available:
            return []
        return await self.client.lrange(key, start, end)

    async def ltrim(self, key: str, start: int, end: int) -> bool:
        """Обрезает список. Возвращает False при недоступности Redis."""
        if not self._available:
            return False
        return await self.client.ltrim(key, start, end)

    async def llen(self, key: str) -> int:
        """Возвращает длину списка. Возвращает 0 при недоступности Redis."""
        if not self._available:
            return 0
        return await self.client.llen(key)

    async def pipeline(self) -> Any:  # aioredis.client.Pipeline
        """
        Создаёт pipeline для атомарного выполнения команд.

        Вызывает RuntimeError при недоступности Redis. Перед вызовом
        всегда проверяйте is_available.
        """
        if not self._available:
            raise RuntimeError("Redis недоступен — pipeline невозможен")
        return self.client.pipeline()

    async def health_check(self) -> bool:
        """Проверяет доступность Redis. Возвращает False при недоступности."""
        if not self._available:
            return False
        try:
            await self.client.ping()
            return True
        except Exception:
            self._available = False
            return False

    async def close(self) -> None:
        """Закрывает соединение с Redis."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
            self._available = False
            logger.info("Соединение с Redis закрыто")

    @classmethod
    async def shutdown(cls) -> None:
        """Закрывает singleton-клиент и сбрасывает состояние."""
        if cls._instance is not None:
            await cls._instance.close()
            cls._instance = None


async def get_redis() -> RedisClient:
    """Возвращает singleton-клиент Redis (удобная функция-помощник)."""
    return await RedisClient.get_instance()
