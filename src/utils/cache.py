import asyncio
import json
import logging
import os
from typing import Any

import aiofiles
from cachetools import TTLCache

from src.config import settings

logger = logging.getLogger(__name__)

# TTL в 1 секунду, maxsize=1000 для защиты от переполнения
spam_cache: TTLCache = TTLCache(maxsize=1000, ttl=1.0)

# Единый lock для доступа к monitoring_cache.json из всех модулей
_cache_lock = asyncio.Lock()


async def swap_cache_key(key: str, new_value: Any) -> Any:
    """Atomically reads old value and writes new value if different. Returns old value.

    This avoids the TOCTOU race between separate read + write
    calls by holding the lock for the entire read-compare-write cycle.
    """
    path = settings.CACHE_PATH
    temp_path = path + ".tmp"
    try:
        async with _cache_lock:
            cache: dict[str, Any] = {}
            if os.path.exists(path):  # noqa: ASYNC240
                async with aiofiles.open(path, "r", encoding="utf-8") as f:
                    content = await f.read()
                    cache = json.loads(content) if content else {}
            old_value = cache.get(key)
            if old_value != new_value:
                cache[key] = new_value
                async with aiofiles.open(temp_path, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(cache, ensure_ascii=False, indent=4))
                os.replace(temp_path, path)
            return old_value
    except Exception as e:
        logger.error(f"Ошибка swap кэша [{key}]: {e}")
        return None


async def delete_cache_keys_by_prefix(prefix: str) -> int:
    """Удаляет все ключи, начинающиеся с prefix. Возвращает количество удалённых."""
    path = settings.CACHE_PATH
    temp_path = path + ".tmp"
    deleted = 0
    try:
        async with _cache_lock:
            if not os.path.exists(path):  # noqa: ASYNC240
                return 0
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                content = await f.read()
                cache = json.loads(content) if content else {}
            keys_to_delete = [k for k in cache if k.startswith(prefix)]
            for k in keys_to_delete:
                del cache[k]
                deleted += 1
            if deleted:
                async with aiofiles.open(temp_path, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(cache, ensure_ascii=False, indent=4))
                os.replace(temp_path, path)
        return deleted
    except Exception as e:
        logger.error(f"Ошибка удаления ключей по префиксу [{prefix}]: {e}")
        return 0
