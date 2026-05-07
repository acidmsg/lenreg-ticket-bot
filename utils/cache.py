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
            async with aiofiles.open(path, 'r', encoding='utf-8') as f:
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
            async with aiofiles.open(temp_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=4))
            os.replace(temp_path, path)
    except Exception as e:
        logger.error(f"Ошибка сохранения кэша мониторинга: {e}")


async def update_cache_key(key: str, value: Any) -> None:
    """Обновляет одно значение в кэше."""
    cache = await load_monitoring_cache()
    cache[key] = value
    await save_monitoring_cache(cache)


async def delete_cache_key(key: str) -> None:
    """Удаляет ключ из кэша."""
    cache = await load_monitoring_cache()
    if key in cache:
        del cache[key]
        await save_monitoring_cache(cache)
