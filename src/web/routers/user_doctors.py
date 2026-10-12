"""
Врачи Mini App API (``/api/user/doctors``).

Модуль описывает пути без префикса: префикс ``/api/user`` добавляет
агрегатор :mod:`src.web.routers.user_api`. Сборка списка врачей вынесена в
:mod:`src.services.doctor_catalog`; discovery-оркестрация остаётся здесь —
``services`` не имеет права зависеть от ``handlers``.
"""

import asyncio
import datetime
import time as time_module
from typing import Any, cast

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field

from src.database.manager import DatabaseManager
from src.database.types import MonitoringEntry, PatientInfo
from src.services.doctor_catalog import (
    CatalogContext,
    DoctorCatalogQuery,
    build_doctors,
    load_monitoring,
    matching_free_tickets,
    visible_doctor_ids,
)
from src.utils.cache import get_cache_key
from src.utils.helpers import safe_name
from src.web.routers.user_common import (
    _get_api,
    _get_db,
    _get_telegram_id,
    _monitoring_id_to_parts,
)
from src.web.routers.user_slots import (
    SLOTS_REFRESH_WAIT_SECONDS,
    _await_fresh_slots,
    _clinic_slots_fresh,
    _load_cached_slots,
    _trigger_stale_clinic_slots_refresh,
)

router = APIRouter()

# Бюджеты блокирующей работы пользовательских запросов. Клиент (Mini App)
# сдаётся через 20 с, поэтому портальные операции в самом запросе ограничены:
# не уложились — отдаём то, что есть, а обновление уходит в фон.
# Талоны (T3) в первом кадре запроса не опрашиваются вовсе — читаются из кэша
# clinic_slots, поэтому отдельного бюджета слотов нет.
DISCOVERY_TIMEOUT_SECONDS = 6.0


class AddDoctorRequest(BaseModel):
    """Тело запроса на добавление врача в мониторинг."""

    clinic_id: str = Field(..., description="ID клиники")
    specialty_id: str = Field(default="", description="ID специальности (опционально)")
    doctor_id: str = Field(..., description="ID врача")
    patient_id: str = Field(..., description="ID пациента")
    doctor_name: str = Field(
        default="", description="Имя врача (опционально, из Mini App)"
    )
    specialty_name: str = Field(
        default="", description="Название специальности (опционально, из Mini App)"
    )
    date: str = Field(
        default="", description="Дата приёма в формате ДД.ММ.ГГГГ (опционально)"
    )


class ForceCheckRequest(BaseModel):
    """Тело запроса принудительной проверки слотов."""

    monitoring_id: str = Field(
        ..., description="ID мониторинга в формате {patient_id}_{doctor_id}"
    )


async def _trigger_stale_clinic_refresh(db: DatabaseManager, clinic_id: str) -> None:
    """Ставит в фон обновление реестра, если он просрочен для этой клиники (T2).

    Список врачей отдаётся из БД немедленно: портальный обход только
    ставится в очередь через ``refresh_clinic_if_stale()`` и выполняется
    фоновой задачей. Свежая клиника обхода не запускает.
    """
    from src.services.doctor_discovery import refresh_clinic_if_stale

    await refresh_clinic_if_stale(db._db, clinic_id)


def _parse_cache_status(cached_value: Any) -> tuple[str, int]:
    """Разбирает значение Redis-кэша мониторинга в (status, free_tickets).

    - Непустой list слотов → ``("slots_available", len(слоты))``
    - Пустой list или ``"NONE"`` → ``("no_slots", 0)``
    - None (ключа нет) или любой другой тип → ``("checking", 0)``
    """
    if cached_value is None:
        return ("checking", 0)
    if isinstance(cached_value, list):
        count = len(cached_value)
        return ("slots_available", count) if count > 0 else ("no_slots", 0)
    if cached_value == "NONE":
        return ("no_slots", 0)
    # Неизвестный формат (например, словарь от POST /doctors/check)
    return ("checking", 0)


def _serialize_monitoring_filter(entry: MonitoringEntry) -> dict[str, Any]:
    """Сериализует фильтр отслеживания записи мониторинга для JSON-ответа (§9.8).

    Поле ``specific_dates`` хранится в БД JSON-строкой и возвращается списком.
    Разбор делегируется ``monitor._parse_specific_dates`` — единый источник логики
    чтения фильтра, без дублирования.
    """
    from src.services.monitor import _parse_specific_dates

    return {
        "date_from": entry.get("date_from", "") or "",
        "date_to": entry.get("date_to", "") or "",
        "time_from": entry.get("time_from", "") or "",
        "time_to": entry.get("time_to", "") or "",
        "specific_dates": _parse_specific_dates(entry),
    }


@router.get("/doctors")
async def get_doctors(
    request: Request,
    patient_id: str | None = Query(None, description="Фильтр по пациенту"),
) -> dict[str, Any]:
    """Список отслеживаемых врачей со статусом слотов.

    Читает актуальный статус из Redis-кэша мониторинга (ключ
    ``mon:{telegram_id}_{p_id}_{d_id}``), заполняемого ``monitor.py``.
    При недоступности Redis — возвращает ``"checking"`` / 0.

    По каждому врачу возвращаются два счётчика: ``free_tickets`` (общий) и
    ``matching_free_tickets`` (подходящие под фильтр отслеживания, если он
    задан). Расчёт делегируется ``matching_free_tickets`` — единый
    источник логики фильтрации (§7.3).
    """
    db = _get_db(request)
    telegram_id = _get_telegram_id(request)

    user_data = await db.get_user_data(telegram_id)

    doctors_list: list[dict[str, Any]] = []
    monitoring = user_data.get("monitoring", {})

    for p_id, doctors in monitoring.items():
        # Фильтр по пациенту
        if patient_id is not None and p_id != patient_id:
            continue

        patients_dict = user_data.get("patients", {})
        p_info: PatientInfo | dict[str, Any] = patients_dict.get(p_id, {})
        patient_name = p_info.get("fio", p_id)

        for d_id, d_info in doctors.items():
            clinic_name = await db.get_clinic_name(d_info.get("clinic_id", ""))

            # Читаем актуальный статус слотов из Redis-кэша мониторинга
            cache_key = f"{telegram_id}_{p_id}_{d_id}"
            cached_value = await get_cache_key(cache_key)
            status, free_tickets = _parse_cache_status(cached_value)
            matching = await matching_free_tickets(
                telegram_id=telegram_id,
                p_id=p_id,
                d_id=d_id,
                monitoring_entry=d_info,
                free_tickets=free_tickets,
            )

            doctors_list.append(
                {
                    "monitoring_id": f"{p_id}_{d_id}",
                    "patient_id": p_id,
                    "patient_name": patient_name,
                    "doctor_id": d_id,
                    "doctor_name": safe_name(d_info.get("name", "")),
                    "specialty": d_info.get("specialty", ""),
                    "clinic_id": d_info.get("clinic_id", ""),
                    "clinic_name": clinic_name or "",
                    "status": status,
                    "free_tickets": free_tickets,
                    "matching_free_tickets": matching,
                    "last_check": None,
                    "filter": _serialize_monitoring_filter(d_info),
                }
            )

    return {"doctors": doctors_list}


async def _resolve_doctor_names(
    request: Request, body: AddDoctorRequest
) -> tuple[str, str]:
    """Разрешает имя врача и специальность: из тела либо живой lookup API."""
    doctor_name = body.doctor_name or body.doctor_id
    specialty_name = body.specialty_name or body.specialty_id

    # Если имена не переданы клиентом — делаем живой запрос к API.
    if body.doctor_name and body.specialty_name:
        return doctor_name, specialty_name

    try:
        api = _get_api(request)
        doctors = await api.fetch_all_doctors(
            specialty_id=body.specialty_id,
            patient_id=body.patient_id,
            clinic_id=body.clinic_id,
            limiter=api.limiter,
        )

        for doc in doctors:
            if str(doc.get("IdDoc", "")) == body.doctor_id:
                if not body.doctor_name:
                    doctor_name = safe_name(doc.get("Name", doctor_name))
                if not body.specialty_name:
                    specialty_name = doc.get("SpesialityName", specialty_name)
                break
    except Exception:
        # API lookup failed — используем fallback-имена
        pass

    return doctor_name, specialty_name


@router.post("/doctors/add", response_model=None)
async def add_doctor(
    request: Request,
    body: AddDoctorRequest,
) -> dict[str, Any] | JSONResponse:
    """Добавить врача в мониторинг.

    **Важно:** ``toggle_monitoring`` переключает состояние — врач будет
    добавлен, только если он ещё не отслеживается.
    """
    db = _get_db(request)
    telegram_id = _get_telegram_id(request)

    try:
        user_data = await db.get_user_data(telegram_id)

        # Проверяем, что врач ещё НЕ отслеживается
        patient_doctors = user_data.get("monitoring", {}).get(body.patient_id, {})
        if body.doctor_id in patient_doctors:
            existing = patient_doctors[body.doctor_id]
            return JSONResponse(
                status_code=409,
                content={
                    "detail": (
                        f"Врач '{existing.get('name', body.doctor_id)}' "
                        f"уже отслеживается для пациента {body.patient_id}."
                    ),
                },
            )

        doctor_name, specialty_name = await _resolve_doctor_names(request, body)
        clinic_name = await db.get_clinic_name(body.clinic_id) or body.clinic_id

        await db.toggle_monitoring(
            uid=telegram_id,
            p_id=body.patient_id,
            d_id=body.doctor_id,
            d_name=doctor_name,
            clinic_id=body.clinic_id,
            doctor_specialty=specialty_name,
            date=body.date,
        )

        return {
            "status": "added",
            "doctor_name": doctor_name,
            "specialty": specialty_name,
            "clinic_name": clinic_name,
        }

    except httpx.TimeoutException:
        logger.error(
            "Таймаут API при добавлении врача {} для пользователя {}",
            body.doctor_id,
            telegram_id,
        )
        return JSONResponse(
            status_code=504,
            content={"detail": "Таймаут при запросе к API zdrav.lenreg.ru"},
        )
    except httpx.NetworkError:
        logger.error(
            "Сетевая ошибка API при добавлении врача {} для пользователя {}",
            body.doctor_id,
            telegram_id,
        )
        return JSONResponse(
            status_code=502,
            content={"detail": "API zdrav.lenreg.ru недоступно"},
        )
    except Exception:
        logger.exception(
            "Ошибка при добавлении врача {} для пользователя {}",
            body.doctor_id,
            telegram_id,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Внутренняя ошибка сервера"},
        )


@router.delete("/doctors/{monitoring_id}", response_model=None)
async def remove_doctor(
    request: Request,
    monitoring_id: str,
) -> dict[str, Any] | JSONResponse:
    """Удалить врача из мониторинга.

    ``monitoring_id`` — строка формата ``{patient_id}_{doctor_id}``.
    """
    db = _get_db(request)
    telegram_id = _get_telegram_id(request)

    try:
        p_id, d_id = _monitoring_id_to_parts(monitoring_id)
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={"detail": "Неверный формат monitoring_id."},
        )

    user_data = await db.get_user_data(telegram_id)
    patient_doctors = user_data.get("monitoring", {}).get(p_id, {})

    if d_id not in patient_doctors:
        return JSONResponse(
            status_code=404,
            content={
                "detail": (
                    f"Врач с monitoring_id='{monitoring_id}' не найден в мониторинге."
                ),
            },
        )

    doctor_name = patient_doctors[d_id].get("name", d_id)
    clinic_id = patient_doctors[d_id].get("clinic_id", "")
    specialty = patient_doctors[d_id].get("specialty", "")

    await db.toggle_monitoring(
        uid=telegram_id,
        p_id=p_id,
        d_id=d_id,
        d_name=doctor_name,
        clinic_id=clinic_id,
        doctor_specialty=specialty,
    )

    return {
        "status": "removed",
        "doctor_name": doctor_name,
    }


async def _ensure_doctors(
    api: Any,
    db: DatabaseManager,
    doctors_dict: dict[str, Any],
    query: DoctorCatalogQuery,
) -> dict[str, Any]:
    """Возвращает врачей клиники; при пустом реестре запускает discovery.

    Discovery-ветки живут в web-слое (``services`` не зависит от ``handlers``).
    Инлайн-discovery ограничен бюджетом пользовательского запроса: не уложился —
    работа передаётся фоновому сканированию, а ответ отдаётся без врачей.
    """
    if doctors_dict:
        return doctors_dict

    logger.info(
        "Врачи для clinic_id={} не найдены в БД, запускаем on-demand discovery",
        query.clinic_id,
    )
    try:
        from src.handlers.common import _discover_doctors_on_demand

        return await asyncio.wait_for(
            _discover_doctors_on_demand(api, db, query.clinic_id, query.patient_id),
            timeout=DISCOVERY_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        # Инлайн-discovery не укладывается в бюджет пользовательского запроса:
        # передаём работу фоновому циклу и отдаём то, что есть в БД.
        logger.warning(
            "On-demand discovery для clinic_id={} не уложился в {} с — "
            "передаём фоновому сканированию",
            query.clinic_id,
            DISCOVERY_TIMEOUT_SECONDS,
        )
        _request_force_scan()
        return {}
    except Exception:
        logger.exception("Ошибка on-demand discovery для clinic_id={}", query.clinic_id)
        # Если discovery упал — возвращаем пустой список, но не 500
        return {}


def _request_force_scan() -> None:
    """Просит фоновое сканирование врачей; ошибки запроса не пробрасываются."""
    try:
        from src.services.doctor_discovery import trigger_force_scan

        trigger_force_scan()
    except Exception:
        logger.exception("Не удалось запросить фоновое сканирование врачей")


async def _load_fresh_slots(
    db: DatabaseManager,
    clinic_id: str,
    visible_ids: list[str],
    specialty_id: str | None,
    refresh: bool,
) -> tuple[dict[str, dict[str, Any]], bool]:
    """Загружает талоны клиники: из кэша либо с ожиданием свежей записи.

    Свежесть клиники решает, есть ли смысл ждать: при свежем кэше цифры уже
    готовы, и окно ожидания выжигалось бы впустую. Ждём только когда обновление
    реально поставлено в очередь, а кэш пуст или просрочен. Не дождались —
    отдаём то, что есть, без ошибки.
    """
    refresh_started = time_module.time()
    enqueued = await _trigger_stale_clinic_slots_refresh(
        db, clinic_id, visible_ids if specialty_id else None
    )
    clinic_fresh = await _clinic_slots_fresh(db, clinic_id)
    if refresh and enqueued and not clinic_fresh:
        slots_map = await _await_fresh_slots(
            db,
            clinic_id,
            visible_ids,
            since=refresh_started,
            window_seconds=SLOTS_REFRESH_WAIT_SECONDS,
        )
        clinic_fresh = await _clinic_slots_fresh(db, clinic_id)
    else:
        slots_map = await _load_cached_slots(db, clinic_id)
    return slots_map, clinic_fresh


@router.get("/doctors/available", response_model=None)
async def get_available_doctors(
    request: Request,
    clinic_id: str = Query(..., description="ID клиники (обязательный)"),
    patient_id: str = Query(..., description="ID пациента (обязательный)"),
    specialty_id: str | None = Query(
        None,
        description="ID специальности (опционально; не указан — все врачи клиники)",
    ),
    refresh: bool = Query(
        False,
        description=(
            "1 — догрузка цифр: поставить обновление талонов и подождать "
            "свежий кэш в ограниченном окне (первый кадр остаётся мгновенным)"
        ),
    ),
) -> dict[str, Any] | JSONResponse:
    """Список врачей в поликлинике (реестр из БД + талоны из кэша).

    Имена врачей и специальности — из таблицы ``doctors`` (как у бота).
    Талоны (CountFreeTicket, NearestDate) — из кэша ``clinic_slots`` (T3):
    экран не ждёт портал, а просроченный/пустой кэш обновляет фоновый цикл.
    Если врачей в БД нет — срабатывает on-demand discovery (аналогично боту).

    ``refresh=1`` — догрузка цифр без потери скорости: первый ответ отдаётся
    мгновенно как обычно, а повторный запрос с флагом дожидается свежего кэша
    в ограниченном окне (``SLOTS_REFRESH_WAIT_SECONDS``) и отдаёт обновлённые
    значения. Ожидание включается только когда обновление реально поставлено в
    очередь, а кэш клиники при этом пуст или просрочен; свежий кэш отдаётся
    сразу. Не дождались — отдаём то, что есть, без ошибки.

    Поле ``slots_fresh`` сообщает фронту, свеж ли кэш талонов клиники: ``false``
    — кэша нет или он просрочен, и нули ещё не отличить от «талонов нет»,
    поэтому шаг 3 показывает скелетон и догружает числа через ``refresh=1``.
    """
    db = _get_db(request)
    api = _get_api(request)
    telegram_id = _get_telegram_id(request)
    query = DoctorCatalogQuery(
        clinic_id=clinic_id, patient_id=patient_id, specialty_id=specialty_id
    )

    # 1. Получаем врачей из БД
    doctors_dict = await db.get_doctors_for_clinic(clinic_id)

    # 1a. Реестр клиники просрочен — список отдаётся из БД сразу, а обновление
    #     реестра уходит в фон: пользователь не ждёт портал.
    await _trigger_stale_clinic_refresh(db, clinic_id)

    # 2. Если врачей нет — on-demand discovery
    doctors_dict = await _ensure_doctors(api, db, doctors_dict, query)

    # 3. Мониторинг пользователя: отметки is_monitored и фильтры пациента
    monitoring = await load_monitoring(db, telegram_id, patient_id)

    # 4. Видимые врачи (после фильтра специальности) — только их талоны нужно
    #    обновлять точечно: K вызовов портала вместо обхода всей клиники (T4).
    visible_ids = visible_doctor_ids(doctors_dict, specialty_id)

    # 5. Талоны (CountFreeTicket/NearestDate) — ТОЛЬКО из кэша ``clinic_slots``
    #    (T3). Портал в HTTP-обработчике не опрашивается.
    slots_map, slots_fresh = await _load_fresh_slots(
        db, clinic_id, visible_ids, specialty_id, refresh
    )

    # 6. Формируем ответ: врачи из БД + талоны из кэша + флаг is_monitored
    doctors = await build_doctors(
        CatalogContext(
            doctors=doctors_dict,
            visible_ids=visible_ids,
            specialty_id=specialty_id,
            slots_map=slots_map,
            monitoring=monitoring,
            telegram_id=telegram_id,
            patient_id=patient_id,
        )
    )

    return {
        "clinic_id": clinic_id,
        "specialty_id": specialty_id,
        "slots_fresh": slots_fresh,
        "doctors": doctors,
    }


@router.get("/doctors/search", response_model=None)
async def search_doctors(
    request: Request,
    q: str = Query(
        ..., min_length=2, description="Поисковый запрос (минимум 2 символа)"
    ),
) -> dict[str, Any] | JSONResponse:
    """Поиск врачей по подстроке в имени (глобально, по всем клиникам).

    Возвращает врачей из всех клиник без информации о слотах.
    Проверка слотов через API не выполняется для скорости поиска —
    слоты запрашиваются позже, при выборе конкретного врача.
    """
    db = _get_db(request)

    try:
        doctors = await db._db.search_doctors_by_name(q, limit=20)
    except Exception:
        logger.exception("Ошибка поиска врачей по запросу '{}'", q)
        return JSONResponse(
            status_code=500,
            content={"detail": "Внутренняя ошибка сервера при поиске врачей."},
        )

    result: list[dict[str, Any]] = []
    for doc in doctors:
        result.append(
            {
                "doctor_id": doc["doctor_id"],
                "name": doc["name"],
                "specialty_name": doc.get("specialty", ""),
                "clinic_id": doc["clinic_id"],
                "clinic_name": doc.get("clinic_name", ""),
                "free_tickets": -1,
            }
        )

    return {"doctors": result}


@router.post("/doctors/check", response_model=None)
async def force_check_doctor(
    request: Request,
    body: ForceCheckRequest,
) -> dict[str, Any] | JSONResponse:
    """Принудительная проверка слотов врача (живой запрос к API zdrav.lenreg.ru).

    Делегирует в сервисный слой :func:`src.services.monitor.force_check_single_doctor`,
    который выполняет живой запрос, обновляет кэш и возвращает статус слотов.
    Уведомления Telegram при этом НЕ отправляются.
    """
    db = _get_db(request)
    api = _get_api(request)
    telegram_id = _get_telegram_id(request)

    # 1. Разбираем monitoring_id
    try:
        p_id, d_id = _monitoring_id_to_parts(body.monitoring_id)
    except ValueError:
        return JSONResponse(
            status_code=400, content={"detail": "Неверный формат monitoring_id."}
        )

    # 2. Получаем данные пользователя и проверяем, что врач отслеживается
    user_data = await db.get_user_data(telegram_id)
    patient_doctors = user_data.get("monitoring", {}).get(p_id, {})
    if d_id not in patient_doctors:
        return JSONResponse(
            status_code=404,
            content={
                "detail": (
                    f"Врач с monitoring_id='{body.monitoring_id}' "
                    f"не найден в мониторинге."
                ),
            },
        )

    d_info = patient_doctors[d_id]
    p_info = cast(PatientInfo, user_data.get("patients", {}).get(p_id, {}))

    # 3. Делегируем проверку в сервисный слой
    from src.services.monitor import force_check_single_doctor

    try:
        slots_raw, _cache_key = await force_check_single_doctor(
            api=api,
            uid=telegram_id,
            p_id=p_id,
            d_id=d_id,
            d_info=d_info,
            p_info=p_info,
            db=db,
        )
    except Exception:
        logger.exception(
            "Ошибка при проверке слотов для monitoring_id={}", body.monitoring_id
        )
        return JSONResponse(
            status_code=502,
            content={"detail": "API zdrav.lenreg.ru недоступно."},
        )

    # 4. Форматируем ответ
    doctor_name = d_info.get("name", d_id)
    clinic_id = d_info.get("clinic_id", "")
    specialty = d_info.get("specialty", "")
    clinic_name = await db.get_clinic_name(clinic_id) or clinic_id

    slots: list[dict[str, str]] = []
    if slots_raw:
        for slot_str in slots_raw:
            parts = slot_str.split(" в ", 1)
            slots.append(
                {
                    "date": parts[0].strip() if parts else slot_str,
                    "time": parts[1].strip() if len(parts) > 1 else "",
                    "clinic_id": clinic_id,
                }
            )

    total = len(slots)
    now_iso = datetime.datetime.now(datetime.UTC).isoformat()

    return {
        "status": "ok",
        "monitoring_id": body.monitoring_id,
        "doctor_name": doctor_name,
        "specialty": specialty,
        "clinic_name": clinic_name,
        "slot_status": "slots_available" if total > 0 else "no_slots",
        "total": total,
        "slots": slots,
        "checked_at": now_iso,
    }
