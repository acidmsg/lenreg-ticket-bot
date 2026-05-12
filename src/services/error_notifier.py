"""
Error notification service: NTFY (primary) + optional Sentry.

NTFY sends HTTP POST to a configurable topic URL.
Sentry is integrated only if SENTRY_DSN is set in config.
"""

import logging
import traceback

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


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
            )
            self._sentry_initialized = True
            logger.info("Sentry SDK initialized")
        except ImportError:
            logger.warning("Sentry SDK not installed, skipping Sentry integration")
        except Exception as e:
            logger.error(f"Failed to initialize Sentry: {e}")

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
            # Truncate to avoid huge messages
            if len(tb_str) > 2000:
                tb_str = tb_str[-2000:]

            title = f"❌ Bot Error: {context or type(error).__name__}"
            message = f"{type(error).__name__}: {error}\n\n```\n{tb_str}\n```"

            if extra:
                extra_lines = "\n".join(f"{k}: {v}" for k, v in extra.items())
                message += f"\n\n**Extra:**\n{extra_lines}"

            async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
                await client.post(
                    settings.NTFY_TOPIC_URL,
                    content=message.encode("utf-8"),
                    headers={
                        "Title": title,
                        "Priority": "urgent",
                        "Tags": "rotating_light,bot",
                    },
                )
        except Exception as e:
            logger.error(f"Failed to send NTFY notification: {e}")

    def _notify_sentry(
        self,
        error: Exception,
        context: str = "",
        extra: dict | None = None,
    ) -> None:
        """Send error to Sentry."""
        try:
            import sentry_sdk

            with sentry_sdk.push_scope() as scope:
                scope.set_tag("context", context)
                if extra:
                    for k, v in extra.items():
                        scope.set_extra(k, v)
                sentry_sdk.capture_exception(error)
        except Exception as e:
            logger.error(f"Failed to send Sentry notification: {e}")


# Singleton
error_notifier = ErrorNotifier()
