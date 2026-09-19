"""Подписанные ссылки на экспорт записи (Mini App).

Кнопка «Сохранить» должна отдавать файл на устройство. Скачивание через
``fetch`` + blob в WebView Telegram не срабатывает, а открыть обычную ссылку
нельзя: путь ``/api/user/*`` закрыт проверкой initData, а заголовок к ссылке
не приложить. Поэтому клиент сначала запрашивает короткоживущую подписанную
ссылку (``GET /api/user/bookings/{id}/export-link``), а файл отдаёт публичный
эндпоинт ``/api/export/bookings/{id}`` — он проверяет подпись и срок годности.

Ключ подписи — производная от токена бота, отдельный секрет не нужен.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode

#: Форматы, которые умеет отдавать экспорт.
EXPORT_FORMATS: tuple[str, ...] = ("png", "pdf", "ics")

#: Время жизни ссылки (секунды). Файл нужен сразу после нажатия кнопки.
EXPORT_LINK_TTL_SECONDS = 600


def _signing_secret(bot_token: str) -> bytes:
    """Возвращает ключ подписи, выведенный из токена бота."""
    return hashlib.sha256(f"export-link:{bot_token}".encode()).digest()


def _payload(booking_id: str, fmt: str, uid: str, exp: int) -> str:
    """Собирает подписываемую строку."""
    return f"{booking_id}|{fmt}|{uid}|{exp}"


def sign_export(
    booking_id: str,
    fmt: str,
    uid: str,
    *,
    bot_token: str,
    ttl: int = EXPORT_LINK_TTL_SECONDS,
    now: float | None = None,
) -> str:
    """Возвращает query-строку с параметрами и подписью для скачивания файла.

    Args:
        booking_id: Идентификатор записи.
        fmt: Формат файла (``png``, ``pdf``, ``ics``).
        uid: Telegram ID владельца записи.
        bot_token: Токен бота — источник ключа подписи.
        ttl: Время жизни ссылки в секундах.
        now: Момент выпуска (для тестов), по умолчанию — текущее время.

    Returns:
        Query-строка вида ``format=png&uid=1&exp=…&sig=…``.
    """
    issued_at = time.time() if now is None else now
    exp = int(issued_at + ttl)
    signature = hmac.new(
        _signing_secret(bot_token),
        _payload(booking_id, fmt, uid, exp).encode(),
        hashlib.sha256,
    ).hexdigest()
    return urlencode({"format": fmt, "uid": uid, "exp": exp, "sig": signature})


def verify_export(
    booking_id: str,
    fmt: str,
    uid: str,
    exp: int,
    sig: str,
    *,
    bot_token: str,
    now: float | None = None,
) -> bool:
    """Проверяет подпись и срок годности ссылки на скачивание.

    Args:
        booking_id: Идентификатор записи.
        fmt: Формат файла.
        uid: Telegram ID владельца из ссылки.
        exp: Момент истечения ссылки (unix-время).
        sig: Подпись из ссылки.
        bot_token: Токен бота — источник ключа подписи.
        now: Текущий момент (для тестов).

    Returns:
        ``True``, если ссылка подлинная и не истекла.
    """
    if fmt not in EXPORT_FORMATS:
        return False
    current = time.time() if now is None else now
    if exp < current:
        return False
    expected = hmac.new(
        _signing_secret(bot_token),
        _payload(booking_id, fmt, uid, exp).encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(sig, expected)
