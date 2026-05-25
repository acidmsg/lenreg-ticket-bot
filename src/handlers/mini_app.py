"""Обработчик данных из Telegram Mini App (web_app_data)."""

import json

from aiogram import F, Router
from aiogram.types import Message
from loguru import logger

from src.database.manager import DatabaseManager

router = Router()


@router.message(F.web_app_data)
async def handle_web_app_data(message: Message, db: DatabaseManager) -> None:
    """Обрабатывает данные, отправленные из Mini App через sendData()."""
    if not message.web_app_data:
        return

    try:
        data = json.loads(message.web_app_data.data)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Некорректные данные от Mini App: {}", message.web_app_data.data)
        await message.answer("⚠️ Некорректные данные от Mini App.")
        return

    action = data.get("action", "")
    uid = str(message.from_user.id) if message.from_user else "unknown"
    logger.info("Mini App action={} от пользователя {}", action, uid)

    if action == "doctor_added":
        doctor_name = data.get("doctor_name", "неизвестный врач")
        specialty = data.get("specialty", "")
        clinic = data.get("clinic_name", "")
        await message.answer(
            f"✅ Врач добавлен в мониторинг:\n"
            f"👨‍⚕️ {doctor_name}\n"
            f"📋 {specialty}\n"
            f"🏥 {clinic}"
        )

    elif action == "doctor_removed":
        doctor_name = data.get("doctor_name", "неизвестный врач")
        await message.answer(f"🗑 Врач удалён из мониторинга: {doctor_name}")

    elif action == "slots_viewed":
        # Только логирование
        logger.debug("Пользователь {} просмотрел слоты", uid)

    elif action == "closed":
        # Mini App закрыт без действий
        logger.debug("Пользователь {} закрыл Mini App", uid)

    else:
        logger.warning("Неизвестное действие Mini App: {} от {}", action, uid)
        await message.answer(f"⚠️ Неизвестное действие: {action}")
