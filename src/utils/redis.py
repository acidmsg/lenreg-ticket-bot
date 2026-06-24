"""
Модуль управления подключением к Redis.

Предоставляет клиент RedisClient с asyncio-поддержкой,
пулом соединений и корректным завершением работы.
Экземпляры привязаны к event loop, в котором созданы.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import TYPE_CHECKING, Any, ClassVar, cast

from loguru import logger
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError
from redis.exceptions import TimeoutError as RedisTimeoutError

from src.config import settings

if TYPE_CHECKING:
    from redis.asyncio import Redis


class RedisClient:
    """Клиент Redis с asyncio-поддержкой и graceful degradation.

    Управляет пулом соединений, предоставляет атомарные операции
    и корректное завершение работы. При недоступности Redis возвращает
    безопасные значения по умолчанию, не прерывая работу бота.

    **Важно:** Экземпляры привязаны к event loop, в котором созданы.
    ``get_instance()`` возвращает экземпляр для текущего event loop.
    Это позволяет использовать Redis из разных потоков (бот + веб-дашборд)
    без ошибок «bound to a different event loop».

    Использование:
        redis = await RedisClient.get_instance()
        if redis.is_available:
            await redis.set("key", "value", ex=60)
            value = await redis.get("key")
    """

    _instances: ClassVar[dict[int, RedisClient]] = {}
    _locks: ClassVar[dict[int, Any]] = {}

    def __init__(self) -> None:
        self._redis: Redis | None = None
        self._url: str = settings.REDIS_URL
        self._available: bool = False

    @classmethod
    async def get_instance(cls) -> RedisClient:
        """Возвращает экземпляр RedisClient для текущего event loop.

        Создаёт новый экземпляр при первом обращении из каждого event loop.
        Это предотвращает ошибки «bound to a different event loop» при
        использовании Redis из веб-дашборда (uvicorn в отдельном потоке).

        Если Redis недоступен, экземпляр всё равно создаётся, но переходит
        в режим graceful degradation (is_available = False). Все методы
        возвращают безопасные значения по умолчанию.
        """
        import asyncio

        loop = asyncio.get_running_loop()
        loop_id = id(loop)

        if loop_id in cls._instances:
            return cls._instances[loop_id]

        if loop_id not in cls._locks:
            cls._locks[loop_id] = asyncio.Lock()

        async with cls._locks[loop_id]:
            if loop_id in cls._instances:
                return cls._instances[loop_id]
            instance = cls()
            await instance._connect()
            cls._instances[loop_id] = instance
            if instance._available:
                logger.info("Redis-клиент инициализирован")
            else:
                logger.warning(
                    "Redis недоступен — бот работает в режиме "
                    "graceful degradation (без кэша и rate limiting)"
                )
        return cls._instances[loop_id]

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
    def client(self) -> Redis:
        """Возвращает экземпляр aioredis.Redis.

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
        try:
            return cast("str | None", await self.client.get(key))
        except RedisConnectionError as e:
            logger.warning(
                f"Redis get({key}): connection error — {e}. Fallback: return None."
            )
            return None
        except RedisTimeoutError as e:
            logger.warning(f"Redis get({key}): timeout — {e}. Fallback: return None.")
            return None
        except RedisError as e:
            logger.error(
                f"Redis get({key}): Redis error — {e}. Fallback: return None.",
                exc_info=True,
            )
            return None

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        """Устанавливает значение. Возвращает False при недоступности Redis."""
        if not self._available:
            return False
        try:
            return cast("bool", await self.client.set(key, value, ex=ex))
        except RedisConnectionError as e:
            logger.warning(
                f"Redis set({key}): connection error — {e}. Fallback: return False."
            )
            return False
        except RedisTimeoutError as e:
            logger.warning(f"Redis set({key}): timeout — {e}. Fallback: return False.")
            return False
        except RedisError as e:
            logger.error(
                f"Redis set({key}): Redis error — {e}. Fallback: return False.",
                exc_info=True,
            )
            return False

    async def delete(self, *keys: str) -> int:
        """Удаляет ключи. Возвращает 0 при недоступности Redis."""
        if not self._available:
            return 0
        try:
            return cast("int", await self.client.delete(*keys))
        except RedisConnectionError as e:
            logger.warning(
                f"Redis delete({keys}): connection error — {e}. Fallback: return 0."
            )
            return 0
        except RedisTimeoutError as e:
            logger.warning(f"Redis delete({keys}): timeout — {e}. Fallback: return 0.")
            return 0
        except RedisError as e:
            logger.error(
                f"Redis delete({keys}): Redis error — {e}. Fallback: return 0.",
                exc_info=True,
            )
            return 0

    async def exists(self, *keys: str) -> int:
        """Проверяет существование ключей. Возвращает 0 при недоступности Redis."""
        if not self._available:
            return 0
        try:
            return cast("int", await self.client.exists(*keys))
        except RedisConnectionError as e:
            logger.warning(
                f"Redis exists({keys}): connection error — {e}. Fallback: return 0."
            )
            return 0
        except RedisTimeoutError as e:
            logger.warning(f"Redis exists({keys}): timeout — {e}. Fallback: return 0.")
            return 0
        except RedisError as e:
            logger.error(
                f"Redis exists({keys}): Redis error — {e}. Fallback: return 0.",
                exc_info=True,
            )
            return 0

    async def expire(self, key: str, seconds: int) -> bool:
        """Устанавливает TTL. Возвращает False при недоступности Redis."""
        if not self._available:
            return False
        try:
            return cast("bool", await self.client.expire(key, seconds))
        except RedisConnectionError as e:
            logger.warning(
                f"Redis expire({key}, {seconds}s): connection error — {e}. → False"
            )
            return False
        except RedisTimeoutError as e:
            logger.warning(f"Redis expire({key}, {seconds}s): timeout — {e}. → False")
            return False
        except RedisError as e:
            logger.error(
                f"Redis expire({key}, {seconds}s): Redis error — {e}. → False",
                exc_info=True,
            )
            return False

    async def ttl(self, key: str) -> int:
        """Возвращает оставшееся время жизни ключа.
        Возвращает -2 (ключ не существует) при недоступности Redis.
        """
        if not self._available:
            return -2
        try:
            return cast("int", await self.client.ttl(key))
        except RedisConnectionError as e:
            logger.warning(
                f"Redis ttl({key}): connection error — {e}. Fallback: return -2."
            )
            return -2
        except RedisTimeoutError as e:
            logger.warning(f"Redis ttl({key}): timeout — {e}. Fallback: return -2.")
            return -2
        except RedisError as e:
            logger.error(
                f"Redis ttl({key}): Redis error — {e}. Fallback: return -2.",
                exc_info=True,
            )
            return -2

    async def keys(self, pattern: str) -> list[str]:
        """Возвращает список ключей. Возвращает [] при недоступности Redis."""
        if not self._available:
            return []
        try:
            return cast("list[str]", await self.client.keys(pattern))
        except RedisConnectionError as e:
            logger.warning(
                f"Redis keys({pattern}): connection error — {e}. Fallback: return []."
            )
            return []
        except RedisTimeoutError as e:
            logger.warning(
                f"Redis keys({pattern}): timeout — {e}. Fallback: return []."
            )
            return []
        except RedisError as e:
            logger.error(
                f"Redis keys({pattern}): Redis error — {e}. Fallback: return [].",
                exc_info=True,
            )
            return []

    async def incr(self, key: str) -> int:
        """Атомарно инкрементирует значение. Возвращает 0 при недоступности Redis."""
        if not self._available:
            return 0
        try:
            return cast("int", await self.client.incr(key))
        except RedisConnectionError as e:
            logger.warning(
                f"Redis incr({key}): connection error — {e}. Fallback: return 0."
            )
            return 0
        except RedisTimeoutError as e:
            logger.warning(f"Redis incr({key}): timeout — {e}. Fallback: return 0.")
            return 0
        except RedisError as e:
            logger.error(
                f"Redis incr({key}): Redis error — {e}. Fallback: return 0.",
                exc_info=True,
            )
            return 0

    async def rpush(self, key: str, *values: str) -> int:
        """Добавляет значения в список. Возвращает 0 при недоступности Redis."""
        if not self._available:
            return 0
        try:
            return await cast(Awaitable[int], self.client.rpush(key, *values))
        except RedisConnectionError as e:
            logger.warning(f"Redis rpush({key}, {values}): connection error — {e}. → 0")
            return 0
        except RedisTimeoutError as e:
            logger.warning(f"Redis rpush({key}, {values}): timeout — {e}. → 0")
            return 0
        except RedisError as e:
            logger.error(
                f"Redis rpush({key}, {values}): Redis error — {e}. → 0",
                exc_info=True,
            )
            return 0

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        """Возвращает срез списка. Возвращает [] при недоступности Redis."""
        if not self._available:
            return []
        try:
            return await cast(Awaitable[list[str]], self.client.lrange(key, start, end))
        except RedisConnectionError as e:
            logger.warning(
                f"Redis lrange({key}, {start}, {end}): connection error — {e}. → []"
            )
            return []
        except RedisTimeoutError as e:
            logger.warning(f"Redis lrange({key}, {start}, {end}): timeout — {e}. → []")
            return []
        except RedisError as e:
            logger.error(
                f"Redis lrange({key}, {start}, {end}): Redis error — {e}. → []",
                exc_info=True,
            )
            return []

    async def ltrim(self, key: str, start: int, end: int) -> bool:
        """Обрезает список. Возвращает False при недоступности Redis."""
        if not self._available:
            return False
        try:
            return bool(await cast(Awaitable[str], self.client.ltrim(key, start, end)))
        except RedisConnectionError as e:
            logger.warning(
                f"Redis ltrim({key}, {start}, {end}): connection error — {e}. → False"
            )
            return False
        except RedisTimeoutError as e:
            logger.warning(
                f"Redis ltrim({key}, {start}, {end}): timeout — {e}. → False"
            )
            return False
        except RedisError as e:
            logger.error(
                f"Redis ltrim({key}, {start}, {end}): Redis error — {e}. → False",
                exc_info=True,
            )
            return False

    async def llen(self, key: str) -> int:
        """Возвращает длину списка. Возвращает 0 при недоступности Redis."""
        if not self._available:
            return 0
        try:
            return await cast(Awaitable[int], self.client.llen(key))
        except RedisConnectionError as e:
            logger.warning(
                f"Redis llen({key}): connection error — {e}. Fallback: return 0."
            )
            return 0
        except RedisTimeoutError as e:
            logger.warning(f"Redis llen({key}): timeout — {e}. Fallback: return 0.")
            return 0
        except RedisError as e:
            logger.error(
                f"Redis llen({key}): Redis error — {e}. Fallback: return 0.",
                exc_info=True,
            )
            return 0

    async def pipeline(self) -> Any:
        """Создаёт pipeline для атомарного выполнения команд.

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
        """Закрывает все экземпляры RedisClient (по одному на event loop)."""
        for instance in cls._instances.values():
            await instance.close()
        cls._instances.clear()
        cls._locks.clear()


async def get_redis() -> RedisClient:
    """Возвращает singleton-клиент Redis (удобная функция-помощник)."""
    return await RedisClient.get_instance()
