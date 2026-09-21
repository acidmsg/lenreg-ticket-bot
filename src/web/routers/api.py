"""
JSON API веб-дашборда.

Эндпоинты возвращают JSON-ответы для дашборда и Mini App.
"""

import asyncio
import csv
import io
from typing import Annotated, Any, cast

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

from src.services.audit import actor_from_request, log_action
from src.services.doctor_discovery import trigger_force_scan
from src.services.log_reader import (
    LEVELS,
    default_log_path,
    read_logs,
    read_tail,
)
from src.services.params import (
    RESOLUTION_ORDER,
    ParamError,
    collect_params,
    set_param,
)
from src.services.search import search_all
from src.services.tools import TOOLS, run_tool, tool_view
from src.services.user_actions import ACTIONS, action_view, run_action
from src.web.routers._shared import (
    get_summary_data,
    get_users_data,
)

router = APIRouter()


@router.get("/dashboard/summary")
async def api_summary(request: Request) -> dict[str, Any]:
    """JSON-сводка состояния системы."""
    db = request.app.state.db
    pm = request.app.state.prometheus_metrics

    data = await get_summary_data(db, pm)
    stats = data["stats"]
    telegram = data["telegram"]

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
        "telegram_status": {
            "accessible": telegram["api_ok"],
            "mode": telegram["mode"],
            "mode_label": telegram["mode_label"],
            "last_check_seconds_ago": telegram["last_check_seconds_ago"],
            "latency_ms": telegram["latency_ms"],
            "queue_depth": telegram["queue_depth"],
            "queue_peak": telegram["queue_peak"],
            "rate_limit": telegram["rate_limit"],
            "sends_total": telegram["sends_total"],
            "send_errors_total": telegram["send_errors_total"],
            "retry_after_total": telegram["retry_after_total"],
            # Готовые строки для фолбэка живого обновления: форматирование живёт
            # в telegram_health, а не дублируется в JS (как mode_label выше).
            "api_health": telegram["api_health"],
            "last_check": telegram["last_check"],
            "latency": telegram["latency"],
            "queue": telegram["queue"],
            "sends": telegram["sends"],
            "retry_after": telegram["retry_after"],
        },
        "background_tasks": {
            task["name"]: task["health"] for task in data["background_tasks"]
        },
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


# Префиксы, с которых табличные процессоры начинают формулу (CWE-1236).
_CSV_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_response(filename: str, rows: list[list[str]]) -> Response:
    """Собирает CSV-ответ с BOM (Excel корректно читает кириллицу).

    Args:
        filename: Имя файла в Content-Disposition.
        rows: Строки таблицы, первая — заголовок.

    Returns:
        Ответ с телом CSV.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerows(rows)
    return Response(
        content="\ufeff" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _csv_safe(value: Any) -> str:
    """Обезвреживает значение для CSV: формулы не должны исполняться."""
    text = "" if value is None else str(value)
    if text.startswith(_CSV_INJECTION_PREFIXES):
        return "'" + text
    return text


def _log_rows_response(
    request: Request,
    records: list[Any],
    offset: int | None,
    rotated: bool,
) -> HTMLResponse:
    """Отдаёт строки логов частичным шаблоном: одна разметка на страницу и динамику."""
    templates = cast(Jinja2Templates, request.app.state.templates)
    response = templates.TemplateResponse(
        request, "_log_rows.html", {"records": records}
    )
    if offset is not None:
        response.headers["X-Log-Offset"] = str(offset)
    response.headers["X-Log-Rotated"] = "1" if rotated else "0"
    return response


def _log_filters(
    level: str | None, source: list[str] | None, q: str | None
) -> tuple[str | None, list[str], str | None]:
    """Приводит параметры фильтра к виду, который понимает читатель логов."""
    level_value = level.upper() if level else None
    if level_value not in LEVELS:
        level_value = None
    sources = [item.strip() for item in (source or []) if item.strip()]
    return level_value, sources, (q or "").strip() or None


@router.get("/logs/rows")
async def api_logs_rows(
    request: Request,
    level: str | None = None,
    source: Annotated[list[str] | None, Query()] = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> HTMLResponse:
    """Следующая порция логов для динамической подгрузки списка.

    Разметка приходит тем же частичным шаблоном, что и на странице, поэтому
    подгруженные записи не отличаются от первого экрана.
    """
    log_path = default_log_path()
    level_value, sources, query_value = _log_filters(level, source, q)
    records: list[Any] = []
    log_size: int | None = None
    if log_path.is_file():
        try:
            records, _ = await asyncio.to_thread(
                read_logs,
                log_path,
                level=level_value,
                sources=sources or None,
                query=query_value,
                limit=max(1, min(limit, 500)),
                offset=max(0, offset),
            )
            log_size = log_path.stat().st_size
        except OSError:
            records = []
    return _log_rows_response(request, records, log_size, False)


@router.get("/logs/tail")
async def api_logs_tail(
    request: Request,
    after: int | None = None,
    level: str | None = None,
    source: Annotated[list[str] | None, Query()] = None,
    q: str | None = None,
) -> HTMLResponse:
    """Новые строки лога для режима «следить» (HTML-фрагмент строк).

    ``after`` — байтовая позиция, с которой дочитываем файл (отрицательная
    считается началом слежения). Ротация сообщается заголовком
    ``X-Log-Rotated``, позиция для следующего запроса — ``X-Log-Offset``.
    Фильтры те же, что на странице: слежение не подмешивает лишние строки.
    """
    log_path = default_log_path()
    level_value, sources, query_value = _log_filters(level, source, q)
    if not log_path.is_file():
        return _log_rows_response(request, [], 0, False)
    try:
        records, offset, rotated = await asyncio.to_thread(
            read_tail,
            log_path,
            after_offset=after,
            level=level_value,
            sources=sources or None,
            query=query_value,
        )
    except OSError:
        # Файл ротировали между is_file() и чтением — слежение начнётся заново.
        return _log_rows_response(request, [], 0, True)
    # Строки кладутся сверху, поэтому отдаём их в порядке «новые первыми».
    return _log_rows_response(request, list(reversed(records)), offset, rotated)


@router.get("/dashboard/search")
async def api_search(request: Request) -> dict[str, Any]:
    """Глобальный поиск: uid, пациент, врач, клиника."""
    query = request.query_params.get("q", "")
    return await search_all(request.app.state.db, query)


@router.get("/dashboard/export/users.csv")
async def api_export_users(request: Request) -> Response:
    """Выгрузка пользователей с числом пациентов и цепочек мониторинга."""
    db = request.app.state.db
    users = get_users_data(db)
    rows = [["uid", "пациентов", "цепочек мониторинга"]]
    for user in users:
        rows.append(
            [
                _csv_safe(user.get("uid", "")),
                _csv_safe(user.get("patients_count", 0)),
                _csv_safe(user.get("monitoring_count", 0)),
            ]
        )
    await log_action(
        db,
        actor_from_request(request),
        "export_users",
        target=f"rows={len(rows) - 1}",
    )
    return _csv_response("users.csv", rows)


@router.get("/dashboard/export/clinics.csv")
async def api_export_clinics(request: Request) -> Response:
    """Выгрузка клиник с городом и типом."""
    db = request.app.state.db
    # Пустой шаблон LIKE (``%%``) возвращает все клиники: тот же репозиторий,
    # что и у поиска, без дублирования SQL.
    clinics = await db.search_clinics("", limit=5000)
    rows = [["clinic_id", "название", "город", "тип"]]
    for clinic in clinics:
        rows.append(
            [
                _csv_safe(clinic["clinic_id"]),
                _csv_safe(clinic["name"]),
                _csv_safe(clinic["city"]),
                _csv_safe(clinic["type"]),
            ]
        )
    await log_action(
        db,
        actor_from_request(request),
        "export_clinics",
        target=f"rows={len(rows) - 1}",
    )
    return _csv_response("clinics.csv", rows)


# ── Действия над пользователем (DASH-8) ─────────────────────


@router.get("/dashboard/user-actions/{uid}")
async def api_user_actions(request: Request, uid: str) -> dict[str, Any]:
    """Список доступных действий над пользователем."""
    return {
        "uid": uid,
        "actions": [action_view(action) for action in ACTIONS.values()],
    }


@router.post("/dashboard/user-actions/{uid}/{action}")
async def api_user_action(request: Request, uid: str, action: str) -> dict[str, Any]:
    """Выполняет действие над пользователем; без confirm — не выполняет.

    Тело: ``{"params": {...}, "confirm": bool}``.
    """
    if action not in ACTIONS:
        return JSONResponse(status_code=404, content={"detail": "Действие не найдено."})

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "Неверный JSON."})
    if not isinstance(body, dict):
        return JSONResponse(status_code=400, content={"detail": "Ожидался объект."})

    raw_params = body.get("params") or {}
    if not isinstance(raw_params, dict):
        return JSONResponse(
            status_code=400, content={"detail": "params должен быть объектом."}
        )
    params = {str(key): str(value) for key, value in raw_params.items()}

    db = request.app.state.db
    try:
        result = await run_action(
            db,
            uid,
            action,
            params,
            confirm=bool(body.get("confirm")),
            actor=actor_from_request(request),
        )
    except KeyError:
        return JSONResponse(status_code=404, content={"detail": "Действие не найдено."})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    return JSONResponse(status_code=200, content=result)


# ── Инструменты обслуживания (DASH-7) ───────────────────────


@router.get("/tools")
async def api_tools(request: Request) -> dict[str, Any]:
    """Список инструментов: имя, вид, параметры."""
    return {"tools": [tool_view(spec) for spec in TOOLS.values()]}


@router.post("/tools/{name}/run")
async def api_tool_run(request: Request, name: str) -> dict[str, Any]:
    """Запускает инструмент; мутирующие — только с подтверждением.

    Тело: ``{"params": {...}, "apply": bool, "confirm": bool}``.
    """
    if name not in TOOLS:
        return JSONResponse(
            status_code=404, content={"detail": "Инструмент не найден."}
        )

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "Неверный JSON."})
    if not isinstance(body, dict):
        return JSONResponse(status_code=400, content={"detail": "Ожидался объект."})

    raw_params = body.get("params") or {}
    if not isinstance(raw_params, dict):
        return JSONResponse(
            status_code=400, content={"detail": "params должен быть объектом."}
        )
    params = {str(key): str(value) for key, value in raw_params.items()}

    db = request.app.state.db
    db_path = getattr(db, "db_path", "data/bot.db")
    try:
        result = await run_tool(
            db,
            name,
            params,
            apply=bool(body.get("apply")),
            confirm=bool(body.get("confirm")),
            actor=actor_from_request(request),
            db_path=db_path,
        )
    except KeyError:
        return JSONResponse(
            status_code=404, content={"detail": "Инструмент не найден."}
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    status_code = 200 if result["status"] in {"ok", "confirm_required"} else 502
    return JSONResponse(status_code=status_code, content=result)


@router.get("/health")
async def liveness() -> dict[str, Any]:
    """Liveness probe — всегда 200, если процесс жив."""
    return {"status": "ok"}
