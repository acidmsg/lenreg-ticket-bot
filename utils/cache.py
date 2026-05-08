import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional

import aiofiles
from cachetools import TTLCache

from config import settings

logger = logging.getLogger(__name__)

# TTL в 1 секунду, maxsize=1000 для защиты от переполнения
spam_cache = TTLCache(maxsize=1000, ttl=1.0)

# Единый lock для доступа к monitoring_cache.json из всех модулей
_cache_lock = asyncio.Lock()


async def load_monitoring_cache() -> Dict[str, Any]:
    """Загружает monitoring_cache.json (async, thread-safe)."""
    path = settings.CACHE_PATH
    if not os.path.exists(path):
        return {}
    try:
        async with _cache_lock:
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content) if content else {}
    except Exception as e:
        logger.error(f"Ошибка чтения кэша мониторинга: {e}")
        return {}


async def save_monitoring_cache(data: Dict[str, Any]) -> None:
    """Сохраняет monitoring_cache.json атомарно (async, thread-safe)."""
    path = settings.CACHE_PATH
    temp_path = path + ".tmp"
    try:
        async with _cache_lock:
            async with aiofiles.open(temp_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=4))
            os.replace(temp_path, path)
    except Exception as e:
        logger.error(f"Ошибка сохранения кэша мониторинга: {e}")


async def read_cache_key(key: str) -> Any:
    """Читает одно значение из кэша (возвращает None если ключ отсутствует)."""
    cache = await load_monitoring_cache()
    return cache.get(key)


async def update_cache_key(key: str, value: Any) -> None:
    """Атомарно обновляет одно значение в кэше (read-modify-write под единым lock)."""
    path = settings.CACHE_PATH
    temp_path = path + ".tmp"
    try:
        async with _cache_lock:
            # Read
            cache: Dict[str, Any] = {}
            if os.path.exists(path):
                async with aiofiles.open(path, "r", encoding="utf-8") as f:
                    content = await f.read()
                    cache = json.loads(content) if content else {}
            # Modify
            cache[key] = value
            # Write
            async with aiofiles.open(temp_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(cache, ensure_ascii=False, indent=4))
            os.replace(temp_path, path)
    except Exception as e:
        logger.error(f"Ошибка атомарного обновления кэша [{key}]: {e}")


async def swap_cache_key(key: str, new_value: Any) -> Any:
    """Atomically reads old value and writes new value if different. Returns old value.

    This avoids the TOCTOU race between separate read_cache_key + update_cache_key
    calls by holding the lock for the entire read-compare-write cycle.
    """
    path = settings.CACHE_PATH
    temp_path = path + ".tmp"
    try:
        async with _cache_lock:
            # Read
            cache: Dict[str, Any] = {}
            if os.path.exists(path):
                async with aiofiles.open(path, "r", encoding="utf-8") as f:
                    content = await f.read()
                    cache = json.loads(content) if content else {}
            old_value = cache.get(key)
            # Write only if changed
            if old_value != new_value:
                cache[key] = new_value
                async with aiofiles.open(temp_path, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(cache, ensure_ascii=False, indent=4))
                os.replace(temp_path, path)
            return old_value
    except Exception as e:
        logger.error(f"Ошибка swap кэша [{key}]: {e}")
        return None


async def delete_cache_key(key: str) -> None:
    """Атомарно удаляет ключ из кэша (read-modify-write под единым lock)."""
    path = settings.CACHE_PATH
    temp_path = path + ".tmp"
    try:
        async with _cache_lock:
            # Read
            if not os.path.exists(path):
                return
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                content = await f.read()
                cache = json.loads(content) if content else {}
            # Modify
            if key not in cache:
                return
            del cache[key]
            # Write
            async with aiofiles.open(temp_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(cache, ensure_ascii=False, indent=4))
            os.replace(temp_path, path)
    except Exception as e:
        logger.error(f"Ошибка атомарного удаления из кэша [{key}]: {e}")
