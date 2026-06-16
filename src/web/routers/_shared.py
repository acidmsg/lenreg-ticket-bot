"""
Общие хелперы сбора данных для роутеров дашборда.

Чистые функции, не зависящие от HTTP-контекста (Request).
Используются как api.py, так и pages.py для устранения дублирования.
"""

import time
from typing import Any

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
        monitor_loop_alive = health_metrics_module.monitor_loop_alive
        discovery_tasks_alive = health_metrics_module.discovery_tasks_alive
        healthcheck_loop_alive = health_metrics_module.healthcheck_loop_alive
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
        "monitor_loop_alive": monitor_loop_alive,
        "discovery_tasks_alive": discovery_tasks_alive,
        "healthcheck_loop_alive": healthcheck_loop_alive,
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
