"""
Общие хелперы сбора данных для роутеров дашборда.

Чистые функции, не зависящие от HTTP-контекста (Request).
Используются как api.py, так и pages.py для устранения дублирования.
"""

import time
from typing import Any

from src.config import settings
from src.services.background import describe_background_tasks
from src.services.healthcheck import metrics as health_metrics_module
from src.services.healthcheck import metrics_lock


async def get_summary_data(
    db: Any,
    prometheus_metrics: Any,
) -> dict[str, Any]:
    """Сбор сырых данных для сводки дашборда.

    Returns:
        Словарь с агрегированной статистикой, метриками здоровья API,
        данными doctor_discovery и последними алертами.
    """
    stats = await db.get_total_stats()
    user_stats = db.get_user_statistics()
    active_monitorings = user_stats["active_monitorings"]
    recent_alerts = await db.get_all_monitoring_logs(limit=10, offset=0)

    async with metrics_lock:
        uptime_str = health_metrics_module.uptime_str()
        uptime_sec = health_metrics_module.uptime_seconds()
        api_ok = health_metrics_module.last_api_ok
        last_check = health_metrics_module.last_api_check_time
        checks_total = health_metrics_module.api_checks_total
        errors_total = health_metrics_module.api_errors_total
        notifications_sent = health_metrics_module.monitoring_notifications_sent

    seconds_ago = int(time.time() - last_check) if last_check else 0
    availability = 0.0
    if checks_total > 0:
        availability = round((checks_total - errors_total) / checks_total * 100, 2)

    doctors_discovered = int(prometheus_metrics._doctors_discovered._value.get())
    doctors_last_scan = int(prometheus_metrics.doctors_last_scan_timestamp._value.get())

    return {
        "stats": stats,
        "active_monitorings": active_monitorings,
        "recent_alerts": recent_alerts,
        "uptime_str": uptime_str,
        "uptime_sec": uptime_sec,
        "api_ok": api_ok,
        "last_check": last_check,
        "checks_total": checks_total,
        "errors_total": errors_total,
        "background_tasks": describe_background_tasks(),
        "notifications_sent": notifications_sent,
        "seconds_ago": seconds_ago,
        "availability": availability,
        "doctors_discovered": doctors_discovered,
        "doctors_last_scan": doctors_last_scan,
    }


def get_users_data(
    db: Any,
    limit: int | None = None,
    offset: int = 0,
    search: str | None = None,
) -> list[dict[str, Any]]:
    """Сбор данных пользователей из БД.

    Args:
        db: Объект базы данных.
        limit: Максимальное количество записей (None — без ограничения).
        offset: Смещение для пагинации.
        search: Строка поиска по uid (None — без фильтрации).

    Returns:
        Список словарей с полями uid, patient_count, monitoring_count, last_activity_ts.
    """
    db_data = db.data

    users: list[dict[str, Any]] = []
    for uid, u_info in db_data.items():
        # Фильтрация по поиску
        if search and search.lower() not in uid.lower():
            continue

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

    # Пагинация
    if offset:
        users = users[offset:]
    if limit is not None:
        users = users[:limit]

    return users


def render_partial(templates: Any, name: str, **context: Any) -> str:
    """Рендерит Jinja2-партиал в строку.

    Используется SSE-потоком: блоки сводки отдаются уже готовым HTML, чтобы
    разметка жила в шаблонах (один источник правды), а не дублировалась в JS.

    Args:
        templates: Объект ``Jinja2Templates`` из ``app.state.templates``.
        name: Имя шаблона-партиала.
        **context: Контекст рендера.

    Returns:
        HTML-строка партиала.
    """
    env = templates.env
    ctx: dict[str, Any] = {"macros": env.get_template("macros.html").module}
    ctx.update(context)
    return env.get_template(name).render(**ctx)


def _format_ts_hms(ts: int) -> str:
    """Форматирует Unix-время в ЧЧ:ММ:СС (пустая строка для отсутствующего)."""
    if not ts:
        return "не было"
    return time.strftime("%H:%M:%S", time.localtime(ts))


async def build_live_payload(
    db: Any,
    prometheus_metrics: Any,
    templates: Any,
) -> dict[str, Any]:
    """Собирает снапшот для SSE-обновления страниц дашборда.

    Returns:
        Словарь с готовыми к вставке строками (``display``), флагами для
        бейджей (``flags``) и перерендеренными HTML-блоками задач и алертов.
    """
    data = await get_summary_data(db, prometheus_metrics)
    stats = data["stats"]

    async with metrics_lock:
        api_health = health_metrics_module.api_health_str()

    return {
        "ts": int(time.time()),
        "interval": max(2, int(settings.DASHBOARD_STREAM_INTERVAL)),
        "display": {
            "uptime": data["uptime_str"],
            "total_users": str(stats["total_users"]),
            "total_patients": str(stats["total_patients"]),
            "total_monitored_doctors": str(stats["total_monitored_doctors"]),
            "active_monitorings": str(data["active_monitorings"]),
            "doctors_discovered": str(data["doctors_discovered"]),
            "doctors_last_scan": _format_ts_hms(data["doctors_last_scan"]),
            "api_health": api_health,
            "api_last_check": (
                f"{data['seconds_ago']} с назад" if data["last_check"] else "—"
            ),
            "api_checks": str(data["checks_total"]),
            "api_errors": str(data["errors_total"]),
            "api_availability": f"{data['availability']} %",
            "notifications": str(data["notifications_sent"]),
        },
        "flags": {"api_ok": bool(data["api_ok"])},
        "tasks_html": render_partial(
            templates,
            "_background_tasks.html",
            background_tasks=data["background_tasks"],
        ),
        "alerts_html": render_partial(
            templates, "_alerts.html", recent_alerts=data["recent_alerts"]
        ),
    }


async def get_clinics_data(db: Any) -> list[dict[str, Any]]:
    """Сбор данных клиник из БД.

    Returns:
        Список словарей с полями clinic_id, name, type, city, is_active, doctor_count.
    """
    clinics = await db._db.get_active_clinics()

    result: list[dict[str, Any]] = []
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

    return result
