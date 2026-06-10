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

from src.database.manager import DatabaseManager

router = Router()


@router.message(F.web_app_data)
async def handle_web_app_data(message: Message, db: DatabaseManager) -> None:
    """Обрабатывает данные, отправленные из Mini App через sendData()."""
    if not message.web_app_data:
        return

    # --- Верификация данных ---
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


async def _handle_doctor_added(
    message: Message, db: DatabaseManager, uid: str, payload: dict
) -> None:
    """Обрабатывает действие 'doctor_added' из Mini App.

    Проверяет, существует ли уже запись в БД (добавлена через REST API).
    Если нет — добавляет через ``toggle_monitoring()``.
    """
    doctor_name = payload.get("doctor_name", "неизвестный врач")
    specialty = payload.get("specialty", "")
    clinic_name = payload.get("clinic_name", "")

    # Пытаемся извлечь ID из payload (если Mini App их передаёт)
    doctor_id = payload.get("doctor_id", "")
    patient_id = payload.get("patient_id", "")
    clinic_id = payload.get("clinic_id", "")

    # Если есть ID — проверяем, существует ли уже запись (REST API мог добавить)
    if doctor_id and patient_id:
        user_data = await db.get_user_data(uid)
        patient_doctors = user_data.get("monitoring", {}).get(patient_id, {})
        if doctor_id in patient_doctors:
            # Уже добавлено через REST API — просто подтверждаем
            existing = patient_doctors[doctor_id]
            existing_name = (
                existing.get("name", doctor_name)
                if isinstance(existing, dict)
                else doctor_name
            )
            await message.answer(
                f"✅ Врач уже в мониторинге:\n"
                f"👨‍⚕️ {existing_name}\n"
                f"📋 {specialty}\n"
                f"🏥 {clinic_name}"
            )
            return

        # Не найдено в БД — добавляем через toggle_monitoring (fallback)
        if clinic_id:
            try:
                await db.toggle_monitoring(
                    uid=uid,
                    p_id=patient_id,
                    d_id=doctor_id,
                    d_name=doctor_name,
                    clinic_id=clinic_id,
                    d_spec=specialty,
                    date="",
                )
                logger.info(
                    "Mini App fallback: врач {} (d_id={}) добавлен через "
                    "toggle_monitoring",
                    doctor_name,
                    doctor_id,
                )
            except Exception as e:
                logger.error(
                    "Mini App: ошибка при добавлении врача {} (d_id={}): {}",
                    doctor_name,
                    doctor_id,
                    e,
                )
                await message.answer("⚠️ Ошибка при добавлении врача в мониторинг.")
                return

    await message.answer(
        f"✅ Врач добавлен в мониторинг:\n"
        f"👨‍⚕️ {doctor_name}\n"
        f"📋 {specialty}\n"
        f"🏥 {clinic_name}"
    )


async def _handle_doctor_removed(
    message: Message, db: DatabaseManager, uid: str, payload: dict
) -> None:
    """Обрабатывает действие 'doctor_removed' из Mini App.

    Проверяет, существует ли ещё запись в БД (могла быть удалена через REST API).
    Если запись всё ещё есть — удаляет через ``toggle_monitoring()``.
    """
    doctor_name = payload.get("doctor_name", "неизвестный врач")

    # Пытаемся извлечь ID из payload
    monitoring_id = payload.get("monitoring_id", "")
    doctor_id = payload.get("doctor_id", "")
    patient_id = payload.get("patient_id", "")

    # Разбираем monitoring_id если есть (формат: {patient_id}_{doctor_id})
    if monitoring_id and not (patient_id and doctor_id):
        parts = monitoring_id.split("_", 1)
        if len(parts) == 2:
            patient_id, doctor_id = parts

    if doctor_id and patient_id:
        user_data = await db.get_user_data(uid)
        patient_doctors = user_data.get("monitoring", {}).get(patient_id, {})

        if doctor_id in patient_doctors:
            # Всё ещё в мониторинге — удаляем через toggle_monitoring (fallback)
            d_info = patient_doctors[doctor_id]
            existing_name = (
                d_info.get("name", doctor_name)
                if isinstance(d_info, dict)
                else doctor_name
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
                    d_spec=specialty,
                )
                logger.info(
                    "Mini App fallback: врач {} (d_id={}) удалён через "
                    "toggle_monitoring",
                    existing_name,
                    doctor_id,
                )
            except Exception as e:
                logger.error(
                    "Mini App: ошибка при удалении врача {} (d_id={}): {}",
                    existing_name,
                    doctor_id,
                    e,
                )
                await message.answer("⚠️ Ошибка при удалении врача из мониторинга.")
                return
        else:
            # Уже удалено через REST API
            logger.debug(
                "Mini App: врач {} (d_id={}) уже удалён через REST API",
                doctor_name,
                doctor_id,
            )

    await message.answer(f"🗑 Врач удалён из мониторинга: {doctor_name}")
