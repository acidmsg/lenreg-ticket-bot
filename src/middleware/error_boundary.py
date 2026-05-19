"""
Global error boundary middleware for aiogram.

Catches common non-fatal exceptions (MessageNotModified, MessageToDeleteNotFound)
that are currently silently swallowed in every handler, centralising error
suppression and logging.
"""

from typing import Any

from aiogram import BaseMiddleware
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNotFound,
)
from aiogram.types import CallbackQuery, Message
from loguru import logger


class ErrorBoundaryMiddleware(BaseMiddleware):
    """
    Outer middleware that wraps every handler in a try/except.

    Non-fatal Telegram errors (message not modified, message not found,
    user blocked the bot) are silently suppressed.
    All other exceptions are logged and re-raised so the dispatcher
    can handle them (or crash the polling loop if truly fatal).
    """

    async def __call__(self, handler, event, data) -> Any:
        try:
            return await handler(event, data)
        except TelegramBadRequest as e:
            # "message is not modified" — harmless, happens on fast double-clicks
            if "not modified" in str(e).lower():
                return
            # "message to delete not found" — already deleted by cleanup
            if "message to delete not found" in str(e).lower():
                return
            # "message can't be deleted for everyone" — already gone
            if "message can't be deleted" in str(e).lower():
                return
            logger.warning(f"TelegramBadRequest in handler: {e}")
        except TelegramNotFound:
            # Message/chat not found — likely deleted
            return
        except TelegramForbiddenError:
            # User blocked the bot — silently ignore
            user_info = ""
            if isinstance(event, (Message, CallbackQuery)):
                uid = event.from_user.id if event.from_user else "?"
                user_info = f" for user {uid}"
            logger.info(f"Bot blocked by user{user_info}, ignoring")
            return
        except Exception:
            # Log full traceback; let aiogram's default error handling
            # decide whether to crash (usually it won't for handler errors)
            event_info = type(event).__name__
            if isinstance(event, CallbackQuery) and event.data:
                event_info += f" data={event.data!r}"
            logger.opt(exception=True).error(
                f"Unhandled error in handler ({event_info})"
            )
            # Re-raise so dispatcher.process_update() catches it
            # and continues with the next update (aiogram default behaviour)
            raise
