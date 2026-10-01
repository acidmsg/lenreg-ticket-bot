"""Инлайн-клавиатуры бота: точка входа в приложение и уведомления.

После среза интерфейса клавиатуры бота несут единственную функцию — открыть
Mini App. Кнопки навигации, выбора пациентов и записи удалены: эти сценарии
полностью живут в приложении.
"""

from aiogram.types import InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.config import settings
from src.i18n import _
from src.utils.bot_identity import get_bot_username


def _mini_app_available() -> bool:
    """Mini App включён и настроен — значит, кнопку входа можно собрать."""
    return bool(settings.MINI_APP_ENABLED and settings.MINI_APP_URL)


def _add_open_app_button(builder: InlineKeyboardBuilder, startapp: str = "") -> None:
    """Добавляет кнопку «Открыть в приложении».

    С payload (уведомления) — deep-link ``https://t.me/<bot>?startapp=<payload>``:
    Telegram открывает Mini App сразу на нужном экране. Без payload (точка входа
    ``/start``) — web_app-кнопка с ``MINI_APP_URL``: голый ``https://t.me/<bot>``
    открывает чат с ботом, а не приложение.

    Args:
        builder: Строитель клавиатуры, в который добавляется кнопка.
        startapp: Payload deep-link'а (например, ``slots_<p_id>_<d_id>``).
    """
    bot_username = get_bot_username()
    if startapp and bot_username:
        builder.button(
            text=_("btn-open-mini-app"),
            url=f"https://t.me/{bot_username}?startapp={startapp}",
        )
    else:
        builder.button(
            text=_("btn-open-mini-app"),
            web_app=WebAppInfo(url=settings.MINI_APP_URL),
        )


def get_notification_keyboard(p_id: str, d_id: str) -> InlineKeyboardMarkup | None:
    """Инлайн-клавиатура уведомления о свободных номерках.

    Единственная кнопка — «Открыть в приложении», ведёт на экран номерков
    конкретного врача.

    Args:
        p_id: Идентификатор пациента.
        d_id: Идентификатор врача.

    Returns:
        InlineKeyboardMarkup с одной кнопкой либо ``None``, если Mini App
        выключен: пустую клавиатуру Telegram не принимает.
    """
    if not _mini_app_available():
        return None
    builder = InlineKeyboardBuilder()
    _add_open_app_button(builder, startapp=f"slots_{p_id}_{d_id}")
    builder.adjust(1)
    return builder.as_markup()


def get_app_entry_keyboard() -> InlineKeyboardMarkup | None:
    """Клавиатура точки входа в приложение для ``/start``.

    Returns:
        InlineKeyboardMarkup с одной кнопкой либо ``None``, если Mini App
        выключен.
    """
    if not _mini_app_available():
        return None
    builder = InlineKeyboardBuilder()
    _add_open_app_button(builder)
    builder.adjust(1)
    return builder.as_markup()
