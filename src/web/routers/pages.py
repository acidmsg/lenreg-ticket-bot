"""
HTML-страницы веб-дашборда.

Все эндпоинты — read-only, рендерят Jinja2-шаблоны.
"""

import time
from typing import cast

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from loguru import logger

from src.services.healthcheck import metrics as health_metrics
from src.services.healthcheck import metrics_lock
from src.web.routers._shared import get_clinics_data, get_summary_data, get_users_data

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard_summary(request: Request) -> HTMLResponse:
    """Главная страница — сводка."""
    try:
        db = request.app.state.db
        pm = request.app.state.prometheus_metrics

        data = await get_summary_data(db, pm)
        stats = data["stats"]

        # Строка здоровья API (для отображения)
        api_health = health_metrics.api_health_str()

        # Состояние переключателя планового сканирования врачей
        doctor_scan_enabled = await db.config.get_config("doctor_scan_enabled", "1")

        templates = cast(Jinja2Templates, request.app.state.templates)
        return templates.TemplateResponse(
            request,
            "summary.html",
            {
                "stats": stats,
                "active_monitorings": data["active_monitorings"],
                "uptime": data["uptime_str"],
                "api_health": api_health,
                "api_ok": data["api_ok"],
                "monitor_alive": data["monitor_loop_alive"],
                "discovery_alive": data["discovery_tasks_alive"],
                "healthcheck_alive": data["healthcheck_loop_alive"],
                "api_checks": data["checks_total"],
                "api_errors": data["errors_total"],
                "notifications": data["notifications_sent"],
                "recent_alerts": data["recent_alerts"],
                "doctors_discovered": data["doctors_discovered"],
                "doctors_last_scan": data["doctors_last_scan"],
                "doctor_scan_enabled": doctor_scan_enabled == "1",
            },
        )
    except Exception:
        logger.exception("Ошибка в dashboard_summary")
        raise


@router.get("/users", response_class=HTMLResponse)
async def users_list(request: Request) -> HTMLResponse:
    """Список пользователей."""
    db = request.app.state.db
    users_data = get_users_data(db)

    templates = cast(Jinja2Templates, request.app.state.templates)
    return templates.TemplateResponse(
        request,
        "users.html",
        {
            "users": users_data,
            "total": len(users_data),
        },
    )


@router.get("/users/{uid}", response_class=HTMLResponse)
async def user_detail(request: Request, uid: str) -> HTMLResponse:
    """Детали пользователя."""
    db = request.app.state.db
    db_data = db.data

    templates = cast(Jinja2Templates, request.app.state.templates)
    user_info = db_data.get(uid)
    if user_info is None:
        return templates.TemplateResponse(
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

    return templates.TemplateResponse(
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
) -> HTMLResponse:
    """Лог мониторинга с пагинацией и фильтрацией."""
    db = request.app.state.db
    logs = await db.get_all_monitoring_logs(
        limit=limit, offset=offset, uid=uid, status=status
    )
    total = await db.get_all_monitoring_logs_count(uid=uid, status=status)

    templates = cast(Jinja2Templates, request.app.state.templates)
    return templates.TemplateResponse(
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
async def clinics_list(request: Request) -> HTMLResponse:
    """Список клиник."""
    db = request.app.state.db
    clinics_data = await get_clinics_data(db)

    templates = cast(Jinja2Templates, request.app.state.templates)
    return templates.TemplateResponse(
        request,
        "clinics.html",
        {
            "clinics": clinics_data,
            "total": len(clinics_data),
        },
    )


@router.get("/backups", response_class=HTMLResponse)
async def backups_page(request: Request) -> HTMLResponse:
    """Страница управления резервным копированием."""
    templates = cast(Jinja2Templates, request.app.state.templates)
    return templates.TemplateResponse(
        request,
        "backups.html",
        {
            "api_key": request.app.state.config.WEB_DASHBOARD_API_KEY,
        },
    )


@router.get("/api-status", response_class=HTMLResponse)
async def api_status(request: Request) -> HTMLResponse:
    """Состояние внешнего API."""
    pm = request.app.state.prometheus_metrics

    async with metrics_lock:
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

    templates = cast(Jinja2Templates, request.app.state.templates)
    return templates.TemplateResponse(
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
