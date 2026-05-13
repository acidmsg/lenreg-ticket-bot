"""
User data preload middleware for aiogram.

Loads user_data from the database once per update and injects it into
data["user_data"], eliminating repeated db.get_user_data() calls in handlers.
"""

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message
from loguru import logger

from src.database.manager import DatabaseManager


class UserDataPreloadMiddleware(BaseMiddleware):
    """
    Outer middleware that preloads user_data for every Message and CallbackQuery.

    The loaded dict is placed into data["user_data"] and is available
    to all downstream handlers and filters. Handlers that modify user_data
    must write changes back via db.update_user().

    Falls back to an empty dict if the user is unknown or db is unavailable.
    """

    async def __call__(self, handler, event, data):
        db: DatabaseManager | None = data.get("db")
        uid: str | None = None

        if isinstance(event, Message):
            uid = str(event.from_user.id) if event.from_user else None
        elif isinstance(event, CallbackQuery):
            uid = str(event.from_user.id) if event.from_user else None

        if uid and db:
            try:
                data["user_data"] = await db.get_user_data(uid)
            except Exception:
                logger.opt(exception=True).warning(
                    f"UserDataPreload: failed to load data for {uid}"
                )
                data["user_data"] = {}
        else:
            data["user_data"] = {}

        return await handler(event, data)
