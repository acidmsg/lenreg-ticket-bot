"""
JSON API веб-дашборда.

Эндпоинты возвращают JSON-ответы для дашборда и Mini App.
"""

import csv
import io
import time
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response

from src.services.audit import actor_from_request, log_action
from src.services.doctor_discovery import trigger_force_scan
from src.services.params import (
    RESOLUTION_ORDER,
    ParamError,
    collect_params,
    set_param,
)
from src.web.routers._shared import get_clinics_data, get_summary_data, get_users_data

router = APIRouter()


@router.get("/dashboard/summary")
async def api_summary(request: Request) -> dict[str, Any]:
    """JSON-сводка состояния системы."""
    db = request.app.state.db
    pm = request.app.state.prometheus_metrics

    data = await get_summary_data(db, pm)
    stats = data["stats"]
    recent_alerts = data["recent_alerts"]

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
        "uptime": data["uptime_str"],
        "uptime_seconds": data["uptime_sec"],
        "total_users": stats["total_users"],
        "total_patients": stats["total_patients"],
        "total_monitored_doctors": stats["total_monitored_doctors"],
        "doctors_discovered": data["doctors_discovered"],
        "doctors_last_scan": data["doctors_last_scan"],
        "active_monitorings": data["active_monitorings"],
        "api_status": {
            "accessible": data["api_ok"],
            "last_check_seconds_ago": data["seconds_ago"],
            "total_checks": data["checks_total"],
            "total_errors": data["errors_total"],
            "availability_pct": data["availability"],
        },
        "background_tasks": {
            task["name"]: task["health"] for task in data["background_tasks"]
        },
        "recent_alerts": alerts,
    }


@router.get("/dashboard/users")
async def api_users(request: Request) -> dict[str, Any]:
    """JSON-список пользователей."""
    db = request.app.state.db
    users = get_users_data(db)
    return {"users": users, "total": len(users)}


@router.get("/dashboard/users/{uid}", response_model=None)
async def api_user_detail(request: Request, uid: str) -> dict[str, Any] | JSONResponse:
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
    clinics = await get_clinics_data(db)
    return {"clinics": clinics, "total": len(clinics)}


@router.get("/dashboard/health")
async def api_dashboard_health(request: Request) -> dict[str, Any]:
    """JSON-статус здоровья API."""
    from src.services.healthcheck import metrics as health_metrics
    from src.services.healthcheck import metrics_lock

    async with metrics_lock:
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


@router.get("/config", response_model=None)
async def api_config_list(request: Request) -> dict[str, Any]:
    """Список параметров конфигурации с источником значения и предупреждениями."""
    db = request.app.state.db
    return {
        "params": await collect_params(db),
        "resolution_order": list(RESOLUTION_ORDER),
    }


@router.post("/config/{key}", response_model=None)
async def api_config_set(request: Request, key: str) -> dict[str, Any] | JSONResponse:
    """Меняет параметр конфигурации из реестра (валидация обязательна).

    Ошибки: ``400`` — значение не прошло проверку, ``404`` — неизвестный ключ.
    Изменение всегда попадает в журнал действий (``config_change``).
    """
    db = request.app.state.db
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400, content={"detail": "Неверный формат запроса"}
        )

    if not isinstance(body, dict):
        return JSONResponse(
            status_code=400,
            content={"detail": "Ожидается объект с полем value"},
        )

    raw = body.get("value")
    if raw is None:
        return JSONResponse(
            status_code=400, content={"detail": "Поле value обязательно"}
        )

    try:
        return await set_param(db, key, str(raw), actor=actor_from_request(request))
    except KeyError:
        return JSONResponse(
            status_code=404, content={"detail": f"Неизвестный параметр: {key}"}
        )
    except ParamError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})


@router.post("/dashboard/doctor-scan/toggle")
async def toggle_doctor_scan(request: Request) -> dict[str, Any]:
    """Включить/выключить плановое сканирование врачей."""
    db = request.app.state.db
    current = await db.config.get_config("doctor_scan_enabled", "1")
    new_value = "0" if current == "1" else "1"
    await db.config.set_config("doctor_scan_enabled", new_value)
    await log_action(
        db,
        actor=actor_from_request(request),
        action="doctor_scan_toggle",
        enabled=new_value == "1",
    )
    return {"doctor_scan_enabled": new_value == "1"}


@router.post("/dashboard/doctor-scan/force")
async def force_doctor_scan(request: Request) -> dict[str, Any]:
    """Принудительный запуск сканирования врачей.

    ``trigger_force_scan()`` потокобезопасно планирует установку флага в loop'е
    фоновой задачи discovery. Если цикл ещё не запущен, запрос игнорируется:
    в ответе возвращается статус ``unavailable`` вместо ложного ``started``.
    """
    started = trigger_force_scan()
    await log_action(
        request.app.state.db,
        actor=actor_from_request(request),
        action="doctor_scan_force",
        status="started" if started else "unavailable",
    )
    return {"status": "started" if started else "unavailable"}


# ── Алерты (DASH-5) ─────────────────────────────────────────

# Максимум идентификаторов в одном подтверждении: ограничивает число
# параметров SQL-запроса (SQLITE_MAX_VARIABLE_NUMBER).
MAX_ALERT_IDS = 500

# Префиксы, с которых табличные процессоры начинают формулу (CWE-1236).
_CSV_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: Any) -> str:
    """Обезвреживает значение для CSV: формулы не должны исполняться."""
    text = "" if value is None else str(value)
    if text.startswith(_CSV_INJECTION_PREFIXES):
        return "'" + text
    return text


@router.post("/alerts/ack")
async def ack_alerts(request: Request) -> dict[str, Any]:
    """Подтверждает или снимает алерты; изменение пишется в журнал.

    Тело запроса: ``{"ids": [1, 2], "state": "acked" | "resolved"}``.
    ``state`` по умолчанию — ``acked``.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "Неверный JSON."})

    if not isinstance(body, dict):
        return JSONResponse(status_code=400, content={"detail": "Ожидался объект."})

    raw_ids = body.get("ids")
    if not isinstance(raw_ids, list) or not raw_ids:
        return JSONResponse(
            status_code=400, content={"detail": "Нужен непустой список ids."}
        )
    try:
        alert_ids = [int(value) for value in raw_ids]
    except (TypeError, ValueError):
        return JSONResponse(
            status_code=400, content={"detail": "Идентификаторы должны быть числами."}
        )

    if len(alert_ids) > MAX_ALERT_IDS:
        return JSONResponse(
            status_code=400,
            content={
                "detail": f"Слишком много идентификаторов (максимум {MAX_ALERT_IDS})."
            },
        )

    state = str(body.get("state", "acked"))
    if state not in ("acked", "resolved", "new"):
        return JSONResponse(
            status_code=400, content={"detail": f"Недопустимое состояние: {state}"}
        )

    db = request.app.state.db
    actor = actor_from_request(request)
    changed = await db.set_alerts_state(alert_ids, state, actor)
    await log_action(
        db,
        actor,
        "alert_state",
        target=",".join(str(value) for value in alert_ids[:20]),
        state=state,
        changed=changed,
    )
    return {
        "status": "ok",
        "changed": changed,
        "state": state,
        "unacked": await db.unacked_alerts_count(),
    }


@router.get("/alerts/export.csv")
async def export_alerts_csv(
    request: Request,
    uid: str | None = None,
    status: str | None = None,
    ack_status: str | None = None,
    days: int | None = Query(None, ge=1, le=365),
) -> Response:
    """Выгружает алерты в CSV с теми же фильтрами, что и страница."""
    db = request.app.state.db
    now = time.time()
    since = now - days * 86400 if days else None

    alerts = await db.list_alerts(
        limit=10000,
        offset=0,
        uid=uid,
        status=status,
        ack_status=ack_status,
        since=since,
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "id",
            "время",
            "uid",
            "пациент",
            "врач",
            "специальность",
            "клиника",
            "дата слота",
            "событие",
            "состояние",
            "подтвердил",
        ]
    )
    for alert in alerts:
        writer.writerow(
            [
                alert["id"],
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(alert["ts"])),
                _csv_safe(alert["uid"]),
                _csv_safe(alert["patient_name"]),
                _csv_safe(alert["doctor_name"]),
                _csv_safe(alert["specialty"]),
                _csv_safe(alert["clinic_name"]),
                _csv_safe(alert["slot_date"]),
                _csv_safe(alert["status"]),
                _csv_safe(alert.get("ack_status", "new")),
                _csv_safe(alert.get("acked_by", "")),
            ]
        )

    # BOM: без него Excel на Windows читает кириллицу в неверной кодировке.
    csv_body = "\ufeff" + buffer.getvalue()
    await log_action(
        db,
        actor_from_request(request),
        "alerts_export",
        target=f"rows={len(alerts)}",
    )
    return Response(
        content=csv_body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="alerts.csv"',
        },
    )


@router.get("/health")
async def liveness() -> dict[str, Any]:
    """Liveness probe — всегда 200, если процесс жив."""
    return {"status": "ok"}
