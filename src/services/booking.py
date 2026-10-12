"""
Доменная оркестрация бронирования талона (``POST /api/user/book``).

Модуль не зависит от HTTP: идемпотентность (``Idempotency-Key``) и уведомление
Telegram остаются в web-слое (:mod:`src.web.routers.user_bookings`). Здесь —
резолв пациента и врача, natural-key дедуп, ``pending``-запись, вызов внешнего
API и классификация доменного исхода.
"""

import datetime
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx
from loguru import logger

from src.database.manager import DatabaseManager
from src.database.types import BookingEntry
from src.services.patient_check import CHECK_STATUS_INVALID, check_patient_status
from src.utils.helpers import format_error_message

#: Сколько секунд pending-запись считается «выполняющейся» и блокирует
#: повторную попытку. По истечении запись не блокирует новый запрос.
PENDING_BOOKING_TTL_SECONDS = 120


@dataclass(frozen=True, slots=True)
class BookingCommand:
    """Доменные параметры бронирования плюс идентичность пользователя."""

    telegram_id: str
    clinic_id: str
    patient_id: str
    doctor_id: str
    appointment_id: str
    slot_date: str
    slot_time: str
    history_id: str = ""
    referral_id: str = ""


@dataclass(frozen=True, slots=True)
class BookingOutcome:
    """Доменный исход сценария бронирования для HTTP-слоя.

    ``status`` — термин для HTTP-слоя: ``confirmed``, ``already_booked``,
    ``busy``, ``slot_taken``, ``forbidden``, ``patient_not_found``,
    ``api_timeout``, ``api_unavailable``, ``unknown``.
    """

    status: str
    http_status: int
    body: dict[str, Any]
    booking_id: str = ""
    retry_after: str = ""


@dataclass(frozen=True, slots=True)
class BookingContext:
    """Собранные реквизиты записи: пациент, врач, клиника, ключ записи."""

    booking_id: str
    patient_name: str
    doctor_id: str
    doctor_name: str
    specialty: str
    clinic_name: str


def slot_date_display(iso_date: str) -> str:
    """Переводит дату слота из ISO ``ГГГГ-ММ-ДД`` в ``ДД.ММ.ГГГГ``.

    Формат ``ДД.ММ.ГГГГ`` — формат хранения ``bookings.slot_date``: он
    зафиксирован автоархивацией прошедших записей и экспортом в ICS.
    """
    return datetime.date.fromisoformat(iso_date).strftime("%d.%m.%Y")


async def book(
    command: BookingCommand,
    api: Any,
    db: DatabaseManager,
) -> BookingOutcome:
    """Выполняет сценарий бронирования и возвращает доменный исход."""
    user_data = await _load_user_data(db, command)
    if user_data is None:
        return _error(500, "unknown", "Внутренняя ошибка сервера.")

    patients = user_data.get("patients", {})
    if command.patient_id not in patients:
        logger.warning(
            "Запись на чужого пациента p_id={} (uid={})",
            command.patient_id,
            command.telegram_id,
        )
        return _error(403, "forbidden", "Пациент не найден у текущего пользователя.")

    patient_info = patients.get(command.patient_id, {})
    patient_name = patient_info.get("fio", command.patient_id)
    booking_id = f"{command.patient_id}_{command.doctor_id}_{command.appointment_id}"

    duplicate = await _find_duplicate(db, command, booking_id)
    if duplicate is not None:
        return duplicate

    if await _patient_missing_in_clinic(command, patient_info, api, db):
        return _error(
            409,
            "patient_not_found",
            (
                "Пациент не найден в выбранной клинике. "
                "Проверьте ФИО и дату рождения в карточке пациента."
            ),
        )

    context = await _resolve_context(db, user_data, command, booking_id, patient_name)
    if isinstance(context, BookingOutcome):
        return context

    await _save_booking(db, command, context, status="pending")

    result = await _call_api(api, command)
    if isinstance(result, BookingOutcome):
        return result
    return await _classify_result(db, result, command, context)


async def _load_user_data(
    db: DatabaseManager, command: BookingCommand
) -> Mapping[str, Any] | None:
    """Читает данные пользователя; ошибка чтения → ``None`` (ответ 500)."""
    try:
        return await db.get_user_data(command.telegram_id)
    except Exception:
        logger.exception("Ошибка получения данных пользователя {}", command.telegram_id)
        return None


async def _find_duplicate(
    db: DatabaseManager, command: BookingCommand, booking_id: str
) -> BookingOutcome | None:
    """Natural-key дедуп по четвёрке (uid, patient_id, doctor_id, appointment_id).

    Повтор означает, что запись уже оформлена — например, ответ на первый
    запрос потерялся при обрыве связи. ``pending``-запись в пределах
    ``PENDING_BOOKING_TTL_SECONDS`` блокирует повтор (409 busy), устаревшая —
    не блокирует; ``failed`` тоже не блокирует.
    """
    existing = await db.get_booking_by_id(booking_id)
    if (
        existing is None
        or str(existing["uid"]) != command.telegram_id
        or existing.get("is_archived", 0)
    ):
        return None

    existing_status = existing.get("status", "confirmed")
    if existing_status == "pending":
        age = time.time() - float(existing.get("created_at", 0) or 0)
        if age < PENDING_BOOKING_TTL_SECONDS:
            logger.info(
                "Запись booking_id={} ещё оформляется (uid={})",
                booking_id,
                command.telegram_id,
            )
            return BookingOutcome(
                status="busy",
                http_status=409,
                body=_busy_body(),
                retry_after="3",
            )
        return None
    if existing_status == "failed":
        return None

    logger.info(
        "Повторная запись: booking_id={} уже существует (uid={})",
        booking_id,
        command.telegram_id,
    )
    return BookingOutcome(
        status="already_booked",
        http_status=200,
        body=_already_booked_body(existing),
        booking_id=str(existing["booking_id"]),
    )


async def _patient_missing_in_clinic(
    command: BookingCommand,
    patient_info: Any,
    api: Any,
    db: DatabaseManager,
) -> bool:
    """Предпроверка (P3-PREBOOK): пациент должен числиться в клинике записи.

    Дешёвая проверка с кэшем (P3-VERIFY) вместо ошибки внешнего signup:
    пользователь получает понятное «пациент не найден».
    """
    check_status = await check_patient_status(
        command.telegram_id,
        command.patient_id,
        patient_info,
        api,
        db,
        clinic_ids=[command.clinic_id],
    )
    if check_status != CHECK_STATUS_INVALID:
        return False

    logger.info(
        "Запись отклонена: пациент ...{} не найден в клинике {} (uid=...{})",
        str(command.patient_id)[-4:],
        command.clinic_id,
        str(command.telegram_id)[-4:],
    )
    return True


async def _resolve_context(
    db: DatabaseManager,
    user_data: Mapping[str, Any],
    command: BookingCommand,
    booking_id: str,
    patient_name: str,
) -> BookingContext | BookingOutcome:
    """Реквизиты врача: мониторинг → справочник клиники по паре → отказ 400."""
    monitored = user_data.get("monitoring", {}).get(command.patient_id, {})
    doctor_info = monitored.get(command.doctor_id)
    doctor_name = doctor_info.get("name", "") if doctor_info else ""
    specialty = doctor_info.get("specialty", "") if doctor_info else ""

    if not doctor_name or not specialty:
        clinic_doctors = await db.get_doctors_for_clinic(command.clinic_id)
        clinic_doctor = clinic_doctors.get(command.doctor_id)
        if clinic_doctor is not None:
            doctor_name = doctor_name or clinic_doctor["name"]
            specialty = specialty or clinic_doctor["specialty"]
        elif clinic_doctors:
            logger.warning(
                "Врач d_id={} не найден в справочнике клиники c_id={} (uid={})",
                command.doctor_id,
                command.clinic_id,
                command.telegram_id,
            )
            return _error(
                400, "unknown", "Выбранный врач не найден в указанной клинике."
            )

    clinic_name = await db.get_clinic_name(command.clinic_id) or command.clinic_id
    return BookingContext(
        booking_id=booking_id,
        patient_name=patient_name,
        doctor_id=command.doctor_id,
        doctor_name=doctor_name or command.doctor_id,
        specialty=specialty,
        clinic_name=clinic_name,
    )


async def _save_booking(
    db: DatabaseManager,
    command: BookingCommand,
    context: BookingContext,
    *,
    status: str,
) -> None:
    """Сохраняет запись: ``pending`` до внешнего вызова, ``confirmed`` после.

    Ошибка сохранения не фейлит сценарий: ``pending`` уже мог быть записан,
    а подтверждение на стороне портала уже создано.
    """
    entry = BookingEntry(
        booking_id=context.booking_id,
        uid=command.telegram_id,
        p_id=command.patient_id,
        d_id=context.doctor_id,
        doctor_name=context.doctor_name,
        patient_name=context.patient_name,
        specialty=context.specialty,
        clinic_id=command.clinic_id,
        clinic_name=context.clinic_name,
        slot_date=slot_date_display(command.slot_date),
        slot_time=command.slot_time,
        appointment_id=command.appointment_id,
        created_at=time.time(),
        is_archived=0,
        status=status,
    )
    try:
        await db.save_booking(entry)
    except Exception as exc:
        if status == "confirmed":
            logger.error("Ошибка сохранения booking в БД: {}", exc)
        else:
            logger.exception(
                "Не удалось сохранить pending-запись {}", context.booking_id
            )


async def _mark_failed(db: DatabaseManager, booking_id: str) -> None:
    """Помечает запись как ``failed``; ошибка не пробрасывается."""
    try:
        await db.update_booking_status(booking_id, "failed")
    except Exception:
        logger.exception("Не удалось пометить запись {} как failed", booking_id)


async def _call_api(api: Any, command: BookingCommand) -> Any:
    """Вызывает API бронирования; ``httpx``-исключения → доменный исход."""
    try:
        return await api.book_appointment(
            clinic_id=command.clinic_id,
            patient_id=command.patient_id,
            appointment_id=command.appointment_id,
            history_id=command.history_id,
            referral_id=command.referral_id,
        )
    except httpx.TimeoutException:
        logger.error(
            "Таймаут API при бронировании для пользователя {}", command.telegram_id
        )
        return _error(504, "api_timeout", format_error_message("api_timeout"))
    except httpx.NetworkError:
        logger.error(
            "Сетевая ошибка API при бронировании для пользователя {}",
            command.telegram_id,
        )
        return _error(502, "api_unavailable", format_error_message("api_unavailable"))
    except Exception:
        logger.exception(
            "Ошибка при бронировании для пользователя {}", command.telegram_id
        )
        return _error(500, "unknown", format_error_message("unknown"))


def _is_slot_taken(error_id: Any, detail_lower: str) -> bool:
    """IdError 39 либо текст про занятый слот означают, что слот уже выкуплен."""
    return error_id == 39 or "занят" in detail_lower or "slot_taken" in detail_lower


def _is_forbidden(detail_lower: str) -> bool:
    """Признак запрета со стороны портала (HTTP 403 в тексте ошибки)."""
    return "403" in detail_lower or "заблокировало" in detail_lower


async def _classify_result(
    db: DatabaseManager,
    result: Any,
    command: BookingCommand,
    context: BookingContext,
) -> BookingOutcome:
    """Классифицирует ответ портала: успех либо доменный исход ошибки."""
    if result.success:
        await _save_booking(db, command, context, status="confirmed")
        return BookingOutcome(
            status="confirmed",
            http_status=200,
            body=_confirmed_body(context, command),
            booking_id=context.booking_id,
        )

    if not result.error:
        return _error(500, "unknown", format_error_message("unknown"))
    return await _classify_error(db, result, context)


async def _classify_error(
    db: DatabaseManager, result: Any, context: BookingContext
) -> BookingOutcome:
    """Разбирает причину отказа портала в доменный исход."""
    detail = result.error.ErrorDescription or result.error.detail or ""
    lowered = detail.lower()

    if detail == "busy":
        # Предыдущая запись ещё выполняется (защита от конкурентных запросов)
        return BookingOutcome(
            status="busy", http_status=409, body=_busy_body(), retry_after="2"
        )
    if _is_slot_taken(result.error.IdError, lowered):
        await _mark_failed(db, context.booking_id)
        return BookingOutcome(
            status="slot_taken", http_status=409, body=_slot_taken_body()
        )
    if _is_forbidden(lowered):
        await _mark_failed(db, context.booking_id)
        return BookingOutcome(
            status="forbidden", http_status=403, body=_forbidden_body()
        )
    if "таймаут" in lowered or "timeout" in lowered:
        return _error(504, "api_timeout", format_error_message("api_timeout", detail))
    if "сетевая" in lowered or "network" in lowered:
        return _error(
            502, "api_unavailable", format_error_message("api_unavailable", detail)
        )
    return _error(500, "unknown", format_error_message("unknown"))


def _error(http_status: int, error_code: str, detail: str) -> BookingOutcome:
    """Собирает исход-ошибку с телом контракта BookErrorResponse."""
    return BookingOutcome(
        status=error_code,
        http_status=http_status,
        body={"success": False, "error": error_code, "detail": detail},
    )


def _busy_body() -> dict[str, Any]:
    """Тело ответа «предыдущая запись ещё выполняется»."""
    return {
        "success": False,
        "error": "busy",
        "detail": format_error_message("busy"),
    }


def _slot_taken_body() -> dict[str, Any]:
    """Тело ответа «слот уже занят»."""
    return {
        "success": False,
        "error": "slot_taken",
        "detail": format_error_message("slot_taken"),
    }


def _forbidden_body() -> dict[str, Any]:
    """Тело ответа «портал запретил запись»."""
    return {
        "success": False,
        "error": "forbidden",
        "detail": format_error_message("forbidden"),
    }


def _confirmed_body(context: BookingContext, command: BookingCommand) -> dict[str, Any]:
    """Тело успешного ответа на бронирование."""
    return {
        "success": True,
        "already_booked": False,
        "booking_id": context.booking_id,
        "doctor_name": context.doctor_name,
        "specialty": context.specialty,
        "clinic_name": context.clinic_name,
        "date": slot_date_display(command.slot_date),
        "time": command.slot_time,
        "patient_name": context.patient_name,
    }


def _already_booked_body(existing: Mapping[str, Any]) -> dict[str, Any]:
    """Тело ответа на повторную запись: сохранённая запись как успех."""
    return {
        "success": True,
        "already_booked": True,
        "booking_id": existing["booking_id"],
        "doctor_name": existing["doctor_name"],
        "specialty": existing["specialty"],
        "clinic_name": existing["clinic_name"],
        "date": existing["slot_date"],
        "time": existing["slot_time"],
        "patient_name": existing["patient_name"],
    }
