"""Middleware проверки initData из Telegram Mini App.

Проверяет HMAC-SHA256 подпись initData, переданную в заголовке
X-Telegram-InitData. Применяется только к путям /api/user/*.
"""

import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qs

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.config import settings

logger = logging.getLogger(__name__)

# Сигнатура — HMAC-SHA256("WebAppData", BOT_TOKEN), используемая как ключ
# для вычисления хеша data_check_string.
_WEB_APP_DATA_KEY = b"WebAppData"


class TelegramInitDataMiddleware(BaseHTTPMiddleware):
    """Проверяет HMAC-SHA256 подпись initData из Telegram Mini App.

    Применяется только к путям /api/user/*. Извлекает telegram_id
    и сохраняет в request.state.telegram_id.

    Алгоритм верификации:
    1. Извлечь заголовок X-Telegram-InitData.
    2. Распарсить initData как application/x-www-form-urlencoded.
    3. Извлечь поле hash (контрольная сумма).
    4. Отсортировать все поля, кроме hash, по алфавиту.
    5. Сформировать data_check_string: key1=value1\\nkey2=value2\\n...
    6. Вычислить secret_key = HMAC-SHA256("WebAppData", BOT_TOKEN).
    7. Вычислить computed_hash = HMAC-SHA256(data_check_string, secret_key).
    8. Сравнить computed_hash (hex) с hash. Не совпадают → 403.
    9. Проверить auth_date (не старше MINI_APP_INITDATA_MAX_AGE).
    10. Извлечь user.id → telegram_id из JSON-поля user.
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

        # --- Dev-режим: bypass при ENVIRONMENT=development ---
        if settings.ENVIRONMENT == "development" and not request.headers.get(
            "X-Telegram-InitData"
        ):
            logger.warning(
                "Mini App middleware: bypass в dev-режиме — заголовок "
                "X-Telegram-InitData отсутствует. Запрос пропущен без проверки."
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

        # --- Шаг 2: парсинг initData ---
        try:
            parsed = parse_qs(init_data_raw, keep_blank_values=True)
        except Exception:
            logger.exception("Mini App middleware: ошибка парсинга initData")
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid initData format"},
            )

        # Приводим значения к плоскому словарю (parse_qs возвращает списки)
        fields: dict[str, str] = {
            key: value[0] if value else "" for key, value in parsed.items()
        }

        # --- Шаг 3: извлечение hash ---
        received_hash = fields.pop("hash", None)
        if not received_hash:
            logger.warning("Mini App middleware: поле hash отсутствует в initData")
            return JSONResponse(
                status_code=403,
                content={"detail": "Missing hash in initData"},
            )

        # --- Шаг 4-5: формирование data_check_string ---
        # Сортируем оставшиеся поля по алфавиту ключей
        sorted_fields = sorted(fields.items(), key=lambda item: item[0])
        data_check_string = "\n".join(f"{key}={value}" for key, value in sorted_fields)

        # --- Шаг 6-7: вычисление HMAC-SHA256 подписи ---
        secret_key = hmac.new(
            _WEB_APP_DATA_KEY,
            settings.BOT_TOKEN.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        computed_hash = hmac.new(
            secret_key,
            data_check_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        # --- Шаг 8: сравнение хешей ---
        if not hmac.compare_digest(computed_hash, received_hash):
            logger.warning(
                "Mini App middleware: неверная подпись initData. "
                "Ожидался hash=%s, получен hash=%s",
                computed_hash,
                received_hash,
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid initData signature"},
            )

        # --- Шаг 9: проверка auth_date ---
        auth_date_str = fields.get("auth_date", "0")
        try:
            auth_date = int(auth_date_str)
        except (ValueError, TypeError):
            logger.warning(
                "Mini App middleware: некорректное значение auth_date=%s",
                auth_date_str,
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid auth_date in initData"},
            )

        max_age = settings.MINI_APP_INITDATA_MAX_AGE
        now = int(time.time())
        if now - auth_date > max_age:
            logger.warning(
                "Mini App middleware: initData просрочена. "
                "auth_date=%d, now=%d, max_age=%d",
                auth_date,
                now,
                max_age,
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "initData has expired"},
            )
        if auth_date > now:
            logger.warning(
                "Mini App middleware: auth_date из будущего=%d, now=%d",
                auth_date,
                now,
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "auth_date is in the future"},
            )

        # --- Шаг 10: извлечение telegram_id из JSON-поля user ---
        user_json = fields.get("user", "")
        if not user_json:
            logger.warning("Mini App middleware: поле user отсутствует в initData")
            return JSONResponse(
                status_code=403,
                content={"detail": "Missing user field in initData"},
            )

        try:
            user_data = json.loads(user_json)
        except json.JSONDecodeError:
            logger.exception("Mini App middleware: ошибка разбора JSON поля user")
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid JSON in user field"},
            )

        telegram_id = user_data.get("id")
        if telegram_id is None:
            logger.warning("Mini App middleware: поле user.id отсутствует")
            return JSONResponse(
                status_code=403,
                content={"detail": "Missing user.id in initData"},
            )

        # Сохраняем telegram_id в состоянии запроса для эндпоинтов
        request.state.telegram_id = int(telegram_id)

        logger.debug(
            "Mini App middleware: initData успешно проверена для telegram_id=%d",
            request.state.telegram_id,
        )

        return await call_next(request)
