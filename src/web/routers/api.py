"""
JSON API веб-дашборда.

Все эндпоинты — read-only, возвращают JSON-ответы.
"""

import time
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from src.database.types import UserData
from src.services.healthcheck import _metrics_lock
from src.services.healthcheck import metrics as health_metrics

router = APIRouter()


def _count_active_monitorings(db_data: dict[str, UserData]) -> int:
    """Считает количество активных мониторингов."""
    return sum(
        1
        for u_info in db_data.values()
        for p_id, doctors in u_info.get("monitoring", {}).items()
        if doctors
    )


def _count_total_monitored_doctors(db_data: dict[str, UserData]) -> int:
    """Считает количество отслеживаемых врачей."""
    return sum(
        len(
            set(
                d_id
                for doctors in u_info.get("monitoring", {}).values()
                for d_id in doctors
            )
        )
        for u_info in db_data.values()
    )


@router.get("/dashboard/summary")
async def api_summary(request: Request) -> dict[str, Any]:
    """JSON-сводка состояния системы."""
    db = request.app.state.db
    db_data = db.data

    stats = await db.get_total_stats()
    active_monitorings = _count_active_monitorings(db_data)
    recent_alerts = await db.get_all_monitoring_logs(limit=10, offset=0)

    async with _metrics_lock:
        uptime_str = health_metrics.uptime_str()
        uptime_sec = health_metrics.uptime_seconds()
        api_ok = health_metrics.last_api_ok
        last_check = health_metrics.last_api_check_time
        checks_total = health_metrics.api_checks_total
        errors_total = health_metrics.api_errors_total
        monitor_loop_alive = health_metrics.monitor_loop_alive
        discovery_tasks_alive = health_metrics.discovery_tasks_alive
        healthcheck_loop_alive = health_metrics.healthcheck_loop_alive

    seconds_ago = int(time.time() - last_check) if last_check else 0
    availability = 0.0
    if checks_total > 0:
        availability = round((checks_total - errors_total) / checks_total * 100, 2)

    # Форматируем алерты
    alerts = []
    for log in recent_alerts:
        alerts.append(
            {
                "id": log["id"],
                "uid": log["uid"],
                "patient_name": log["patient_name"],
                "doctor_name": log["doctor_name"],
                "specialty": log["specialty"],
                "clinic_name": log["clinic_name"],
                "slot_date": log["slot_date"],
                "status": log["status"],
                "ts": log["ts"],
            }
        )

    return {
        "uptime": uptime_str,
        "uptime_seconds": uptime_sec,
        "total_users": stats["total_users"],
        "total_patients": stats["total_patients"],
        "total_monitored_doctors": stats["total_monitored_doctors"],
        "active_monitorings": active_monitorings,
        "api_status": {
            "accessible": api_ok,
            "last_check_seconds_ago": seconds_ago,
            "total_checks": checks_total,
            "total_errors": errors_total,
            "availability_pct": availability,
        },
        "background_tasks": {
            "monitor_loop": "alive" if monitor_loop_alive else "dead",
            "discovery_tasks": discovery_tasks_alive,
            "healthcheck_loop": ("alive" if healthcheck_loop_alive else "dead"),
            "cleanup_loop": "alive",  # нет отдельного флага, подразумевается
            "schema_check_loop": "alive",
        },
        "recent_alerts": alerts,
    }


@router.get("/dashboard/users")
async def api_users(request: Request) -> dict[str, Any]:
    """JSON-список пользователей."""
    db = request.app.state.db
    db_data = db.data

    users = []
    for uid, u_info in db_data.items():
        patient_count = len(u_info.get("patients", {}))
        monitoring_count = sum(
            len(doctors) for doctors in u_info.get("monitoring", {}).values()
        )
        # Последняя активность из last_messages
        last_ts = 0.0
        for lm in u_info.get("last_messages", {}).values():
            if lm.get("ts", 0) > last_ts:
                last_ts = lm["ts"]

        users.append(
            {
                "uid": uid,
                "patient_count": patient_count,
                "monitoring_count": monitoring_count,
                "last_activity_ts": last_ts,
            }
        )

    users.sort(key=lambda u: u["uid"])
    return {"users": users, "total": len(users)}


@router.get("/dashboard/users/{uid}")
async def api_user_detail(request: Request, uid: str) -> dict[str, Any]:
    """JSON-детали пользователя."""
    db = request.app.state.db
    db_data = db.data

    user_info = db_data.get(uid)
    if user_info is None:
        return JSONResponse(
            status_code=404,
            content={"detail": f"Пользователь {uid} не найден"},
        )

    return {
        "uid": uid,
        "patients": user_info.get("patients", {}),
        "monitoring": user_info.get("monitoring", {}),
        "last_messages": user_info.get("last_messages", {}),
    }


@router.get("/dashboard/logs")
async def api_logs(
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    uid: str | None = Query(None),
    status: str | None = Query(None),
) -> dict[str, Any]:
    """JSON-лог мониторинга с пагинацией."""
    db = request.app.state.db
    logs = await db.get_all_monitoring_logs(
        limit=limit, offset=offset, uid=uid, status=status
    )
    total = await db.get_all_monitoring_logs_count(uid=uid, status=status)
    return {"logs": logs, "total": total, "offset": offset, "limit": limit}


@router.get("/dashboard/clinics")
async def api_clinics(request: Request) -> dict[str, Any]:
    """JSON-список клиник."""
    db = request.app.state.db
    clinics = await db._db.get_active_clinics()

    result = []
    for clinic in clinics:
        doctor_count = await db.get_clinic_doctor_count(clinic["clinic_id"])
        result.append(
            {
                "clinic_id": clinic["clinic_id"],
                "name": clinic["name"],
                "type": clinic["type"],
                "city": clinic["city"],
                "is_active": clinic["is_active"],
                "doctor_count": doctor_count,
            }
        )

    return {"clinics": result, "total": len(result)}


@router.get("/dashboard/health")
async def api_dashboard_health(request: Request) -> dict[str, Any]:
    """JSON-статус здоровья API."""
    async with _metrics_lock:
        api_ok = health_metrics.last_api_ok
        last_check = health_metrics.last_api_check_time
        check_duration = health_metrics.last_check_duration
        checks_total = health_metrics.api_checks_total
        errors_total = health_metrics.api_errors_total

    seconds_ago = int(time.time() - last_check) if last_check else 0
    availability = 0.0
    if checks_total > 0:
        availability = round((checks_total - errors_total) / checks_total * 100, 2)

    return {
        "api_accessible": api_ok,
        "last_check_seconds_ago": seconds_ago,
        "last_check_duration": check_duration,
        "total_checks": checks_total,
        "total_errors": errors_total,
        "availability_pct": availability,
        "schema_status": {},
        "schema_drift_details": {},
    }


@router.get("/health")
async def liveness() -> dict[str, Any]:
    """Liveness probe — всегда 200, если процесс жив."""
    return {"status": "ok"}
