"""
Error notification service: NTFY (primary) + optional Sentry.

NTFY sends HTTP POST to a configurable topic URL.
Sentry is integrated only if SENTRY_DSN is set in config.
"""

import asyncio
import traceback
from typing import Any

import aiohttp
import httpx
import sentry_sdk
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from loguru import logger

from src.config import settings


def _before_send(event: Any, hint: dict[str, Any]) -> Any | None:
    """Фильтрует несущественные ошибки перед отправкой в Sentry.

    Args:
        event: Событие Sentry.
        hint: Подсказка Sentry, содержащая информацию об исключении.

    Returns:
        Событие для отправки или None, если событие следует отбросить.
    """
    exc_info = hint.get("exc_info")
    if exc_info is not None:
        exc_type, _exc_value, _tb = exc_info
        # Игнорируем сетевые ошибки
        if issubclass(exc_type, (aiohttp.ClientError, asyncio.TimeoutError)):
            return None
        # Игнорируем системные сигналы завершения
        if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
            return None
        # Игнорируем временные ошибки Telegram API
        if issubclass(exc_type, (TelegramRetryAfter, TelegramNetworkError)):
            return None
    return event


class ErrorNotifier:
    """Centralized error notification dispatcher."""

    def __init__(self):
        self._sentry_initialized = False
        self._init_sentry()

    def _init_sentry(self):
        """Initialize Sentry SDK if DSN is configured."""
        if not settings.SENTRY_DSN:
            return
        try:
            import sentry_sdk

            sentry_sdk.init(
                dsn=settings.SENTRY_DSN,
                traces_sample_rate=0.0,  # no performance tracing for bot
                send_default_pii=True,  # capture user Telegram IDs in error context
                enable_logs=True,  # forward Python logging to Sentry
                environment=settings.ENVIRONMENT,
                before_send=_before_send,
            )
            self._sentry_initialized = True
            logger.info("Sentry SDK initialized")
        except ImportError:
            logger.warning("Sentry SDK not installed, skipping Sentry integration")
        except Exception as e:
            logger.error(f"Failed to initialize Sentry: {e}", exc_info=True)

    async def notify(
        self,
        error: Exception,
        context: str = "",
        extra: dict | None = None,
    ) -> None:
        """
        Send error notification through configured channels.
        Silently swallows its own errors to never break the caller.
        """
        if not settings.ERROR_NOTIFY_ENABLED:
            return

        # NTFY
        if settings.NTFY_TOPIC_URL:
            await self._notify_ntfy(error, context, extra)

        # Sentry
        if self._sentry_initialized and settings.SENTRY_DSN:
            self._notify_sentry(error, context, extra)

    async def _notify_ntfy(
        self,
        error: Exception,
        context: str = "",
        extra: dict | None = None,
    ) -> None:
        """Send error to NTFY topic via HTTP POST."""
        try:
            tb_str = "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            )
            # Truncate to avoid huge messages: сохраняем начало (тип + сообщение)
            if len(tb_str) > 2000:
                tb_str = tb_str[:2000]

            title = f"❌ Bot Error: {context or type(error).__name__}"
            message = f"{type(error).__name__}: {error}\n\n```\n{tb_str}\n```"

            if extra:
                extra_lines = "\n".join(f"{k}: {v}" for k, v in extra.items())
                message += f"\n\n**Extra:**\n{extra_lines}"

            # NTFY expects ASCII-safe headers, non-ASCII chars (emoji) → replace
            safe_title = title.encode("ascii", errors="replace").decode("ascii")
            safe_content = message

            async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
                await client.post(
                    settings.NTFY_TOPIC_URL,
                    content=safe_content,
                    headers={
                        "Title": safe_title,
                        "Priority": "urgent",
                        "Tags": "rotating_light,bot",
                    },
                )
        except (TimeoutError, httpx.RequestError, httpx.TimeoutException) as e:
            logger.error(f"Failed to send NTFY notification: {e}", exc_info=True)
        except Exception as e:
            # Последний fallback для неожиданных ошибок (кодировка, память и т.п.)
            logger.error(
                f"Unexpected error in NTFY notification: {e}", exc_info=True
            )

    def _notify_sentry(
        self,
        error: Exception,
        context: str = "",
        extra: dict | None = None,
    ) -> None:
        """Send error to Sentry."""
        try:
            with sentry_sdk.push_scope() as scope:
                scope.set_tag("context", context)
                if extra:
                    for k, v in extra.items():
                        scope.set_extra(k, v)
                sentry_sdk.capture_exception(error)
        except Exception as e:
            logger.error(
                f"Failed to send Sentry notification: {e}", exc_info=True
            )

    # ── Schema Change Notifications (F8) ───────────────────────────

    async def notify_schema_change(
        self,
        endpoint: str,
        diffs: list[str],
    ) -> None:
        """Отправляет алерт об изменении схемы API.

        Args:
            endpoint: Название эндпоинта (напр. 'speciality_list').
            diffs: Список строк с описанием расхождений.
        """
        if not settings.ERROR_NOTIFY_ENABLED:
            return

        # NTFY
        if settings.NTFY_TOPIC_URL:
            await self._notify_schema_change_ntfy(endpoint, diffs)

        # Sentry
        if self._sentry_initialized and settings.SENTRY_DSN:
            self._notify_schema_change_sentry(endpoint, diffs)

    async def _notify_schema_change_ntfy(
        self,
        endpoint: str,
        diffs: list[str],
    ) -> None:
        """Отправляет NTFY-уведомление об изменении схемы API."""
        try:
            title = f"API Schema Change: {endpoint}"
            message = f"Эндпоинт: {endpoint}\n\nРасхождения ({len(diffs)}):\n"
            for i, diff in enumerate(diffs, 1):
                message += f"{i}. {diff}\n"

            # Truncate до 2000 символов
            if len(message) > 2000:
                message = message[:1997] + "..."

            safe_title = title.encode("ascii", errors="replace").decode("ascii")
            safe_content = message.encode("utf-8")

            async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
                await client.post(
                    settings.NTFY_TOPIC_URL,
                    content=safe_content,
                    headers={
                        "Title": safe_title,
                        "Priority": "high",
                        "Tags": "api_schema_change,rotating_light",
                    },
                )
        except (TimeoutError, httpx.RequestError, httpx.TimeoutException) as e:
            logger.error(
                "Failed to send NTFY schema change notification: {}", e, exc_info=True
            )
        except Exception as e:
            # Последний fallback для неожиданных ошибок
            logger.error(
                "Unexpected error in NTFY schema change notification: {}",
                e,
                exc_info=True,
            )

    def _notify_schema_change_sentry(
        self,
        endpoint: str,
        diffs: list[str],
    ) -> None:
        """Отправляет Sentry-событие об изменении схемы API."""
        try:
            import sentry_sdk

            with sentry_sdk.push_scope() as scope:
                scope.set_tag("alert_type", "api_schema_change")
                scope.set_tag("endpoint", endpoint)
                scope.set_extra("endpoint", endpoint)
                scope.set_extra("diffs", diffs)
                scope.set_extra("diffs_count", len(diffs))
                sentry_sdk.capture_message(
                    f"API Schema Change: {endpoint} — {len(diffs)} расхождений",
                    level="warning",
                )
        except Exception as e:
            logger.error(
                "Failed to send Sentry schema change notification: {}",
                e,
                exc_info=True,
            )


# Singleton
error_notifier = ErrorNotifier()
