"""
HTML-страницы веб-дашборда.

Все эндпоинты — read-only, рендерят Jinja2-шаблоны.
"""

import time

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from loguru import logger

from src.services.healthcheck import _metrics_lock
from src.services.healthcheck import metrics as health_metrics

router = APIRouter()


def _count_active_monitorings(db_data: dict) -> int:
    """Считает количество активных мониторингов (разные p_id у пользователей)."""
    return sum(
        1
        for u_info in db_data.values()
        for p_id, doctors in u_info.get("monitoring", {}).items()
        if doctors
    )


@router.get("/", response_class=HTMLResponse)
async def dashboard_summary(request: Request):
    """Главная страница — сводка."""
    try:
        db = request.app.state.db
        db_data = db.data

        stats = await db.get_total_stats()
        active_monitorings = _count_active_monitorings(db_data)

        # Последние 10 алертов из лога
        recent_alerts = await db.get_all_monitoring_logs(limit=10, offset=0)

        # Метрики под локом
        async with _metrics_lock:
            uptime = health_metrics.uptime_str()
            api_health = health_metrics.api_health_str()
            monitor_alive = health_metrics.monitor_loop_alive
            discovery_alive = health_metrics.discovery_tasks_alive
            healthcheck_alive = health_metrics.healthcheck_loop_alive
            api_checks = health_metrics.api_checks_total
            api_errors = health_metrics.api_errors_total
            notifications = health_metrics.monitoring_notifications_sent

        return request.app.state.templates.TemplateResponse(
            request,
            "summary.html",
            {
                "stats": stats,
                "active_monitorings": active_monitorings,
                "uptime": uptime,
                "api_health": api_health,
                "monitor_alive": monitor_alive,
                "discovery_alive": discovery_alive,
                "healthcheck_alive": healthcheck_alive,
                "api_checks": api_checks,
                "api_errors": api_errors,
                "notifications": notifications,
                "recent_alerts": recent_alerts,
            },
        )
    except Exception:
        logger.exception("Ошибка в dashboard_summary")
        raise


@router.get("/users", response_class=HTMLResponse)
async def users_list(request: Request):
    """Список пользователей."""
    db = request.app.state.db
    db_data = db.data

    users_data = []
    for uid, u_info in db_data.items():
        patient_count = len(u_info.get("patients", {}))
        monitoring_count = sum(
            len(doctors) for doctors in u_info.get("monitoring", {}).values()
        )
        users_data.append(
            {
                "uid": uid,
                "patient_count": patient_count,
                "monitoring_count": monitoring_count,
            }
        )

    # Сортируем по UID
    users_data.sort(key=lambda u: u["uid"])

    return request.app.state.templates.TemplateResponse(
        request,
        "users.html",
        {
            "users": users_data,
            "total": len(users_data),
        },
    )


@router.get("/users/{uid}", response_class=HTMLResponse)
async def user_detail(request: Request, uid: str):
    """Детали пользователя."""
    db = request.app.state.db
    db_data = db.data

    user_info = db_data.get(uid)
    if user_info is None:
        return request.app.state.templates.TemplateResponse(
            request,
            "user_detail.html",
            {
                "uid": uid,
                "not_found": True,
                "patients": {},
                "monitoring": {},
                "last_messages": {},
            },
        )

    return request.app.state.templates.TemplateResponse(
        request,
        "user_detail.html",
        {
            "uid": uid,
            "not_found": False,
            "patients": user_info.get("patients", {}),
            "monitoring": user_info.get("monitoring", {}),
            "last_messages": user_info.get("last_messages", {}),
        },
    )


@router.get("/logs", response_class=HTMLResponse)
async def monitoring_logs(
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    uid: str | None = Query(None),
    status: str | None = Query(None),
):
    """Лог мониторинга с пагинацией и фильтрацией."""
    db = request.app.state.db
    logs = await db.get_all_monitoring_logs(
        limit=limit, offset=offset, uid=uid, status=status
    )
    total = await db.get_all_monitoring_logs_count(uid=uid, status=status)

    return request.app.state.templates.TemplateResponse(
        request,
        "logs.html",
        {
            "logs": logs,
            "offset": offset,
            "limit": limit,
            "total": total,
            "uid_filter": uid or "",
            "status_filter": status or "",
        },
    )


@router.get("/clinics", response_class=HTMLResponse)
async def clinics_list(request: Request):
    """Список клиник."""
    db = request.app.state.db
    clinics = await db._db.get_active_clinics()

    clinics_data = []
    for clinic in clinics:
        doctor_count = await db.get_clinic_doctor_count(clinic["clinic_id"])
        clinics_data.append(
            {
                "clinic_id": clinic["clinic_id"],
                "name": clinic["name"],
                "type": clinic["type"],
                "city": clinic["city"],
                "is_active": clinic["is_active"],
                "doctor_count": doctor_count,
            }
        )

    return request.app.state.templates.TemplateResponse(
        request,
        "clinics.html",
        {
            "clinics": clinics_data,
            "total": len(clinics_data),
        },
    )


@router.get("/api-status", response_class=HTMLResponse)
async def api_status(request: Request):
    """Состояние внешнего API."""
    pm = request.app.state.prometheus_metrics

    async with _metrics_lock:
        uptime = health_metrics.uptime_str()
        api_ok = health_metrics.last_api_ok
        last_check = health_metrics.last_api_check_time
        check_duration = health_metrics.last_check_duration
        checks_total = health_metrics.api_checks_total
        errors_total = health_metrics.api_errors_total
        last_error = health_metrics.last_error_message
        monitor_alive = health_metrics.monitor_loop_alive
        healthcheck_alive = health_metrics.healthcheck_loop_alive
        discovery_alive = health_metrics.discovery_tasks_alive

    seconds_ago = int(time.time() - last_check) if last_check else 0
    availability = 0.0
    if checks_total > 0:
        availability = round((checks_total - errors_total) / checks_total * 100, 2)

    # Текущее состояние схем API из PrometheusMetrics
    schema_status: dict[str, bool] = {}
    schema_drift_details: dict = {}
    try:
        schema_status = pm.get_schema_status()
    except Exception:
        logger.exception("Ошибка получения статуса схем API")

    return request.app.state.templates.TemplateResponse(
        request,
        "api_status.html",
        {
            "uptime": uptime,
            "api_ok": api_ok,
            "seconds_ago": seconds_ago,
            "check_duration": check_duration,
            "checks_total": checks_total,
            "errors_total": errors_total,
            "availability": availability,
            "last_error": last_error,
            "monitor_alive": monitor_alive,
            "healthcheck_alive": healthcheck_alive,
            "discovery_alive": discovery_alive,
            "schema_status": schema_status,
            "schema_drift_details": schema_drift_details,
        },
    )
