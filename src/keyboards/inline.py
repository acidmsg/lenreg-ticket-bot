"""Инлайн-клавиатуры бота: точка входа в приложение и уведомления.

После среза интерфейса клавиатуры бота несут единственную функцию — открыть
Mini App. Кнопки навигации, выбора пациентов и записи удалены: эти сценарии
полностью живут в приложении.
"""

from dataclasses import dataclass

from aiogram.types import InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.config import settings
from src.i18n import _
from src.services.screen_render import RenderedScreen
from src.utils.bot_identity import get_bot_username

# Жёсткий предел кнопок экрана чата: схема S2 использует одну контекстную
# кнопку и одну кнопку приложения. Больше превращает сводку в список (дизайн §10.2).
SCREEN_KEYBOARD_LIMIT = 3


@dataclass(frozen=True, slots=True)
class _ContextButton:
    """Контекстная кнопка S2: подпись и payload deep-link'а."""

    text: str
    startapp: str


def _mini_app_available() -> bool:
    """Mini App включён и настроен — значит, кнопку входа можно собрать."""
    return bool(settings.MINI_APP_ENABLED and settings.MINI_APP_URL)


def _add_open_app_button(
    builder: InlineKeyboardBuilder,
    startapp: str = "",
    text: str | None = None,
) -> None:
    """Добавляет кнопку «Открыть в приложении».

    С payload (уведомления) — deep-link ``https://t.me/<bot>?startapp=<payload>``:
    Telegram открывает Mini App сразу на нужном экране. Без payload (точка входа
    ``/start``) — web_app-кнопка с ``MINI_APP_URL``: голый ``https://t.me/<bot>``
    открывает чат с ботом, а не приложение.

    Args:
        builder: Строитель клавиатуры, в который добавляется кнопка.
        startapp: Payload deep-link'а (например, ``slots_<p_id>_<d_id>``).
        text: Подпись кнопки; ``None`` — стандартная подпись уведомлений.
    """
    label = text or _("btn-open-mini-app")
    bot_username = get_bot_username()
    if startapp and bot_username:
        builder.button(
            text=label,
            url=f"https://t.me/{bot_username}?startapp={startapp}",
        )
    else:
        builder.button(
            text=label,
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


def _context_button(rendered: RenderedScreen) -> _ContextButton | None:
    """Контекстная кнопка S2 по состоянию экрана.

    Подписи различаются парой «глагол + объект», поэтому две кнопки экрана
    никогда не выглядят одинаково. Используются только те значения
    ``startapp``, которые понимает Mini App: ``patients``, ``add``,
    ``bookings`` и ``slots_<p_id>_<d_id>``.
    """
    if rendered.is_new_user:
        return _ContextButton(str(_("btn-screen-add-patient")), "patients")
    if not rendered.has_monitoring:
        return _ContextButton(str(_("btn-screen-add-doctor")), "add")
    if rendered.pair_for_deeplink is not None:
        p_id, d_id = rendered.pair_for_deeplink
        label = _("btn-screen-slots").format(doctor=rendered.pair_doctor_name)
        return _ContextButton(str(label), f"slots_{p_id}_{d_id}")
    return _ContextButton(str(_("btn-screen-bookings")), "bookings")


def get_screen_keyboard(rendered: RenderedScreen) -> InlineKeyboardMarkup | None:
    """Клавиатура единого экрана чата по схеме S2 (дизайн §10.2).

    Экран несёт не более двух кнопок: контекстную (ведёт к тому, что важнее
    прямо сейчас) и постоянную «Открыть приложение» на главный экран Mini App.
    Deep-link к паре допускается только один — это устраняет «три одинаковые
    кнопки» прежней схемы.

    Args:
        rendered: Результат рендера экрана: состояние и пара для deep-link.

    Returns:
        InlineKeyboardMarkup с одной-двумя кнопками; ``None``, если Mini App
        выключен или URL не задан (пустую клавиатуру Telegram не принимает).
    """
    if not _mini_app_available():
        return None
    builder = InlineKeyboardBuilder()
    action = _context_button(rendered)
    if action is None or not get_bot_username():
        # Без username deep-link не собрать: остаётся единственная кнопка
        # входа — две кнопки с одинаковой подписью запрещены схемой S2.
        _add_open_app_button(builder, text=_("btn-screen-open-app"))
    else:
        builder.button(
            text=action.text,
            url=f"https://t.me/{get_bot_username()}?startapp={action.startapp}",
        )
        builder.button(
            text=_("btn-screen-open-app"),
            web_app=WebAppInfo(url=settings.MINI_APP_URL),
        )
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
