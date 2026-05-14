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

from typing import Optional

import redis.asyncio as aioredis
from loguru import logger

from src.config import settings


class RedisClient:
    """
    Singleton-клиент Redis с asyncio-поддержкой.

    Управляет пулом соединений, предоставляет атомарные операции
    и корректное завершение работы.

    Использование:
        redis = await RedisClient.get_instance()
        await redis.set("key", "value", ex=60)
        value = await redis.get("key")
    """

    _instance: Optional[RedisClient] = None
    _lock = None  # asyncio.Lock, инициализируется при первом вызове

    def __init__(self) -> None:
        self._redis: Optional[aioredis.Redis] = None
        self._url: str = settings.REDIS_URL

    @classmethod
    async def get_instance(cls) -> RedisClient:
        """Возвращает singleton-экземпляр RedisClient, создавая при необходимости."""
        if cls._instance is None:
            import asyncio

            if cls._lock is None:
                cls._lock = asyncio.Lock()

            async with cls._lock:
                if cls._instance is None:
                    instance = cls()
                    await instance._connect()
                    cls._instance = instance
                    logger.info("Redis-клиент инициализирован")
        return cls._instance

    async def _connect(self) -> None:
        """Устанавливает соединение с Redis через пул."""
        self._redis = aioredis.from_url(
            self._url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=10,
            socket_connect_timeout=5,
            socket_keepalive=True,
            health_check_interval=30,
        )
        # Проверка соединения
        await self._redis.ping()

    @property
    def client(self) -> aioredis.Redis:
        """Возвращает экземпляр aioredis.Redis (нужна предварительная инициализация)."""
        if self._redis is None:
            raise RuntimeError(
                "Redis-клиент не инициализирован. Вызовите get_instance() сначала."
            )
        return self._redis

    async def get(self, key: str) -> Optional[str]:
        """Получает значение по ключу."""
        return await self.client.get(key)

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        """Устанавливает значение с опциональным TTL (в секундах)."""
        return await self.client.set(key, value, ex=ex)

    async def delete(self, *keys: str) -> int:
        """Удаляет ключи. Возвращает количество удалённых."""
        return await self.client.delete(*keys)

    async def exists(self, *keys: str) -> int:
        """Проверяет существование ключей. Возвращает количество существующих."""
        return await self.client.exists(*keys)

    async def expire(self, key: str, seconds: int) -> bool:
        """Устанавливает TTL на ключ."""
        return await self.client.expire(key, seconds)

    async def ttl(self, key: str) -> int:
        """Возвращает оставшееся время жизни ключа в секундах."""
        return await self.client.ttl(key)

    async def keys(self, pattern: str) -> list[str]:
        """Возвращает список ключей по шаблону (использовать осторожно в production)."""
        return await self.client.keys(pattern)

    async def incr(self, key: str) -> int:
        """Атомарно инкрементирует значение ключа."""
        return await self.client.incr(key)

    async def rpush(self, key: str, *values: str) -> int:
        """Добавляет значения в конец списка."""
        return await self.client.rpush(key, *values)

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        """Возвращает срез списка."""
        return await self.client.lrange(key, start, end)

    async def ltrim(self, key: str, start: int, end: int) -> bool:
        """Обрезает список до указанного диапазона."""
        return await self.client.ltrim(key, start, end)

    async def llen(self, key: str) -> int:
        """Возвращает длину списка."""
        return await self.client.llen(key)

    async def pipeline(self) -> aioredis.client.Pipeline:
        """Создаёт pipeline для атомарного выполнения нескольких команд."""
        return self.client.pipeline()

    async def health_check(self) -> bool:
        """Проверяет доступность Redis."""
        try:
            await self.client.ping()
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Закрывает соединение с Redis."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
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
