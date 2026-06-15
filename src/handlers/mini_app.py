"""Обработчик данных из Telegram Mini App (web_app_data).

Обрабатывает подтверждения от Mini App после того, как REST API
(``POST /api/user/doctors/add``, ``DELETE /api/user/doctors/{id}``)
уже выполнил операции с БД. Проверяет наличие записей в БД и,
если операция не была выполнена через REST API, выполняет её
напрямую через ``DatabaseManager.toggle_monitoring()``.
"""

import json

from aiogram import F, Router
from aiogram.types import Message
from loguru import logger

from src.config import settings
from src.database.manager import DatabaseManager
from src.utils.helpers import verify_telegram_init_data

router = Router()


@router.message(F.web_app_data)
async def handle_web_app_data(message: Message, db: DatabaseManager) -> None:
    """Обрабатывает данные, отправленные из Mini App через sendData()."""
    if not message.web_app_data:
        return

    # --- HMAC-верификация initData (защита от подделки) ---
    init_data = message.web_app_data.data
    is_valid, error_msg, _ = verify_telegram_init_data(init_data, settings.BOT_TOKEN)
    if not is_valid:
        logger.warning("Mini App: верификация initData не пройдена: {}", error_msg)
        return

    # --- Разбор payload ---
    try:
        payload = json.loads(message.web_app_data.data)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Некорректные данные от Mini App: {}", message.web_app_data.data)
        await message.answer("⚠️ Некорректные данные от Mini App.")
        return

    # Проверка: user_id из payload должен совпадать с from_user.id
    uid = str(message.from_user.id) if message.from_user else "unknown"
    payload_uid = str(payload.get("user_id", ""))
    if payload_uid and payload_uid != uid:
        logger.warning(
            "Mini App: user_id в payload ({}) не совпадает с from_user.id ({}). "
            "Данные отклонены.",
            payload_uid,
            uid,
        )
        return

    action = payload.get("action", "")
    logger.info("Mini App action={} от пользователя {}", action, uid)

    if action == "doctor_added":
        await _handle_doctor_added(message, db, uid, payload)
    elif action == "doctor_removed":
        await _handle_doctor_removed(message, db, uid, payload)
    elif action == "slots_viewed":
        logger.debug("Пользователь {} просмотрел слоты", uid)
    elif action == "closed":
        logger.debug("Пользователь {} закрыл Mini App", uid)
    else:
        logger.warning("Неизвестное действие Mini App: {} от {}", action, uid)
        await message.answer(f"⚠️ Неизвестное действие: {action}")


# ── Вспомогательные функции для _handle_doctor_added ────────────────


def _extract_doctor_fields(payload: dict) -> dict:
    """Извлекает и валидирует поля врача из web_app_data.

    Args:
        payload: Данные, переданные из Mini App через sendData().

    Returns:
        Словарь с ключами: doctor_name, specialty, clinic_name,
        doctor_id, patient_id, clinic_id.
    """
    return {
        "doctor_name": payload.get("doctor_name", "неизвестный врач"),
        "specialty": payload.get("specialty", ""),
        "clinic_name": payload.get("clinic_name", ""),
        "doctor_id": payload.get("doctor_id", ""),
        "patient_id": payload.get("patient_id", ""),
        "clinic_id": payload.get("clinic_id", ""),
    }


async def _ensure_doctor_in_db(db: DatabaseManager, uid: str, doctor_data: dict) -> int:
    """Проверяет наличие врача в БД и при необходимости добавляет через fallback.

    Returns:
        0 — врач уже существует, 1 — успешно добавлен, -1 — ошибка.
    """
    doctor_id = doctor_data["doctor_id"]
    patient_id = doctor_data["patient_id"]

    if not doctor_id or not patient_id:
        return -1

    user_data = await db.get_user_data(uid)
    patient_doctors = user_data.get("monitoring", {}).get(patient_id, {})

    if doctor_id in patient_doctors:
        return 0  # Уже добавлен через REST API

    clinic_id = doctor_data["clinic_id"]
    if not clinic_id:
        return -1

    try:
        await db.toggle_monitoring(
            uid=uid,
            p_id=patient_id,
            d_id=doctor_id,
            d_name=doctor_data["doctor_name"],
            clinic_id=clinic_id,
            doctor_specialty=doctor_data["specialty"],
            date="",
        )
        logger.info(
            "Mini App fallback: врач {} (d_id={}) добавлен через toggle_monitoring",
            doctor_data["doctor_name"],
            doctor_id,
        )
        return 1
    except Exception as e:
        logger.error(
            "Mini App: ошибка при добавлении врача {} (d_id={}): {}",
            doctor_data["doctor_name"],
            doctor_id,
            e,
        )
        return -1


async def _send_doctor_added_confirmation(
    message: Message, doctor_data: dict, db_result: int
) -> None:
    """Отправляет подтверждение пользователю о результате добавления врача.

    Args:
        message: Сообщение от Telegram.
        doctor_data: Словарь с полями врача.
        db_result: Результат ``_ensure_doctor_in_db()`` (0, 1 или -1).
    """
    doctor_name = doctor_data["doctor_name"]
    specialty = doctor_data["specialty"]
    clinic_name = doctor_data["clinic_name"]

    if db_result == 0:
        await message.answer(
            f"✅ Врач уже в мониторинге:\n"
            f"👨‍⚕️ {doctor_name}\n"
            f"📋 {specialty}\n"
            f"🏥 {clinic_name}"
        )
    elif db_result == 1:
        await message.answer(
            f"✅ Врач добавлен в мониторинг:\n"
            f"👨‍⚕️ {doctor_name}\n"
            f"📋 {specialty}\n"
            f"🏥 {clinic_name}"
        )
    else:
        await message.answer("⚠️ Ошибка при добавлении врача в мониторинг.")


# ── Вспомогательные функции для _handle_doctor_removed ──────────────


async def _remove_doctor_from_db(db: DatabaseManager, uid: str, payload: dict) -> bool:
    """Удаляет врача из БД через ``toggle_monitoring()`` (fallback).

    Извлекает ID врача и пациента из payload, проверяет наличие записи
    в БД и выполняет удаление. Если запись уже удалена через REST API —
    возвращает True без действий.

    Returns:
        True — удаление выполнено или не требуется, False — ошибка.
    """
    doctor_name = payload.get("doctor_name", "неизвестный врач")
    monitoring_id = payload.get("monitoring_id", "")
    doctor_id = payload.get("doctor_id", "")
    patient_id = payload.get("patient_id", "")

    # Разбираем monitoring_id если есть (формат: {patient_id}_{doctor_id})
    if monitoring_id and not (patient_id and doctor_id):
        parts = monitoring_id.split("_", 1)
        if len(parts) == 2:
            patient_id, doctor_id = parts

    if not doctor_id or not patient_id:
        return True

    user_data = await db.get_user_data(uid)
    patient_doctors = user_data.get("monitoring", {}).get(patient_id, {})

    if doctor_id not in patient_doctors:
        logger.debug(
            "Mini App: врач {} (d_id={}) уже удалён через REST API",
            doctor_name,
            doctor_id,
        )
        return True

    # Всё ещё в мониторинге — удаляем через toggle_monitoring (fallback)
    d_info = patient_doctors[doctor_id]
    existing_name = (
        d_info.get("name", doctor_name) if isinstance(d_info, dict) else doctor_name
    )
    clinic_id = d_info.get("clinic_id", "") if isinstance(d_info, dict) else ""
    specialty = d_info.get("specialty", "") if isinstance(d_info, dict) else ""

    try:
        await db.toggle_monitoring(
            uid=uid,
            p_id=patient_id,
            d_id=doctor_id,
            d_name=existing_name,
            clinic_id=clinic_id,
            doctor_specialty=specialty,
        )
        logger.info(
            "Mini App fallback: врач {} (d_id={}) удалён через toggle_monitoring",
            existing_name,
            doctor_id,
        )
        return True
    except Exception as e:
        logger.error(
            "Mini App: ошибка при удалении врача {} (d_id={}): {}",
            existing_name,
            doctor_id,
            e,
        )
        return False


async def _send_doctor_removed_confirmation(message: Message, doctor_name: str) -> None:
    """Отправляет подтверждение об удалении врача из мониторинга.

    Args:
        message: Сообщение от Telegram.
        doctor_name: ФИО удалённого врача.
    """
    await message.answer(f"🗑 Врач удалён из мониторинга: {doctor_name}")


# ── Основные обработчики действий ────────────────────────────────────


async def _handle_doctor_added(
    message: Message, db: DatabaseManager, uid: str, payload: dict
) -> None:
    """Обрабатывает действие 'doctor_added' из Mini App.

    Проверяет, существует ли уже запись в БД (добавлена через REST API).
    Если нет — добавляет через ``toggle_monitoring()``.
    """
    doctor_data = _extract_doctor_fields(payload)
    db_result = await _ensure_doctor_in_db(db, uid, doctor_data)
    await _send_doctor_added_confirmation(message, doctor_data, db_result)


async def _handle_doctor_removed(
    message: Message, db: DatabaseManager, uid: str, payload: dict
) -> None:
    """Обрабатывает действие 'doctor_removed' из Mini App.

    Проверяет, существует ли ещё запись в БД (могла быть удалена через REST API).
    Если запись всё ещё есть — удаляет через ``toggle_monitoring()``.
    """
    success = await _remove_doctor_from_db(db, uid, payload)
    if not success:
        await message.answer("⚠️ Ошибка при удалении врача из мониторинга.")
        return
    doctor_name = payload.get("doctor_name", "неизвестный врач")
    await _send_doctor_removed_confirmation(message, doctor_name)
