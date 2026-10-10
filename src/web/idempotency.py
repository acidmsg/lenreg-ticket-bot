"""Идемпотентность записи: повтор с тем же ключом отдаёт сохранённый ответ.

Хранилище — в памяти процесса с TTL: приложение живёт одним event loop'ом
(бот + веб), поэтому этого достаточно. Рестарт очищает кэш, что безопасно —
повтор просто пройдёт обычным путём. Кэшируются только терминальные ответы;
busy, 502 и 504 не сохраняются (исход ещё не определён).
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

#: Время жизни сохранённого ответа (секунды).
TTL_SECONDS = 600

#: (uid, idempotency_key) -> (expires_at, params_hash, status_code, body)
_store: dict[tuple[str, str], tuple[float, str, int, Any]] = {}


def params_hash(payload: dict[str, Any]) -> str:
    """Стабильный хеш параметров запроса (для обнаружения подмены)."""
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def get(uid: str, key: str) -> tuple[str, int, Any] | None:
    """Возвращает (params_hash, status_code, body) или None."""
    entry = _store.get((uid, key))
    if entry is None:
        return None
    expires_at, phash, status, body = entry
    if time.time() > expires_at:
        _store.pop((uid, key), None)
        return None
    return phash, status, body


def put(uid: str, key: str, phash: str, status: int, body: Any) -> None:
    """Сохраняет терминальный ответ для пары (uid, key)."""
    _store[(uid, key)] = (time.time() + TTL_SECONDS, phash, status, body)


def clear() -> None:
    """Очищает хранилище (для тестов)."""
    _store.clear()
