"""Middleware проверки initData из Telegram Mini App.

Проверяет HMAC-SHA256 подпись initData, переданную в заголовке
X-Telegram-InitData. Применяется только к путям /api/user/*.

Вся HMAC-верификация делегирована в ``src.utils.helpers.verify_telegram_init_data()``,
которая является единственным источником истины для проверки initData.
"""

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.config import settings
from src.utils.helpers import verify_telegram_init_data

logger = logging.getLogger(__name__)


class TelegramInitDataMiddleware(BaseHTTPMiddleware):
    """Проверяет HMAC-SHA256 подпись initData из Telegram Mini App.

    Применяется только к путям /api/user/*. Извлекает telegram_id
    и сохраняет в request.state.telegram_id.

    Алгоритм верификации (делегирован в ``verify_telegram_init_data()``):
    1. Извлечь заголовок X-Telegram-InitData.
    2. Вызвать ``verify_telegram_init_data()`` для проверки подписи и извлечения ID.
    3. При ошибке — вернуть соответствующий статус (400/403).
    4. При успехе — сохранить telegram_id в request.state.
    """

    async def dispatch(self, request: Request, call_next):
        # Пропускаем пути, не относящиеся к Mini App API
        path = request.url.path
        if not path.startswith("/api/user"):
            logger.debug(
                "Mini App middleware: путь %s пропущен (не /api/user/*)",
                path,
            )
            return await call_next(request)

        logger.debug("Mini App middleware: проверка initData для пути %s", path)

        # --- Аутентификация управляется флагом MINI_APP_AUTH_ENABLED ---
        if not settings.MINI_APP_AUTH_ENABLED:
            logger.warning(
                "Mini App middleware: проверка initData ОТКЛЮЧЕНА "
                "(MINI_APP_AUTH_ENABLED=False). Все запросы пропускаются без проверки."
            )
            return await call_next(request)

        # --- Шаг 1: извлечение заголовка ---
        init_data_raw = request.headers.get("X-Telegram-InitData")
        if not init_data_raw:
            logger.warning("Mini App middleware: X-Telegram-InitData не передан")
            return JSONResponse(
                status_code=403,
                content={"detail": "X-Telegram-InitData header is required"},
            )

        # --- Шаг 2: делегирование верификации в helpers.verify_telegram_init_data ---
        is_valid, error_msg, telegram_id = verify_telegram_init_data(
            init_data_raw,
            settings.BOT_TOKEN,
            max_age=settings.MINI_APP_INITDATA_MAX_AGE,
        )

        if not is_valid:
            # Определяем HTTP-статус по типу ошибки
            if error_msg and (
                "формат" in error_msg.lower() or "json" in error_msg.lower()
            ):
                status_code = 400
            else:
                status_code = 403

            logger.warning(
                "Mini App middleware: верификация не пройдена — %s",
                error_msg,
            )
            return JSONResponse(
                status_code=status_code,
                content={"detail": error_msg or "initData verification failed"},
            )

        # Сохраняем telegram_id в состоянии запроса для эндпоинтов
        request.state.telegram_id = telegram_id

        logger.debug(
            "Mini App middleware: initData успешно проверена для telegram_id=%d",
            request.state.telegram_id,
        )

        return await call_next(request)
