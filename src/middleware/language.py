"""
Захват языка клиента (language_code) на любом апдейте.

Язык нужен для локализации уведомлений (см. src.i18n и monitor). Ранее он
сохранялся только в /start; middleware покрывает любые входящие, включая
открытие Mini App, поэтому язык подхватывается без обязательного /start.
"""

from typing import Any

from aiogram import BaseMiddleware
from loguru import logger

from src.database.manager import DatabaseManager
from src.i18n import resolve_language


def _extract_from_user(event: Any) -> Any | None:
    """Достаёт пользователя из события.

    aiogram может передавать сюда как Update (у него НЕТ атрибута from_user),
    так и Message/CallbackQuery (у них from_user есть). Поэтому сначала пробуем
    напрямую, затем — из вложенного события Update.
    """
    user = getattr(event, "from_user", None)
    if user is not None:
        return user
    for attr in ("message", "edited_message", "callback_query", "inline_query"):
        sub = getattr(event, attr, None)
        sub_user = getattr(sub, "from_user", None) if sub is not None else None
        if sub_user is not None:
            return sub_user
    return None


class LanguageMiddleware(BaseMiddleware):
    """Outer middleware: сохраняет язык клиента из from_user.language_code.

    Пишет в БД только при изменении (кэш uid→lang в памяти процесса), чтобы не
    дёргать БД на каждом апдейте.
    """

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    async def __call__(self, handler, event, data) -> Any:
        db: DatabaseManager | None = data.get("db")
        user = _extract_from_user(event)
        if db is not None and user is not None and user.language_code:
            uid = str(user.id)
            lang = resolve_language(user.language_code)
            if self._cache.get(uid) != lang:
                try:
                    await db.set_user_language(uid, lang)
                    self._cache[uid] = lang
                except Exception as e:
                    logger.opt(exception=True).warning(
                        "Не удалось сохранить язык пользователя {}: {}", uid, e
                    )
        return await handler(event, data)
