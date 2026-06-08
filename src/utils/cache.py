"""
Модуль кэширования на основе Redis.

Заменяет старый файловый JSON-кэш (monitoring_cache.json) и in-memory TTLCache.
Все операции атомарны, с TTL-поддержкой через Redis EXPIRE.

При недоступности Redis возвращает безопасные значения по умолчанию
(graceful degradation).
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from src.utils.redis import get_redis

# Префикс для ключей monitoring-кэша в Redis
_MONITORING_KEY_PREFIX = "mon:"

# TTL для мониторинговых ключей (24 часа по умолчанию)
_MONITORING_TTL = 86400

# TTL для spam-кэша (1 секунда)
_SPAM_TTL = 1


# --- Spam-защита (замена TTLCache) ---


async def is_spam(key: str) -> bool:
    """
    Проверяет, не было ли уже обращения с таким ключом за последнюю секунду.

    Возвращает True если ключ уже существует (спам), False если новое обращение.
    Атомарно: SET NX + EXPIRE в одной операции.

    При недоступности Redis возвращает False (пропускает запрос).
    """
    redis = await get_redis()
    if not redis.is_available:
        return False
    # SET key 1 NX EX 1: True = ключ создан (не спам), None = уже был (спам)
    created = await redis.client.set(f"spam:{key}", "1", ex=_SPAM_TTL, nx=True)
    return created is None


# --- Мониторинговый кэш (замена файлового JSON) ---


def _mon_key(key: str) -> str:
    """Формирует полный Redis-ключ с префиксом monitoring."""
    return f"{_MONITORING_KEY_PREFIX}{key}"


async def get_cache_key(key: str) -> Any | None:
    """
    Читает значение из мониторингового кэша Redis.

    Возвращает десериализованное значение (обычно list[str] — слоты,
    или строка ``"NONE"``, или словарь) либо None, если ключ не найден
    или Redis недоступен.
    """
    redis = await get_redis()
    if not redis.is_available:
        return None
    rkey = _mon_key(key)
    try:
        raw = await redis.client.get(rkey)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.error(f"Ошибка чтения кэша [{key}]: {e}")
        return None


async def swap_cache_key(key: str, new_value: Any) -> Any:
    """
    Атомарно читает старое значение и записывает новое, если отличается.

    Использует GETSET для атомарного read+write в одной команде Redis.
    Возвращает старое значение (десериализованное из JSON) или None при ошибке
    либо недоступности Redis.
    """
    redis = await get_redis()
    if not redis.is_available:
        return None
    rkey = _mon_key(key)
    try:
        new_json = json.dumps(new_value, ensure_ascii=False)
        old_json = await redis.client.getset(rkey, new_json)
        # Устанавливаем TTL на ключ
        await redis.client.expire(rkey, _MONITORING_TTL)
        if old_json is not None:
            return json.loads(old_json)
        return None
    except Exception as e:
        logger.error(f"Ошибка swap кэша [{key}]: {e}")
        return None


async def delete_cache_keys_by_prefix(prefix: str) -> int:
    """
    Удаляет все мониторинговые ключи, начинающиеся с prefix.

    Использует SCAN для безопасного перебора ключей (без блокировки Redis).
    Возвращает количество удалённых ключей.
    При недоступности Redis возвращает 0.
    """
    redis = await get_redis()
    if not redis.is_available:
        return 0
    pattern = f"{_MONITORING_KEY_PREFIX}{prefix}*"
    deleted = 0
    try:
        # Используем SCAN вместо KEYS для безопасного перебора
        cursor = 0
        while True:
            cursor, keys = await redis.client.scan(
                cursor=cursor, match=pattern, count=100
            )
            if keys:
                deleted += await redis.client.delete(*keys)
            if cursor == 0:
                break
        return deleted
    except Exception as e:
        logger.error(f"Ошибка удаления ключей по префиксу [{prefix}]: {e}")
        return 0
