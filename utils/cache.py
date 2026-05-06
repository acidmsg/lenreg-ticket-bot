from cachetools import TTLCache

# TTL в 1 секунду, maxsize=1000 для защиты от переполнения
spam_cache = TTLCache(maxsize=1000, ttl=1.0)
