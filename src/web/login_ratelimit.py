"""Ограничение перебора пароля дашборда (DASH-10).

Счётчик неудачных попыток ведётся по адресу клиента в памяти процесса:
после ``MAX_ATTEMPTS`` неудач вход блокируется на ``LOCKOUT_SECONDS``.
Успешный вход сбрасывает счётчик. Рестарт гейтвея очищает состояние —
это ограничение перебора, а не хранилище блокировок.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

# Порог и длительности подобраны для ручного входа администратора.
MAX_ATTEMPTS = 5
WINDOW_SECONDS = 900
LOCKOUT_SECONDS = 900


# Потолок числа записей: словарь живёт в памяти процесса.
MAX_BUCKETS = 1000


@dataclass
class _Bucket:
    """Неудачные попытки конкретного клиента."""

    failures: int = 0
    first_attempt: float = 0.0
    locked_until: float = 0.0
    lock_count: int = 0
    last_seen: float = 0.0


@dataclass
class LoginRateLimiter:
    """Памятный лимитер попыток входа по адресу клиента."""

    max_attempts: int = MAX_ATTEMPTS
    window_seconds: int = WINDOW_SECONDS
    lockout_seconds: int = LOCKOUT_SECONDS
    _buckets: dict[str, _Bucket] = field(default_factory=dict)

    def _bucket(self, client: str) -> _Bucket:
        bucket = self._buckets.get(client)
        if bucket is None:
            bucket = _Bucket()
            self._buckets[client] = bucket
        return bucket

    def _prune(self, now: float) -> None:
        """Убирает записи клиентов, о которых давно ничего не слышно.

        Без уборки словарь растёт вместе с числом уникальных адресов, а он
        живёт в памяти процесса.
        """
        if len(self._buckets) <= MAX_BUCKETS:
            return
        ttl = self.window_seconds + self.lockout_seconds * 4
        stale = [
            client
            for client, bucket in self._buckets.items()
            if now - bucket.last_seen > ttl and bucket.locked_until <= now
        ]
        for client in stale:
            self._buckets.pop(client, None)

    def lockout_left(self, client: str, now: float | None = None) -> int:
        """Сколько секунд осталось до конца блокировки (0 — вход разрешён)."""
        moment = time.monotonic() if now is None else now
        bucket = self._bucket(client)
        bucket.last_seen = moment
        self._prune(moment)
        if bucket.locked_until <= moment:
            return 0
        return int(bucket.locked_until - moment) + 1

    def record_failure(self, client: str, now: float | None = None) -> int:
        """Регистрирует неудачную попытку.

        Returns:
            Сколько секунд блокировки назначено (0 — попытки ещё есть).
        """
        moment = time.monotonic() if now is None else now
        bucket = self._bucket(client)
        bucket.last_seen = moment
        self._prune(moment)

        window_expired = moment - bucket.first_attempt > self.window_seconds
        if bucket.first_attempt == 0 or window_expired:
            bucket.failures = 0
            bucket.first_attempt = moment

        bucket.failures += 1
        if bucket.failures < self.max_attempts:
            return 0

        # Каждая новая серия неудач удлиняет блокировку, но не бесконечно.
        bucket.lock_count += 1
        multiplier = min(bucket.lock_count, 4)
        bucket.locked_until = moment + self.lockout_seconds * multiplier
        bucket.failures = 0
        bucket.first_attempt = 0
        return int(bucket.locked_until - moment)

    def reset(self, client: str) -> None:
        """Сбрасывает счётчик после успешного входа."""
        self._buckets.pop(client, None)


# Лимитер уровня приложения: веб-слой создаёт один экземпляр.
login_limiter = LoginRateLimiter()


def client_address(request: object) -> str:
    """Адрес клиента для учёта попыток.

    ``X-Forwarded-For`` учитывается только при явно включённом доверии к
    прокси: иначе клиент подставил бы в заголовок любой адрес и обошёл
    ограничение. Пустое значение заголовка тоже уводит на адрес соединения.
    """
    from src.config import settings

    headers = getattr(request, "headers", {})
    if headers and getattr(settings, "WEB_TRUST_FORWARDED_FOR", False):
        forwarded = headers.get("x-forwarded-for")
        if forwarded:
            first = str(forwarded).split(",")[0].strip()
            if first:
                return first

    client = getattr(request, "client", None)
    return getattr(client, "host", "") or "unknown"
