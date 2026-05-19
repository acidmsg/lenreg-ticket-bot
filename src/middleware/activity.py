"""
Activity logging middleware for aiogram.

Logs every incoming user event (message or callback) with user ID and
event details. Provides centralised audit trail without per-handler logging.
"""

from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message
from loguru import logger


class ActivityLogMiddleware(BaseMiddleware):
    """
    Inner middleware that logs user activity for audit purposes.

    Uses DEBUG level to avoid spamming production logs. Logs include:
    - user_id
    - event type (message/callback)
    - content (text or callback_data, truncated to 100 chars)
    """

    async def __call__(self, handler, event, data) -> Any:
        if isinstance(event, Message):
            uid = event.from_user.id if event.from_user else "?"
            text = (event.text or event.caption or "")[:100]
            logger.debug(f"[ACTIVITY] user={uid} msg={text!r}")
        elif isinstance(event, CallbackQuery):
            uid = event.from_user.id if event.from_user else "?"
            cb_data = (event.data or "")[:100]
            logger.debug(f"[ACTIVITY] user={uid} cb={cb_data!r}")

        return await handler(event, data)
