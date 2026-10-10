"""Бот-подтверждение записи: канал, независимый от WebView."""

from __future__ import annotations

from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from loguru import logger

_bot: Bot | None = None


def set_bot(bot: Bot | None) -> None:
    """Регистрирует бот процесса для уведомлений."""
    global _bot
    _bot = bot


def get_bot() -> Bot | None:
    """Возвращает бот процесса или None."""
    return _bot


def _format(booking: dict[str, Any]) -> str:
    """Текст подтверждения записи."""
    lines = ["✅ Запись подтверждена."]
    if booking.get("doctor_name"):
        lines.append("👨⚕️ " + str(booking["doctor_name"]))
    if booking.get("specialty"):
        lines.append("🩺 " + str(booking["specialty"]))
    if booking.get("clinic_name"):
        lines.append("🏥 " + str(booking["clinic_name"]))
    if booking.get("date"):
        lines.append(
            "📅 " + str(booking["date"]) + " в " + str(booking.get("time", ""))
        )
    return "\n".join(lines)


async def send_booking_confirmed(telegram_id: str, booking: dict[str, Any]) -> None:
    """Отправляет подтверждение записи; сбой глотается (best-effort)."""
    bot = _bot
    if bot is None:
        return
    try:
        await bot.send_message(int(telegram_id), _format(booking))
    except (TelegramAPIError, ValueError) as exc:
        logger.warning("Не удалось отправить подтверждение записи: {}", exc)
