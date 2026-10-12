"""
Пациенты Mini App API (``/api/user/patients``).

Модуль описывает пути без префикса: префикс ``/api/user`` добавляет
агрегатор :mod:`src.web.routers.user_api`.

Доменная валидация правки карточки вынесена в
:mod:`src.services.patient_profile`; повторная верификация пациента через
внешний API остаётся здесь (web-слой).
"""

import asyncio
import datetime
from typing import Any, cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field

from src.database.manager import DatabaseManager
from src.database.types import PatientInfo
from src.services.patient_check import (
    CHECK_STATUS_INVALID,
    cache_key,
    check_patient_status,
    clinic_ids_for,
)
from src.services.patient_profile import (
    PatientUpdatePlan,
    build_card,
    build_update_plan,
)
from src.utils.cache import delete_check_cache, get_check_cache
from src.web.routers.user_common import (
    _get_api,
    _get_db,
    _get_telegram_id,
    _normalize_bday_display,
    _serialize_patients,
)

router = APIRouter()


class PatientUpdateRequest(BaseModel):
    """Тело запроса на правку карточки пациента (P3-EDIT).

    Незаданные поля не меняются. Правка ФИО или даты рождения запускает
    обязательную повторную верификацию через ``check_patient``.
    """

    full_name: str | None = Field(None, description="ФИО: три слова")
    birth_date: str | None = Field(None, description="Дата рождения ДД.ММ.ГГГГ")
    alias: str | None = Field(None, description="Псевдоним (пусто — удалить)")


class AddPatientRequest(BaseModel):
    """Тело запроса на добавление пациента."""

    full_name: str = Field(..., description="ФИО пациента (три слова через пробел)")
    birth_date: str = Field(..., description="Дата рождения в формате ДД.ММ.ГГГГ")
    alias: str = Field(default="", description="Псевдоним пациента (необязательно)")
    policy: str = Field(default="", description="Номер полиса ОМС (необязательно)")


async def _find_patient_id(
    api,
    fio: str,
    birth_date: datetime.date,
    db,
    telegram_id: str,
) -> tuple[str | None, str | None]:
    """Поиск пациента с перебором clinic_id и защитой от зависания.

    Возвращает (patient_id | None, error_detail | None).
    Делегирует в :func:`src.services.patient_discovery.find_patient_across_clinics`.
    """
    from src.services.patient_discovery import find_patient_across_clinics

    date_str = birth_date.isoformat()
    status, detail = await find_patient_across_clinics(fio, date_str, api, db)

    if status == "found":
        return (detail, None)  # detail = patient_id
    elif status == "error":
        return (None, detail)  # detail = сообщение об ошибке
    else:  # "not_found"
        return (None, detail)


@router.get("/patients")
async def get_patients(request: Request) -> dict[str, Any]:
    """Список пациентов пользователя.

    К каждому пациенту добавляется флаг ``needs_check`` (P3-ACTUAL): он берётся
    только из кэша проверок (P3-VERIFY) и не вызывает внешний API, поэтому
    список остаётся дешёвым.
    """
    db = _get_db(request)
    telegram_id = _get_telegram_id(request)

    user_data = await db.get_user_data(telegram_id)

    patients_dict = user_data.get("patients", {})
    patients_list = _serialize_patients(patients_dict)
    for entry in patients_list:
        p_id = str(entry["patient_id"])
        entry["needs_check"] = await _patient_needs_check(
            telegram_id, p_id, patients_dict.get(p_id, {})
        )

    return {"patients": patients_list}


async def _patient_needs_check(
    uid: str, p_id: str, p_info: PatientInfo | dict[str, Any]
) -> bool:
    """True, если хотя бы для одной клиники пациента есть кэш «не найден»."""
    for clinic_id in clinic_ids_for(p_info):
        key = cache_key(uid, p_id, clinic_id)
        if await get_check_cache(key) == CHECK_STATUS_INVALID:
            return True
    return False


@router.post("/patients/{patient_id}/check", response_model=None)
async def check_patient(
    request: Request,
    patient_id: str,
) -> dict[str, Any] | JSONResponse:
    """Проверить, числится ли пациент в клиниках (P3-ACTUAL).

    Единый сервис с кэшем (P3-VERIFY): повторные вызовы не бьют по внешнему API.
    Статус ``invalid`` означает «пациент не найден» — клиент показывает бейдж
    «требует проверки» и предлагает исправить карточку.
    """
    db = _get_db(request)
    api = _get_api(request)
    telegram_id = _get_telegram_id(request)

    user_data = await db.get_user_data(telegram_id)
    p_info = user_data.get("patients", {}).get(patient_id)
    if p_info is None:
        return JSONResponse(
            status_code=404,
            content={"detail": "Пациент не найден."},
        )

    status = await check_patient_status(telegram_id, patient_id, p_info, api, db)
    return {
        "patient_id": patient_id,
        "status": status,
        "needs_check": status == CHECK_STATUS_INVALID,
    }


@router.post("/patients/add", response_model=None)
async def add_patient(
    request: Request,
    body: AddPatientRequest,
) -> dict[str, Any] | JSONResponse:
    """Добавить нового пациента.

    Логика поиска пациента (аналогична ``process_bday`` в registration.py):
    1. Сначала поиск в клинике по умолчанию (DEFAULT_CLINIC_ID).
    2. Затем глобальный поиск (пустая строка clinic_id).
    3. Затем перебор всех активных clinic_id из БД.
    """
    db = _get_db(request)
    api = _get_api(request)
    telegram_id = _get_telegram_id(request)

    # Валидация ФИО (три слова)
    fio = body.full_name.strip()
    parts = [p for p in fio.split() if p]
    if len(parts) != 3:
        return JSONResponse(
            status_code=400,
            content={
                "detail": "ФИО должно состоять из трёх слов: Фамилия Имя Отчество"
            },
        )

    # Парсинг даты рождения
    try:
        bday_date = datetime.datetime.strptime(
            body.birth_date.strip(), "%d.%m.%Y"
        ).date()
        if not (datetime.date(1900, 1, 1) <= bday_date <= datetime.date.today()):
            raise ValueError("Дата вне допустимого диапазона")
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={
                "detail": (
                    "Неверный формат даты рождения. "
                    "Ожидается ДД.ММ.ГГГГ (например, 01.01.1990)"
                ),
            },
        )

    # Поиск пациента с таймаутом
    try:
        p_id, last_err = await asyncio.wait_for(
            _find_patient_id(api, fio, bday_date, db, telegram_id),
            timeout=15.0,
        )
    except TimeoutError:
        logger.error("Поиск пациента '{}' превысил таймаут 15с", fio)
        return JSONResponse(
            status_code=504,
            content={
                "detail": (
                    "Поиск пациента занял слишком много времени. Попробуйте позже."
                ),
            },
        )

    if p_id is None:
        if last_err == "api-timeout":
            return JSONResponse(
                status_code=504,
                content={"detail": "Сервер zdrav.lenreg.ru не отвечает."},
            )
        # Все clinic_id перебраны, пациент не найден
        return JSONResponse(
            status_code=404,
            content={
                "detail": last_err or "Пациент не найден ни в одной клинике.",
            },
        )

    # Проверка на дубликат
    user_data = await db.get_user_data(telegram_id)
    if p_id in user_data.get("patients", {}):
        existing = user_data["patients"][p_id]
        return JSONResponse(
            status_code=409,
            content={
                "detail": (
                    f"Пациент '{existing.get('fio', p_id)}' уже добавлен "
                    f"(patient_id={p_id})."
                ),
            },
        )

    # Добавление пациента
    bday_str = bday_date.strftime("%d.%m.%Y")
    p_info: PatientInfo = {
        "fio": fio,
        "bday": bday_str,
    }
    alias = body.alias.strip()
    if alias:
        p_info["alias"] = alias

    try:
        await db.add_patient(uid=telegram_id, p_id=p_id, p_info=p_info)
    except Exception:
        logger.exception(
            "Ошибка сохранения пациента p_id={} для пользователя {}",
            p_id,
            telegram_id,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Ошибка при сохранении пациента."},
        )

    return {
        "status": "added",
        "patient_id": p_id,
        "fio": fio,
    }


@router.delete("/patients/{patient_id}", response_model=None)
async def delete_patient(
    request: Request,
    patient_id: str,
) -> dict[str, Any] | JSONResponse:
    """Удалить пациента из списка отслеживаемых."""
    db = _get_db(request)
    telegram_id = _get_telegram_id(request)

    user_data = await db.get_user_data(telegram_id)
    if patient_id not in user_data.get("patients", {}):
        return JSONResponse(
            status_code=404,
            content={"detail": "Пациент не найден."},
        )

    await db.delete_patient(telegram_id, patient_id)
    # NOTE: CodeQL false positive (py/clear-text-logging-sensitive-data).
    # ID маскированы до последних 4 символов — приватные данные не раскрываются.
    masked_patient = str(patient_id)[-4:]
    masked_telegram = str(telegram_id)[-4:]
    logger.info(
        "Пациент ...{} удалён пользователем ...{}",
        masked_patient,
        masked_telegram,
    )
    return {"status": "deleted", "patient_id": patient_id}


async def _reverify_patient(
    api: Any,
    db: DatabaseManager,
    telegram_id: str,
    patient_id: str,
    plan: PatientUpdatePlan,
) -> JSONResponse | None:
    """Повторно верифицирует пациента после правки ФИО или даты рождения.

    Returns:
        JSONResponse с ошибкой 404/409/504 либо ``None``, если правка допустима.
    """
    try:
        found_id, last_err = await asyncio.wait_for(
            _find_patient_id(
                api,
                plan.fio,
                cast(datetime.date, plan.target_bday),
                db,
                telegram_id,
            ),
            timeout=15.0,
        )
    except TimeoutError:
        return JSONResponse(
            status_code=504,
            content={
                "detail": (
                    "Поиск пациента занял слишком много времени. Попробуйте позже."
                )
            },
        )

    if found_id is None:
        if last_err == "api-timeout":
            return JSONResponse(
                status_code=504,
                content={"detail": "Сервер zdrav.lenreg.ru не отвечает."},
            )
        return JSONResponse(
            status_code=404,
            content={
                "detail": (
                    "Пациент с такими данными не найден ни в одной клинике. "
                    "Проверьте ФИО и дату рождения."
                )
            },
        )

    if str(found_id) != str(patient_id):
        return JSONResponse(
            status_code=409,
            content={
                "detail": (
                    "Пациент с такими данными уже есть в системе под другим "
                    "ID. Удалите карточку и добавьте заново."
                )
            },
        )
    return None


@router.put("/patients/{patient_id}", response_model=None)
async def update_patient(
    request: Request,
    patient_id: str,
    body: PatientUpdateRequest,
) -> dict[str, Any] | JSONResponse:
    """Отредактировать карточку пациента с повторной верификацией (P3-EDIT).

    Меняются только переданные поля. Если меняются ФИО или дата рождения,
    пациент заново ищется во всех клиниках (``check_patient``):

    - не найден — 404 (правка не сохраняется);
    - найден под другим ``patient_id`` — 409 (правка создала бы дубль);
    - API недоступен — 504.

    Кэш проверок пары (P3-VERIFY) сбрасывается: старая отметка «не найден»
    после успешной правки больше не актуальна.
    """
    db = _get_db(request)
    api = _get_api(request)
    telegram_id = _get_telegram_id(request)

    user_data = await db.get_user_data(telegram_id)
    existing = user_data.get("patients", {}).get(patient_id)
    if existing is None:
        return JSONResponse(
            status_code=404,
            content={"detail": "Пациент не найден."},
        )

    try:
        plan = build_update_plan(
            str(existing.get("fio", "")),
            _normalize_bday_display(existing.get("bday", "")),
            body.full_name,
            body.birth_date,
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    if plan.data_changed:
        error_response = await _reverify_patient(api, db, telegram_id, patient_id, plan)
        if error_response is not None:
            return error_response

    new_info = build_card(existing, plan, body.alias)
    await db.add_patient(uid=telegram_id, p_id=patient_id, p_info=new_info)
    await delete_check_cache(telegram_id, patient_id)

    # NOTE: CodeQL false positive (py/clear-text-logging-sensitive-data).
    # ID маскированы до последних 4 символов.
    logger.info(
        "Карточка пациента ...{} отредактирована пользователем ...{}",
        str(patient_id)[-4:],
        str(telegram_id)[-4:],
    )
    return {
        "status": "updated",
        "patient": {
            "patient_id": patient_id,
            "fio": plan.fio,
            "bday": plan.bday_display,
            "alias": new_info.get("alias"),
            "needs_check": False,
        },
    }
