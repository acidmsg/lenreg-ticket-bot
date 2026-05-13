"""
Admin authorization filter for aiogram.

Reusable filter that checks whether the user is in the ADMIN_IDS list.
Eliminates copy-paste admin checks in every admin-only handler.
"""

from aiogram.filters import BaseFilter
from aiogram.types import Message
from loguru import logger

from src.config import settings


class IsAdmin(BaseFilter):
    """
    Filter that passes only for admin users.

    Usage:
        @router.message(Command("status"), IsAdmin())
        async def cmd_status(message: Message, ...): ...

    The filter parses ADMIN_IDS once at init time for performance.
    """

    def __init__(self) -> None:
        self._admin_ids: set[int] = set()
        raw = settings.ADMIN_IDS
        if raw:
            for part in raw.split(","):
                stripped = part.strip()
                if stripped:
                    try:
                        self._admin_ids.add(int(stripped))
                    except ValueError:
                        logger.warning(f"Invalid ADMIN_IDS entry: {stripped!r}")

    async def __call__(self, message: Message) -> bool:
        if not message.from_user:
            return False
        return message.from_user.id in self._admin_ids
