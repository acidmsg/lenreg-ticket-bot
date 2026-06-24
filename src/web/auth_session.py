"""
Session-based аутентификация дашборда (как в x-ui).

Хранит учётные данные в Settings (из .env / БД).
Сессия — подписанный HMAC cookie: username|expiry|signature.
"""

import hashlib
import hmac
import time
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request, status
from fastapi.responses import RedirectResponse, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

# Пути, доступные без аутентификации
_PUBLIC_PATHS = (
    "/login",
    "/api/login",
    "/api/logout",
    "/app",
    "/static",
    "/api/user",
    "/favicon.ico",
)

# Время жизни сессии (8 часов)
SESSION_TTL = 8 * 3600

# Имя cookie
COOKIE_NAME = "dashboard_session"


def _is_public_path(path: str) -> bool:
    """Возвращает True, если путь не требует аутентификации."""
    return any(
        path == p or path.startswith(p + "/") or path.startswith(p)
        for p in _PUBLIC_PATHS
    )


def _make_session(username: str, secret: str) -> str:
    """Создаёт подписанную сессионную строку: username|expiry|signature."""
    expiry = int(time.time()) + SESSION_TTL
    payload = f"{username}|{expiry}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}|{sig}"


def _verify_session(session: str, secret: str) -> str | None:
    """
    Проверяет сессионную строку.
    Возвращает username если валидна, None если нет.
    """
    try:
        parts = session.split("|")
        if len(parts) != 3:
            return None
        username, expiry_str, sig = parts
        expiry = int(expiry_str)
        if time.time() > expiry:
            return None
        payload = f"{username}|{expiry}"
        expected_sig = hmac.new(
            secret.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        return username
    except (ValueError, IndexError):
        return None


def hash_password(password: str) -> str:
    """Хеширует пароль через PBKDF2-SHA256."""
    salt = b"lenreg_dashboard_salt_v1"
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)
    return dk.hex()


class SessionAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware для проверки сессионного cookie на защищённых путях дашборда.

    Публичные пути (/login, /app/, /static/, /api/user/) пропускаются без проверки.
    Остальные пути требуют валидной сессии — иначе редирект на /login.
    """

    def __init__(
        self,
        app: "Any",
        username: str = "",
        password_hash: str = "",
        secret: str = "",
    ):
        super().__init__(app)
        self._username = username
        self._password_hash = password_hash
        self._secret = secret
        self._enabled = bool(username and password_hash and secret)
        if self._enabled:
            logger.info(
                "SessionAuthMiddleware: включен (пользователь: {})",
                username,
            )
        else:
            logger.info("SessionAuthMiddleware: отключен (не заданы учётные данные)")
        # Авторегистрация в глобальном экземпляре для доступа из роутеров
        set_session_middleware(self)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def username(self) -> str:
        return self._username

    @property
    def password_hash(self) -> str:
        return self._password_hash

    @property
    def secret(self) -> str:
        return self._secret

    def update_credentials(self, username: str, password_hash: str) -> None:
        """Обновляет учётные данные (после смены логина/пароля)."""
        self._username = username
        self._password_hash = password_hash
        self._enabled = True
        logger.info(
            "SessionAuthMiddleware: учётные данные обновлены (пользователь: {})",
            username,
        )

    def validate_credentials(self, username: str, password: str) -> bool:
        """Проверяет логин и пароль."""
        if not self._enabled:
            return False
        if username != self._username:
            return False
        return hmac.compare_digest(hash_password(password), self._password_hash)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Публичные пути — пропускаем без проверки
        if _is_public_path(request.url.path):
            return await call_next(request)

        # Если аутентификация отключена — пропускаем
        if not self._enabled:
            return await call_next(request)

        # Проверяем сессионный cookie
        session = request.cookies.get(COOKIE_NAME)
        if not session:
            return self._redirect_to_login(request)

        username = _verify_session(session, self._secret)
        if username is None:
            return self._redirect_to_login(request)

        # Сохраняем username в request.state для использования в шаблонах
        request.state.dashboard_user = username
        return await call_next(request)

    def _redirect_to_login(self, request: Request) -> RedirectResponse:
        """Редирект на страницу входа с сохранением исходного URL."""
        login_url = f"/login?next={request.url.path}"
        return RedirectResponse(url=login_url, status_code=status.HTTP_302_FOUND)

    def make_session_cookie(self, username: str) -> str:
        """Создаёт значение сессионного cookie."""
        return _make_session(username, self._secret)


# Глобальный экземпляр middleware (инициализируется в app.py)
_session_middleware: "SessionAuthMiddleware | None" = None


def get_session_middleware() -> "SessionAuthMiddleware | None":
    """Возвращает глобальный экземпляр SessionAuthMiddleware."""
    return _session_middleware


def set_session_middleware(mw: "SessionAuthMiddleware") -> None:
    """Устанавливает глобальный экземпляр SessionAuthMiddleware."""
    global _session_middleware
    _session_middleware = mw
