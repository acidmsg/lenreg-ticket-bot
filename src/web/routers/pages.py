"""
HTML-страницы веб-дашборда.

Все эндпоинты — read-only, рендерят Jinja2-шаблоны.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from loguru import logger

from src.config import settings
from src.services.background import describe_background_tasks
from src.services.healthcheck import metrics as health_metrics
from src.services.healthcheck import metrics_lock
from src.services.log_reader import (
    LEVELS,
    LogRecord,
    collect_sources,
    default_log_path,
    read_logs,
)
from src.services.params import RESOLUTION_ORDER, collect_params
from src.services.schema_watcher import collect_schema_status
from src.services.search import search_all
from src.services.system_info import backups_reason, collect_system_snapshot
from src.services.tools import TOOLS, tool_view
from src.services.user_actions import ACTIONS, action_view
from src.web.routers._shared import (
    get_clinics_data,
    get_summary_data,
    get_users_data,
    next_scan_seconds,
    planner_status,
)

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

        # Планировщик (UX-3): полный виджет живёт на «Системе», сводка
        # показывает срок до следующего скана строкой.
        background_tasks = data.get("background_tasks") or []
        next_scan_in = next_scan_seconds(background_tasks)

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
                "planner_status": planner_status(background_tasks),
                "api_checks": data["checks_total"],
                "api_errors": data["errors_total"],
                "notifications": data["notifications_sent"],
                "doctors_discovered": data["doctors_discovered"],
                "doctors_last_scan": data["doctors_last_scan"],
                "doctor_scan_enabled": doctor_scan_enabled == "1",
                "next_scan_in": next_scan_in,
                "telegram": data["telegram"],
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
                "actions": [action_view(action) for action in ACTIONS.values()],
                "paused": False,
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
            "actions": [action_view(action) for action in ACTIONS.values()],
            "paused": await db.is_user_paused(uid),
        },
    )


# ── Логи бота (страница вместо журнала событий, 2026-09-20) ──

# Сколько строк отдаём на страницу: больше читать с диска незачем.
LOGS_PAGE_LIMIT = 200


@router.get("/logs", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    level: str | None = Query(None),
    source: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(LOGS_PAGE_LIMIT, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> HTMLResponse:
    """Логи бота: фильтр по уровню, источнику, тексту и постраничный вывод."""
    log_path = default_log_path()
    level_value = level.upper() if level else None
    if level_value not in LEVELS:
        level_value = None
    source_value = (source or "").strip() or None
    query_value = (q or "").strip() or None

    records: list[LogRecord] = []
    sources: list[str] = []
    truncated = False
    log_exists = log_path.is_file()
    log_size = 0
    if log_exists:
        # Чтение хвоста файла — в отдельном потоке: сканирование с диска (до 4 МБ)
        # не должно блокировать event loop дашборда (SSE, другие страницы).
        try:
            records, truncated = await asyncio.to_thread(
                read_logs,
                log_path,
                level=level_value,
                source=source_value,
                query=query_value,
                limit=limit,
                offset=offset,
            )
            sources = await asyncio.to_thread(collect_sources, log_path)
            log_size = log_path.stat().st_size
        except OSError:
            # Файл ротировали между is_file() и чтением — показываем пустую страницу.
            records, sources, truncated = [], [], False
            log_exists, log_size = False, 0

    templates = cast(Jinja2Templates, request.app.state.templates)
    return templates.TemplateResponse(
        request,
        "logs.html",
        {
            "records": records,
            "levels": LEVELS,
            "sources": sources,
            "level_filter": level_value or "",
            "source_filter": source_value or "",
            "query_filter": query_value or "",
            "limit": limit,
            "offset": offset,
            "truncated": truncated,
            "log_name": log_path.name,
            "log_exists": log_exists,
            "log_size": log_size,
        },
    )


# Человекочитаемые подписи действий администратора (журнал /audit-log).
AUDIT_ACTION_LABELS: dict[str, str] = {
    "login": "Вход",
    "login_failed": "Неудачный вход",
    "logout": "Выход",
    "password_change": "Смена пароля",
    "doctor_scan_toggle": "Сканирование: вкл/выкл",
    "doctor_scan_force": "Ручное сканирование",
    "doctor_scan_paused_for_restore": "Сканирование остановлено (restore)",
    "backup_run": "Ручной бэкап",
    "backup_restore_requested": "Запрошено подтверждение restore",
    "backup_restore_started": "Восстановление запущено",
    "backup_restore": "Восстановление БД",
    "backup_delete": "Удаление бэкапа",
}


def _format_audit_payload(payload_json: str) -> str:
    """Превращает payload_json записи журнала в строку «ключ=значение»."""
    try:
        data = json.loads(payload_json or "{}")
    except (TypeError, ValueError):
        return payload_json or ""
    if not isinstance(data, dict):
        return str(data)
    return ", ".join(f"{key}={value}" for key, value in data.items())


@router.get("/audit-log", response_class=HTMLResponse)
async def audit_log_page(
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    actor: str | None = Query(None),
    action: str | None = Query(None),
    search: str | None = Query(None),
    days: int | None = Query(None, ge=1, le=365),
) -> HTMLResponse:
    """Журнал действий администратора: фильтры, пагинация, детали событий."""
    db = request.app.state.db
    since = time.time() - days * 86400 if days else None

    events = await db.audit.list_events(
        limit=limit,
        offset=offset,
        actor=actor,
        action=action,
        since=since,
        search=search,
    )
    total = await db.audit.count_events(
        actor=actor, action=action, since=since, search=search
    )

    templates = cast(Jinja2Templates, request.app.state.templates)
    return templates.TemplateResponse(
        request,
        "audit_log.html",
        {
            "events": events,
            "details": {
                event["id"]: _format_audit_payload(event["payload_json"])
                for event in events
            },
            "actors": await db.audit.distinct_actors(),
            "actions": await db.audit.distinct_actions(),
            "action_labels": AUDIT_ACTION_LABELS,
            "offset": offset,
            "limit": limit,
            "total": total,
            "actor_filter": actor or "",
            "action_filter": action or "",
            "search_filter": search or "",
            "days_filter": days or "",
        },
    )


# Вкладки единого экрана настроек: смена пароля и параметры конфигурации.
SETTINGS_TABS = ("account", "params")


async def _params_context(db: Any) -> dict[str, Any]:
    """Контекст вкладки «Параметры»: группы, счётчик и порядок источников."""
    params = await collect_params(db)
    groups: dict[str, list[dict[str, object]]] = {}
    for param in params:
        groups.setdefault(str(param["group"]), []).append(param)
    return {
        "groups": groups,
        "params_total": len(params),
        "resolution_order": " → ".join(RESOLUTION_ORDER),
    }


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, tab: str = Query("account")) -> HTMLResponse:
    """Единый экран «Настройки»: вкладки «Аккаунт» и «Параметры».

    «Аккаунт» — смена пароля администратора, «Параметры» — редактор
    конфигурации из БД. Старый адрес ``/settings/params`` редиректит сюда.
    """
    active_tab = tab if tab in SETTINGS_TABS else SETTINGS_TABS[0]
    context: dict[str, Any] = {
        "username": getattr(request.state, "dashboard_user", None),
        "active_tab": active_tab,
    }
    if active_tab == "params":
        context.update(await _params_context(request.app.state.db))

    templates = cast(Jinja2Templates, request.app.state.templates)
    return templates.TemplateResponse(request, "settings.html", context)


@router.get("/settings/params", response_class=RedirectResponse)
async def params_page(request: Request) -> RedirectResponse:
    """Старый адрес «Параметров»: вкладка единого экрана ``/settings``.

    Редирект сохраняет рабочими ссылки из закладок.
    """
    return RedirectResponse(url="/settings?tab=params", status_code=302)


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
    )


# Корень проекта: src/web/routers/pages.py → четыре уровня вверх.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


@router.get("/search", response_class=HTMLResponse)
async def search_page(request: Request, q: str = "") -> HTMLResponse:
    """Глобальный поиск: uid, пациент, врач, клиника."""
    db = request.app.state.db
    results = await search_all(db, q)

    templates = cast(Jinja2Templates, request.app.state.templates)
    return templates.TemplateResponse(request, "search.html", {"results": results})


@router.get("/tools", response_class=HTMLResponse)
async def tools_page(request: Request) -> HTMLResponse:
    """Инструменты обслуживания: read-only запуск и dry-run мутаций."""
    templates = cast(Jinja2Templates, request.app.state.templates)
    return templates.TemplateResponse(
        request,
        "tools.html",
        {"tools": [tool_view(spec) for spec in TOOLS.values()]},
    )


@router.get("/system", response_class=HTMLResponse)
async def system_page(request: Request) -> HTMLResponse:
    """Системная страница: диск, БД/WAL, бэкапы, Redis, версии, расписания."""
    db = request.app.state.db
    db_path = getattr(db, "db_path", _PROJECT_ROOT / "data" / "bot.db")
    snapshot = await collect_system_snapshot(
        db,
        db_path=db_path,
        backup_dir=_PROJECT_ROOT / settings.backup_dir,
        project_root=_PROJECT_ROOT,
        uptime_seconds=health_metrics.uptime_seconds(),
    )

    # Телеметрия внешнего API переехала сюда со страницы /api-status (UX-2):
    # отдельный экран дублировал те же метрики, что уже есть на сводке.
    async with metrics_lock:
        api_ok = health_metrics.last_api_ok
        last_check = health_metrics.last_api_check_time
        check_duration = health_metrics.last_check_duration
        checks_total = health_metrics.api_checks_total
        errors_total = health_metrics.api_errors_total
        last_error = health_metrics.last_error_message
    seconds_ago = int(time.time() - last_check) if last_check else 0
    availability = 0.0
    if checks_total > 0:
        availability = round((checks_total - errors_total) / checks_total * 100, 2)

    # Планировщик (UX-3): фоновые задачи и срок до следующего скана.
    background_tasks = describe_background_tasks()

    # Статус статических эталонов схем: сверка моделей с specs/schemas/.
    try:
        schema_status = collect_schema_status()
    except Exception:
        logger.exception("Ошибка получения статуса схем API")
        schema_status = {}

    templates = cast(Jinja2Templates, request.app.state.templates)
    return templates.TemplateResponse(
        request,
        "system.html",
        {
            "system": snapshot,
            "api": {
                "ok": api_ok,
                "seconds_ago": seconds_ago,
                "duration": check_duration,
                "checks_total": checks_total,
                "errors_total": errors_total,
                "availability": availability,
                "last_error": last_error,
            },
            "schema_status": schema_status,
            "background_tasks": background_tasks,
            "next_scan_in": next_scan_seconds(background_tasks),
            "backups_reason": backups_reason(snapshot["backups"]),
        },
    )


@router.get("/api-status", response_class=RedirectResponse)
async def api_status(request: Request) -> RedirectResponse:
    """Старый адрес состояния API: телеметрия переехала на страницу «Система»."""
    return RedirectResponse(url="/system", status_code=302)
