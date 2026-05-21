"""
Loguru logging configuration for the entire application.

Provides:
- Colorful console output
- File logging with rotation (auto-cleanup old logs)
- JSON logging (optional, disabled by default)
- InterceptHandler to bridge all standard-library logging calls into Loguru
- ``sensitive_filter`` — маскирует PII, cookie, CSRF-токены в логах
"""

from __future__ import annotations

import logging
import re
import sys
import types
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from loguru import Record


#: Регулярное выражение для поиска чисел, похожих на user ID (от 5 до 15 цифр)
_RE_USER_ID = re.compile(r"\b\d{5,15}\b")
#: Регулярное выражение для поиска Cookie-строк
_RE_COOKIE = re.compile(
    r"(?i)(cookie|Cookie)\s*[=:]\s*[^\s;]+",
)
#: Регулярное выражение для поиска CSRF-токенов в теле запроса
_RE_CSRF_TOKEN = re.compile(
    r"(?i)(csrf_token|csrfmiddlewaretoken|csrftoken)\s*[=:]\s*[^\s&;]+",
)
#: Query-параметры, содержащие чувствительные данные
_SENSITIVE_QUERY_PARAMS = {"token", "api_key", "secret", "password", "auth", "session"}


def _mask_sensitive_query_params(message: str) -> str:
    """
    Маскирует значения query-параметров, имена которых
    входят в ``_SENSITIVE_QUERY_PARAMS``.

    Пример::

        ?token=abc123&foo=bar  →  ?token=***&foo=bar
    """
    def _replace_param(m: re.Match) -> str:
        name = m.group(1)
        return f"{name}=***"

    pattern = r"([?&])(" + "|".join(_SENSITIVE_QUERY_PARAMS) + r")=[^&\s]+"
    return re.sub(pattern, _replace_param, message, flags=re.IGNORECASE)


def _sensitive_filter(record: Record) -> bool:
    """
    Loguru-фильтр, маскирующий чувствительные данные в сообщениях логов.

    Маскирует:
    - User IDs (последовательности из 5+ цифр)
    - Строки Cookie целиком
    - CSRF-токены (по именам: csrf_token, csrfmiddlewaretoken, csrftoken)
    - Чувствительные query-параметры в URL (token, api_key, secret, …)
    """
    message: str = record.get("message", "")
    if not message:
        return True

    masked = message

    # 1. Маскируем Cookie-строки целиком
    masked = _RE_COOKIE.sub("Cookie=[FILTERED]", masked)

    # 2. Маскируем CSRF-токены
    masked = _RE_CSRF_TOKEN.sub(r"\1=[FILTERED]", masked)

    # 3. Маскируем чувствительные query-параметры в URL
    masked = _mask_sensitive_query_params(masked)

    # 4. Маскируем user IDs (цифровые последовательности 5+ символов).
    #    Выполняется после остальных замен, чтобы не маскировать
    #    уже заменённые значения и не задеть числа в осмысленном контексте
    #    (пороги, таймауты и т.п.), которые встречаются как отдельные токены.
    masked = _RE_USER_ID.sub("***", masked)

    record["message"] = masked
    return True


class InterceptHandler(logging.Handler):
    """
    Redirects all standard-library logging messages to Loguru.

    This ensures that third-party libraries using the standard ``logging``
    module (e.g. ``aiogram``, ``httpx``, ``aiosqlite``) appear in the same
    Loguru sink and with the same formatting as the project's own logs.
    """

    def emit(self, record: logging.LogRecord) -> None:
        # Get the corresponding Loguru level
        level: str | int
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find the caller frame
        current: types.FrameType | None = logging.currentframe()
        depth = 2
        while current is not None and depth > 0:
            current = current.f_back
            depth -= 1

        logger.opt(depth=6, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(
    *,
    log_dir: str = "logs",
    log_file: str = "error.log",
    rotation: str = "10 MB",
    retention: str = "30 days",
    json_serialize: bool = False,
    level: str = "INFO",
) -> None:
    """
    Configure Loguru sinks and install the intercept handler.

    Parameters
    ----------
    log_dir:
        Directory where log files are stored.
    log_file:
        Base name of the log file (e.g. ``error.log``).
    rotation:
        Rotate log files when they reach this size (e.g. ``"10 MB"``).
    retention:
        Keep log files for this duration (e.g. ``"30 days"``).
    json_serialize:
        If ``True``, also write a JSON-structured log file.
    level:
        Minimum log level for console output.
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Remove any default Loguru sink
    logger.remove()


    # --- Console sink (colorful, human-readable) ---
    logger.add(
        sys.stdout,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        level=level.upper(),
        colorize=True,
        filter=_sensitive_filter,
    )

    # --- File sink (plain text, with rotation) ---
    logger.add(
        log_path / log_file,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
            "{name}:{function}:{line} | {message}"
        ),
        level="DEBUG",
        rotation=rotation,
        retention=retention,
        encoding="utf-8",
        filter=_sensitive_filter,
    )

    # --- Optional JSON sink ---
    if json_serialize:
        logger.add(
            log_path / f"{Path(log_file).stem}.json",
            level="DEBUG",
            rotation=rotation,
            retention=retention,
            serialize=True,
            encoding="utf-8",
            filter=_sensitive_filter,
        )

    # --- Bridge standard ``logging`` → Loguru ---
    intercept_handler = InterceptHandler()
    logging.basicConfig(handlers=[intercept_handler], level=logging.DEBUG, force=True)

    # Suppress noisy loggers from third-party libraries
    for lib_name in (
        "aiogram",
        "httpx",
        "httpcore",
        "aiosqlite",
        "asyncio",
    ):
        lib_logger = logging.getLogger(lib_name)
        lib_logger.handlers = [intercept_handler]
        lib_logger.propagate = False

    logger.info(
        "Loguru logging initialised (level={}, file={})", level, log_path / log_file
    )
