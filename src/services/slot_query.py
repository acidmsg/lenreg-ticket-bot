"""
Доменный слой запроса слотов врача (``GET /api/user/slots``).

Модуль не зависит от HTTP: разбирает режим запроса (мониторинг либо прямая
запись), проверяет принадлежность пациента текущему пользователю (IDOR) и
выполняет живой запрос слотов к порталу в рамках серверного бюджета времени.
"""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from loguru import logger

from src.config import settings
from src.database.manager import DatabaseManager
from src.database.types import MonitoringEntry


@dataclass(frozen=True, slots=True)
class SlotQuery:
    """Разобранные параметры запроса слотов (режим + реквизиты)."""

    monitoring_id: str | None = None
    clinic_id: str | None = None
    doctor_id: str | None = None
    patient_id: str | None = None


@dataclass(frozen=True, slots=True)
class ResolvedTarget:
    """Реквизиты врача, клиники и пациента для живого запроса слотов."""

    patient_id: str = ""
    doctor_id: str = ""
    clinic_id: str = ""
    doctor_name: str = ""
    specialty: str = ""
    monitoring_id: str = ""
    error_status: int | None = None
    error_detail: str = ""


@dataclass(frozen=True, slots=True)
class LiveSlots:
    """Сырой ответ портала либо код ошибки сервиса слотов."""

    slots_result: Any = None
    error_status: int | None = None
    error_code: str = ""


async def resolve_target(
    db: DatabaseManager,
    user_data: Mapping[str, Any],
    telegram_id: str,
    query: SlotQuery,
) -> ResolvedTarget:
    """Резолвит целевого врача и клинику для запроса слотов.

    Режим ``monitoring_id`` — врач из мониторинга пользователя; иначе тройка
    ``clinic_id`` + ``doctor_id`` + ``patient_id`` с проверкой владельца (IDOR).
    """
    if query.monitoring_id:
        return _resolve_monitoring_target(user_data, query)
    return await _resolve_direct_target(db, user_data, telegram_id, query)


def _resolve_monitoring_target(
    user_data: Mapping[str, Any], query: SlotQuery
) -> ResolvedTarget:
    """Врач из мониторинга пользователя; отсутствие записи — 404."""
    monitoring_id = query.monitoring_id or ""
    p_id = query.patient_id or ""
    d_id = query.doctor_id or ""

    patient_doctors = user_data.get("monitoring", {}).get(p_id, {})
    if d_id not in patient_doctors:
        detail = f"Врач с monitoring_id='{monitoring_id}' не найден в мониторинге."
        return ResolvedTarget(error_status=404, error_detail=detail)

    doctor_info = patient_doctors[d_id]
    return ResolvedTarget(
        patient_id=p_id,
        doctor_id=d_id,
        clinic_id=doctor_info.get("clinic_id", ""),
        doctor_name=doctor_info.get("name", d_id),
        specialty=doctor_info.get("specialty", ""),
        monitoring_id=monitoring_id,
    )


async def _resolve_direct_target(
    db: DatabaseManager,
    user_data: Mapping[str, Any],
    telegram_id: str,
    query: SlotQuery,
) -> ResolvedTarget:
    """Прямая запись: IDOR-проверка пациента и резолв реквизитов врача.

    Запись мониторинга необязательна: реквизиты берутся из неё, если есть,
    иначе — из справочника клиники по паре ``clinic_id`` + ``doctor_id``.
    """
    p_id = query.patient_id or ""
    d_id = query.doctor_id or ""
    c_id = query.clinic_id or ""

    if p_id not in user_data.get("patients", {}):
        logger.warning(
            "Запрос слотов для чужого пациента p_id={} (uid={})",
            p_id,
            telegram_id,
        )
        return ResolvedTarget(
            error_status=403,
            error_detail="Пациент не найден у текущего пользователя.",
        )

    doctor_entry: MonitoringEntry | None = (
        user_data.get("monitoring", {}).get(p_id, {}).get(d_id)
    )
    doctor_name = doctor_entry.get("name", "") if doctor_entry else ""
    specialty = doctor_entry.get("specialty", "") if doctor_entry else ""

    if not doctor_name or not specialty:
        clinic_doctors = await db.get_doctors_for_clinic(c_id)
        clinic_doctor = clinic_doctors.get(d_id)
        if clinic_doctor is not None:
            doctor_name = doctor_name or clinic_doctor["name"]
            specialty = specialty or clinic_doctor["specialty"]
        elif clinic_doctors:
            # Справочник клиники заполнен, а пары в нём нет — врач не из
            # этой клиники, запрос отклоняем.
            logger.warning(
                "Врач d_id={} не найден в справочнике клиники c_id={} (uid={})",
                d_id,
                c_id,
                telegram_id,
            )
            return ResolvedTarget(
                error_status=400,
                error_detail="Выбранный врач не найден в указанной клинике.",
            )

    # Справочник пуст — пару проверить нечем; внешний API отклонит неверную
    # пару сам, а блокировать запись из-за незаполненного кэша нельзя.
    return ResolvedTarget(
        patient_id=p_id,
        doctor_id=d_id,
        clinic_id=c_id,
        doctor_name=doctor_name or d_id,
        specialty=specialty,
        monitoring_id=f"{p_id}_{d_id}",
    )


async def fetch_live(api: Any, target: ResolvedTarget) -> LiveSlots:
    """Живой запрос слотов к порталу в рамках бюджета ``WEB_SLOTS_TIMEOUT``.

    ``check_slots()`` сам поглощает сетевые ошибки и возвращает ``None``,
    поэтому ветки на ``httpx``-исключения здесь недостижимы: отказ внешнего
    API приходит как ``None`` и превращается в ``api_unavailable``.
    """
    try:
        slots_result = await asyncio.wait_for(
            api.check_slots(
                doc_id=target.doctor_id,
                patient_id=target.patient_id,
                clinic_id=target.clinic_id,
                limiter=api.limiter,
            ),
            timeout=settings.WEB_SLOTS_TIMEOUT,
        )
    except TimeoutError:
        logger.warning(
            "Превышен бюджет времени ({:.1f} с) при получении слотов: monitoring_id={}",
            settings.WEB_SLOTS_TIMEOUT,
            target.monitoring_id,
        )
        return LiveSlots(error_status=504, error_code="api_timeout")
    except Exception:
        logger.exception(
            "Ошибка при получении слотов для monitoring_id={}",
            target.monitoring_id,
        )
        return LiveSlots(error_status=500, error_code="internal")

    if slots_result is None:
        # None от check_slots() — отказ внешнего API (таймаут/сеть/DNS-отказ,
        # 403/429). Это не «нет слотов»: сообщаем о недоступности сервиса.
        logger.warning(
            "Внешний API недоступен при получении слотов: monitoring_id={}",
            target.monitoring_id,
        )
        return LiveSlots(error_status=502, error_code="api_unavailable")
    return LiveSlots(slots_result=slots_result)


def format_slots(slots_result: Any, clinic_id: str) -> list[dict[str, str]]:
    """Собирает список слотов из параллельных списков ``formatted``/``slots``.

    ``formatted`` даёт строку «ДД.ММ.ГГГГ в ЧЧ:ММ», ``raw_slots`` — объект слота
    с полем ``id`` (appointment_id). Оба списка строятся в одном порядке.
    """
    formatted_list = slots_result.formatted or []
    raw_slots = slots_result.slots or []
    slots: list[dict[str, str]] = []
    for index, slot_str in enumerate(formatted_list):
        appointment_id = raw_slots[index].id if index < len(raw_slots) else ""
        parts = slot_str.split(" в ", 1)
        date_str = parts[0] if len(parts) > 0 else slot_str
        time_str = parts[1] if len(parts) > 1 else ""
        slots.append(
            {
                "date": date_str.strip(),
                "time": time_str.strip(),
                "appointment_id": appointment_id,
                "slot_id": appointment_id,  # синоним
                "clinic_id": clinic_id,
            }
        )
    return slots
