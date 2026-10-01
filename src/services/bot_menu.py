"""Меню команд и кнопка меню чата — задаются из кода (CUT-1).

Источник истины для меню Telegram — код, а не BotFather: при старте бот
идемпотентно перезаписывает и список команд, и кнопку меню чата
(``setMyCommands`` / ``setChatMenuButton``). Так меню всегда соответствует
коду и не расходится с ним.

Состав меню:

- всем — ``/start`` («Открыть приложение»);
- админам (``BotCommandScopeChat``) — ``/start`` и ``/status``;
- кнопка меню чата — Web App с ``MINI_APP_URL`` (текст «app»).

Мёртвая команда ``/stop_all`` и удаляемый ``/export`` в меню не попадают:
они не описаны здесь, а слот меню перезаписывается этим вызовом.
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    MenuButtonWebApp,
    WebAppInfo,
)
from loguru import logger

from src.config import settings

# Команды меню. Описания короткие — лимит Bot API 256 символов.
START_COMMAND = BotCommand(command="start", description="Открыть приложение")
STATUS_COMMAND = BotCommand(command="status", description="Состояние системы")

# Текст кнопки меню чата — лимит Bot API 64 символа.
MENU_BUTTON_TEXT = "app"


def parse_admin_ids(raw: str) -> list[int]:
    """Разбирает строку ``ADMIN_IDS`` в список числовых идентификаторов.

    Args:
        raw: Значение ``settings.ADMIN_IDS`` (id через запятую).

    Returns:
        Список id; некорректные элементы пропускаются с предупреждением.
    """
    admin_ids: list[int] = []
    for part in raw.split(","):
        stripped = part.strip()
        if not stripped:
            continue
        try:
            admin_ids.append(int(stripped))
        except ValueError:
            logger.warning("Некорректный ADMIN_IDS: {!r} пропущен", stripped)
    return admin_ids


async def setup_bot_menu(bot: Bot) -> None:
    """Идемпотентно задаёт команды и кнопку меню чата через Bot API.

    Вызывается один раз при старте, после успешной проверки связи с Telegram.
    Ошибки Bot API не роняют запуск: меню — вспомогательный элемент, проблему
    логируем и продолжаем.

    Args:
        bot: запущенный экземпляр бота.
    """
    try:
        await bot.set_my_commands([START_COMMAND], scope=BotCommandScopeDefault())
    except TelegramAPIError as exc:
        logger.warning("Не удалось задать команды по умолчанию: {}", exc)

    admin_ids = parse_admin_ids(settings.ADMIN_IDS or "")
    for admin_id in admin_ids:
        try:
            await bot.set_my_commands(
                [START_COMMAND, STATUS_COMMAND],
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except TelegramAPIError as exc:
            logger.warning("Не удалось задать команды админа {}: {}", admin_id, exc)

    if not settings.MINI_APP_URL:
        logger.warning("MINI_APP_URL не задан — кнопка меню чата не обновлена")
    else:
        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text=MENU_BUTTON_TEXT,
                    web_app=WebAppInfo(url=settings.MINI_APP_URL),
                )
            )
        except TelegramAPIError as exc:
            logger.warning("Не удалось задать кнопку меню чата: {}", exc)

    logger.info(
        "Меню команд и кнопка меню чата обновлены из кода (админов: {})",
        len(admin_ids),
    )
