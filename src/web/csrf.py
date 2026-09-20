"""CSRF-защита дашборда (DASH-10).

Токен привязан к сессионной cookie: значение — HMAC от строки сессии, поэтому
чужой браузер не сможет подделать POST, даже зная путь. Проверка выполняется
для небезопасных методов на защищённых путях; Mini App остаётся в стороне —
он аутентифицируется подписью ``initData`` в собственном middleware.
"""

from __future__ import annotations

import hmac
from hashlib import sha256
from typing import Any

from src.config import settings

# Заголовок, который проставляет фронтенд, и запасное поле формы.
CSRF_HEADER = "X-CSRF-Token"
CSRF_FIELD = "csrf_token"

# Методы, которые не меняют состояние.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Пути, у которых своя схема аутентификации (Mini App) или подписанная ссылка.
CSRF_EXEMPT_PREFIXES = ("/api/user", "/api/export")


def csrf_secret() -> str:
    """Секрет для подписи токена.

    Берём ``CSRF_TOKEN`` из конфига; если он не задан, используется секрет
    сессий — лучше подписанный токен на общем секрете, чем отсутствие защиты
    (пустой ``CSRF_TOKEN`` отмечается предупреждением при старте).
    """
    from src.web.auth_session import get_session_middleware

    mw = get_session_middleware()
    session_secret = mw.secret if mw is not None else ""
    return settings.CSRF_TOKEN or session_secret


def make_csrf_token(session: str, secret: str) -> str:
    """Токен для конкретной сессии.

    Args:
        session: Значение сессионной cookie.
        secret: Секрет подписи.

    Returns:
        Шестнадцатеричная подпись (пустая строка, если считать нечего).
    """
    if not session or not secret:
        return ""
    return hmac.new(secret.encode(), session.encode(), sha256).hexdigest()


def verify_csrf_token(token: str | None, session: str, secret: str) -> bool:
    """Совпадает ли токен запроса с ожидаемым для этой сессии."""
    expected = make_csrf_token(session, secret)
    if not token or not expected:
        return False
    return hmac.compare_digest(token, expected)


async def token_from_request(request: Any) -> str | None:
    """Токен из заголовка или, для обычной формы, из её поля.

    HTML-форма не умеет ставить заголовки, поэтому поле ``csrf_token``
    тоже принимается; тело читается один раз и кешируется Starlette,
    так что обработчик ниже увидит его же.
    """
    provided = request.headers.get(CSRF_HEADER)
    if provided:
        return provided

    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" not in content_type:
        return None

    from urllib.parse import parse_qs

    body = (await request.body()).decode("utf-8", errors="replace")
    values = parse_qs(body).get(CSRF_FIELD) or []
    return values[0] if values else None


def needs_csrf(path: str, method: str) -> bool:
    """Нужна ли проверка токена для этого запроса."""
    if method.upper() in SAFE_METHODS:
        return False
    return not any(path.startswith(prefix) for prefix in CSRF_EXEMPT_PREFIXES)
