"""
Профиль пользователя и справочники Mini App API (``/api/user``).

Модуль описывает пути без префикса: префикс ``/api/user`` добавляет
агрегатор :mod:`src.web.routers.user_api`.
"""

from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from loguru import logger

from src.web.routers.user_common import _get_db, _get_telegram_id, _serialize_patients

router = APIRouter()


@router.get("/profile")
async def get_profile(request: Request) -> dict[str, Any]:
    """Получить профиль пользователя (ФИО, список пациентов, статистику мониторинга)."""
    db = _get_db(request)
    telegram_id = _get_telegram_id(request)

    user_data = await db.get_user_data(telegram_id)

    patients_list = _serialize_patients(user_data.get("patients", {}))

    monitoring = user_data.get("monitoring", {})
    monitoring_count = sum(len(doctors) for doctors in monitoring.values())

    return {
        "telegram_id": telegram_id,
        "patients": patients_list,
        "monitoring_count": monitoring_count,
        "stats": {
            "total_patients": len(user_data.get("patients", {})),
            "total_monitored_doctors": sum(
                len(doctors) for doctors in monitoring.values()
            ),
        },
    }


@router.get("/clinics")
async def get_clinics(request: Request) -> dict[str, Any]:
    """Список поликлиник (из кэша БД)."""
    db = _get_db(request)

    active_clinics = await db._db.get_active_clinics()

    clinics_list: list[dict[str, Any]] = []
    for clinic in active_clinics:
        clinics_list.append(
            {
                "clinic_id": clinic["clinic_id"],
                "name": clinic["name"],
                "short_name": clinic.get("short_name", clinic["name"]),
                "type": clinic["type"],
                "city": clinic.get("city", ""),
                "is_active": bool(clinic["is_active"]),
            }
        )

    return {"clinics": clinics_list}


@router.get("/specialties", response_model=None)
async def get_specialties(
    request: Request,
    clinic_id: str = Query(..., description="ID клиники (обязательный)"),
    patient_id: str | None = Query(None, description="ID пациента (опционально)"),
) -> dict[str, Any] | JSONResponse:
    """Список специальностей в выбранной поликлинике (из БД, таблица doctors)."""
    db = _get_db(request)

    try:
        specialties_raw = await db._db.get_clinic_specialties(clinic_id)
    except Exception:
        logger.exception(
            "Ошибка при получении специальностей из БД для clinic_id={}", clinic_id
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Внутренняя ошибка сервера"},
        )

    specialties: list[dict[str, Any]] = []
    for spec in specialties_raw:
        specialties.append(
            {
                "specialty_id": spec["specialty_id"],
                "name": spec["specialty"],
                "is_tech": False,
                "is_doc": True,
            }
        )

    return {
        "clinic_id": clinic_id,
        "specialties": specialties,
    }
