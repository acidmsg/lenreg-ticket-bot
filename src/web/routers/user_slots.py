"""
Слоты врачей Mini App API (``/api/user/slots``).

Модуль описывает пути без префикса: префикс ``/api/user`` добавляет
агрегатор :mod:`src.web.routers.user_api`. Здесь же живут хелперы кэша
талонов клиники (T3–T4), которые использует экран «Выберите врача».
"""

import asyncio
import time as time_module
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from loguru import logger

from src.database.manager import DatabaseManager
from src.services.slot_query import (
    SlotQuery,
    fetch_live,
    format_slots,
    resolve_target,
)
from src.web.routers.user_common import (
    _build_service_error_response,
    _get_api,
    _get_db,
    _get_telegram_id,
    _monitoring_id_to_parts,
)
from src.web.types import PreheatResponse, UserSlotsResponse

router = APIRouter()

# Догрузка цифр без потери скорости (шаг 3, `refresh=1`). Первый ответ экрана
# остаётся мгновенным; повторный запрос с `refresh=1` ждёт свежий кэш талонов
# ограниченное окно, чтобы фронт дорисовал числа без действий пользователя.
# Окно мало́ и не блокирует UI: не дождались — отдаём то, что есть, без ошибок.
SLOTS_REFRESH_WAIT_SECONDS = 2.5
SLOTS_REFRESH_POLL_SECONDS = 0.5


async def _trigger_stale_clinic_slots_refresh(
    db: DatabaseManager, clinic_id: str, doctor_ids: list[str] | None = None
) -> bool:
    """Ставит в фон обновление талонов, если кэш просрочен или пуст (T3–T4).

    Экран «Выберите врача» отдаёт талоны из БД немедленно: портальный обход
    только ставится в очередь через ``refresh_clinic_slots_if_stale()`` и
    выполняется фоновой задачей ``clinic_slots_refresh``. Свежий кэш обхода не
    запускает. ``doctor_ids`` — врачи, видимые на экране после фильтра
    специальности: при непустом кэше обновляются точечно только они; ``None`` —
    полный batch клиники (bootstrap-путь).

    Returns:
        True — обновление поставлено в очередь (есть чего ждать);
        False — кэш свежий или очередь недоступна.
    """
    from src.services.doctor_discovery import refresh_clinic_slots_if_stale

    return await refresh_clinic_slots_if_stale(db._db, clinic_id, doctor_ids=doctor_ids)


def _index_cached_slots(
    cached: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Индексирует строки кэша талонов по ``doctor_id`` для ответа API.

    Пустая строка ``nearest_date`` в кэше означает «даты нет»; в ответе API
    это ``null``, поэтому приводим к ``None`` (контракт ответа не меняется).
    """
    return {
        row["doctor_id"]: {
            "free_tickets": int(row.get("free_tickets", 0)),
            "nearest_date": row.get("nearest_date") or None,
        }
        for row in cached
    }


async def _load_cached_slots(
    db: DatabaseManager, clinic_id: str
) -> dict[str, dict[str, Any]]:
    """Читает талоны клиники из кэша ``clinic_slots``, индексируя по doctor_id."""
    cached = await db.get_clinic_slots(clinic_id)
    return _index_cached_slots(cached)


async def _clinic_slots_fresh(db: DatabaseManager, clinic_id: str) -> bool:
    """Свеж ли кэш талонов клиники целиком (шаг 3, скелетон).

    Признак для фронта: пока он ``False``, список рисуется скелетоном, потому
    что нули кэша ещё нельзя отличить от «талонов нет». Свежесть — на уровне
    КЛИНИКИ: кэш ``clinic_slots`` не пуст и ``max(updated_at)`` в пределах TTL
    ``slot_cache_ttl_minutes``.

    Отсутствие записи у отдельного врача — честный ноль («талонов нет»), а не
    несвежесть: batch-обход ``sync_clinic_slots`` проходит клинику целиком и
    записывает всех, кому портал отдал талоны. Точечный нюанс T4 (обход одной
    специальности) для пользовательского флага не применяется.

    Ошибка чтения настроек/БД — ``False``: лишний скелетон безопаснее, чем
    выдача нулей под видом свежих данных.
    """
    from src.services.doctor_discovery import clinic_slots_are_stale

    try:
        stale = await clinic_slots_are_stale(db._db, clinic_id)
    except Exception:
        logger.exception(
            "Не удалось определить свежесть талонов clinic_id={}", clinic_id
        )
        return False
    return not stale


async def _await_fresh_slots(
    db: DatabaseManager,
    clinic_id: str,
    doctor_ids: list[str],
    *,
    since: float,
    window_seconds: float,
) -> dict[str, dict[str, Any]]:
    """Ждёт в ограниченном окне появления свежего кэша талонов (шаг 3).

    Повторный запрос с ``refresh=1`` не должен отдавать нули, пока фон ещё не
    записал свежие талоны: ждём запись кэша с ``updated_at >= since`` (``since``
    — момент постановки фонового обновления). Как только свежая запись
    появилась хотя бы по одному видимому врачу — отдаём весь текущий кэш.

    Окно ограничено ``window_seconds`` секунд, опрос — ``SLOTS_REFRESH_POLL_SECONDS``.
    Не дождались — возвращаем то, что есть в кэше (возможно, пусто): никаких
    ошибок и без блокировки UI дольше окна.

    Args:
        db: Менеджер БД (кэш ``clinic_slots``).
        clinic_id: ID клиники.
        doctor_ids: Видимые врачи; пустой список — любой врач клиники.
        since: Момент постановки фонового обновления (``time.time()``).
        window_seconds: Максимальное время ожидания, в секундах.
    """
    wanted = {str(d) for d in doctor_ids}
    deadline = time_module.time() + window_seconds
    cached = await db.get_clinic_slots(clinic_id)
    while True:
        fresh = [
            row
            for row in cached
            if float(row.get("updated_at") or 0) >= since
            and (not wanted or str(row.get("doctor_id")) in wanted)
        ]
        if fresh or time_module.time() >= deadline:
            return _index_cached_slots(cached)
        remaining = deadline - time_module.time()
        await asyncio.sleep(min(SLOTS_REFRESH_POLL_SECONDS, max(remaining, 0.0)))
        cached = await db.get_clinic_slots(clinic_id)


def _parse_monitoring_query(monitoring_id: str) -> SlotQuery | None:
    """Строит запрос слотов по ``monitoring_id``; ``None`` — неверный формат."""
    try:
        p_id, d_id = _monitoring_id_to_parts(monitoring_id)
    except ValueError:
        return None
    return SlotQuery(monitoring_id=monitoring_id, patient_id=p_id, doctor_id=d_id)


@router.get("/slots", response_model=None)
async def get_slots(
    request: Request,
    monitoring_id: str | None = Query(
        None, description="ID мониторинга: {patient_id}_{doctor_id}"
    ),
    clinic_id: str | None = Query(None, description="ID клиники (режим прямой записи)"),
    doctor_id: str | None = Query(None, description="ID врача (режим прямой записи)"),
    patient_id: str | None = Query(
        None, description="ID пациента (режим прямой записи)"
    ),
) -> UserSlotsResponse | JSONResponse:
    """Свободные слоты врача: по мониторингу либо для прямой записи.

    Два режима: ``monitoring_id`` (врач из мониторинга пользователя) либо тройка
    ``clinic_id`` + ``doctor_id`` + ``patient_id`` — без записи мониторинга
    (сценарий «Записаться»). В режиме тройки пациент обязан принадлежать
    текущему пользователю, иначе 403 (IDOR).
    """
    db = _get_db(request)
    api = _get_api(request)
    telegram_id = _get_telegram_id(request)

    user_data = await db.get_user_data(telegram_id)

    if monitoring_id and clinic_id and doctor_id and patient_id:
        return JSONResponse(
            status_code=400,
            content={
                "detail": (
                    "Укажите либо monitoring_id, либо clinic_id + doctor_id + "
                    "patient_id."
                ),
            },
        )

    if monitoring_id:
        query = _parse_monitoring_query(monitoring_id)
        if query is None:
            return JSONResponse(
                status_code=400,
                content={"detail": "Неверный формат monitoring_id."},
            )
    elif clinic_id and doctor_id and patient_id:
        query = SlotQuery(
            clinic_id=clinic_id, doctor_id=doctor_id, patient_id=patient_id
        )
    else:
        return JSONResponse(
            status_code=400,
            content={
                "detail": (
                    "Укажите monitoring_id либо clinic_id + doctor_id + patient_id."
                ),
            },
        )

    target = await resolve_target(db, user_data, telegram_id, query)
    if target.error_status is not None:
        return JSONResponse(
            status_code=target.error_status,
            content={"detail": target.error_detail},
        )

    clinic_name = await db.get_clinic_name(target.clinic_id) or target.clinic_id
    live = await fetch_live(api, target)
    if live.error_status is not None:
        if live.error_code == "internal":
            return JSONResponse(
                status_code=500,
                content={"detail": "Внутренняя ошибка сервера"},
            )
        return _build_service_error_response(live.error_status, live.error_code)

    slots = format_slots(live.slots_result, target.clinic_id)
    return {
        "monitoring_id": target.monitoring_id,
        "doctor_name": target.doctor_name,
        "specialty": target.specialty,
        "clinic_name": clinic_name,
        "slots": slots,
        "total": len(slots),
    }


@router.post("/clinics/{clinic_id}/slots/preheat", response_model=None)
async def preheat_clinic_slots(
    request: Request,
    clinic_id: str,
) -> PreheatResponse:
    """Предпрогрев талонов клиники при её выборе (шаг «Выбор поликлиники»).

    «Выстрелил-и-забыл»: сигнал только ставит обновление талонов клиники в
    фоновую очередь (``refresh_clinic_slots_if_stale`` без списка врачей —
    полный batch клиники), а ответ отдаётся сразу. Свежий кэш обхода не
    запускает и не тратит бюджет портала зря. Портал в обработчике не
    опрашивается, поэтому выбор клиники не тормозит.

    Цель — к моменту отрисовки шага «Выберите врача» цифры уже были тёплыми:
    экран дорисовывает их через ``refresh=1`` без действий пользователя.
    """
    db = _get_db(request)
    await _trigger_stale_clinic_slots_refresh(db, clinic_id)
    return {"status": "ok", "clinic_id": clinic_id}
