"""
Мониторинг врачей Mini App API (``/api/user/monitoring``).

Модуль описывает пути без префикса: префикс ``/api/user`` добавляет
агрегатор :mod:`src.web.routers.user_api`. Здесь же живут валидаторы
фильтра отслеживания — единые правила с ботом (§9.3.5).
"""

import datetime
import json
import re
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field

from src.utils.cache import delete_cache_keys_by_prefix
from src.utils.filter_rules import (
    FILTER_MAX_HORIZON_DAYS,
    FILTER_MAX_SPECIFIC_DATES,
)
from src.web.routers.user_common import (
    _get_db,
    _get_telegram_id,
    _monitoring_id_to_parts,
)
from src.web.types import MonitoringFilterView

router = APIRouter()


class MonitoringFilterRequest(BaseModel):
    """Тело запроса настройки фильтра отслеживания (PUT /filter)."""

    date_from: str = Field(default="", description="Начало интервала дат (ГГГГ-ММ-ДД)")
    date_to: str = Field(default="", description="Конец интервала дат (ГГГГ-ММ-ДД)")
    time_from: str = Field(default="", description="Начало интервала времени (ЧЧ:ММ)")
    time_to: str = Field(default="", description="Конец интервала времени (ЧЧ:ММ)")
    specific_dates: list[str] = Field(
        default_factory=list, description="Список конкретных дат (ГГГГ-ММ-ДД)"
    )


def _validate_filter_date(
    value: str, *, today: datetime.date | None = None
) -> datetime.date | None:
    """Проверяет дату фильтра ``ГГГГ-ММ-ДД`` (пустая строка допустима).

    Границы — едины с серверной валидацией фильтра Mini App:
    дата не раньше сегодня и не позже сегодня + ``FILTER_MAX_HORIZON_DAYS``.

    Args:
        value: Дата в формате ``ГГГГ-ММ-ДД`` либо пустая строка.
        today: Опорная дата для проверки границ (для тестов).

    Returns:
        Разобранная дата либо ``None`` для пустой строки.

    Raises:
        ValueError: Если формат даты или её границы некорректны.
    """
    if not value:
        return None
    try:
        parsed = datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"Неверный формат даты: '{value}'. Ожидается ГГГГ-ММ-ДД."
        ) from exc

    current = today or datetime.date.today()
    if parsed < current:
        raise ValueError("Дата фильтра не может быть в прошлом.")
    if parsed > current + datetime.timedelta(days=FILTER_MAX_HORIZON_DAYS):
        raise ValueError(
            "Дата фильтра не может быть позже чем через "
            f"{FILTER_MAX_HORIZON_DAYS} дней от сегодня."
        )
    return parsed


def _validate_filter_time(value: str) -> None:
    """Проверяет формат времени фильтра 'ЧЧ:ММ' (пустая строка допустима).

    Raises:
        ValueError: Если формат времени некорректен.
    """
    if not value:
        return
    try:
        datetime.time.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"Неверный формат времени: '{value}'. Ожидается ЧЧ:ММ."
        ) from exc


def _validate_filter_specific_dates(values: list[str]) -> list[str]:
    """Проверяет список конкретных дат по правилам бота (§9.3.5).

    Пустой список допустим; иначе — не более ``FILTER_MAX_SPECIFIC_DATES``
    дат, каждая не раньше сегодня. Дубликаты удаляются, порядок сохраняется.

    Raises:
        ValueError: Если дат слишком много или хотя бы одна в прошлом/невалидна.
    """
    cleaned = [value.strip() for value in values if value.strip()]
    if len(cleaned) > FILTER_MAX_SPECIFIC_DATES:
        raise ValueError(
            f"Слишком много конкретных дат: максимум {FILTER_MAX_SPECIFIC_DATES}."
        )

    current = datetime.date.today()
    unique: list[str] = []
    for value in cleaned:
        _validate_filter_date(value, today=current)
        if value not in unique:
            unique.append(value)
    return unique


def _validate_filter_date_range(date_from: Any, date_to: Any) -> None:
    """Проверяет, что верхняя граница дат не раньше нижней (§9.3.5).

    Raises:
        ValueError: Если конец интервала раньше начала.
    """
    if date_from and date_to and date_to < date_from:
        raise ValueError("Дата окончания раньше даты начала.")


def _validate_filter_time_range(time_from: str, time_to: str) -> None:
    """Проверяет, что конец интервала времени не раньше начала (§9.3.5).

    Raises:
        ValueError: Если конец интервала раньше начала.
    """
    if time_from and time_to and time_to < time_from:
        raise ValueError("Конец интервала времени раньше начала.")


# ID пациентов, врачей и клиник — только цифры (инвариант deep-link'ов Mini App,
# см. ``start-param.js``); '_' и пустые значения в путь не принимаются.
_ID_PATTERN = re.compile(r"^\d+$")


def _validate_numeric_id(value: str, label: str) -> None:
    """Проверяет, что идентификатор — непустая последовательность цифр.

    Args:
        value: Значение из пути запроса.
        label: Имя параметра для текста ошибки.

    Raises:
        ValueError: Если идентификатор пуст или содержит не цифры.
    """
    if not value or not _ID_PATTERN.match(value):
        raise ValueError(f"Неверный формат {label}: '{value}'.")


@router.put("/monitoring/{monitoring_id}/filter", response_model=None)
async def update_monitoring_filter(
    request: Request,
    monitoring_id: str,
    body: MonitoringFilterRequest,
) -> dict[str, Any] | JSONResponse:
    """Настроить фильтр отслеживания врача (T-16).

    ``monitoring_id`` — строка формата ``{patient_id}_{doctor_id}``.
    Пустые строки снимают соответствующее ограничение; пустой
    ``specific_dates`` отключает отбор по конкретным датам.
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

    # Валидация форматов, границ и количества — единые правила с ботом (§9.3.5).
    try:
        date_from = _validate_filter_date(body.date_from.strip())
        date_to = _validate_filter_date(body.date_to.strip())
        time_from = body.time_from.strip()
        time_to = body.time_to.strip()
        _validate_filter_time(time_from)
        _validate_filter_time(time_to)
        cleaned_dates = _validate_filter_specific_dates(body.specific_dates)
        _validate_filter_date_range(date_from, date_to)
        _validate_filter_time_range(time_from, time_to)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    # Проверка наличия записи мониторинга
    user_data = await db.get_user_data(telegram_id)
    if d_id not in user_data.get("monitoring", {}).get(p_id, {}):
        return JSONResponse(
            status_code=404,
            content={
                "detail": (
                    f"Врач с monitoring_id='{monitoring_id}' не найден в мониторинге."
                ),
            },
        )

    filter_data = {
        "date_from": body.date_from.strip(),
        "date_to": body.date_to.strip(),
        "time_from": body.time_from.strip(),
        "time_to": body.time_to.strip(),
        "specific_dates": json.dumps(cleaned_dates, ensure_ascii=False),
    }

    try:
        await db.update_monitoring_filter(telegram_id, p_id, d_id, filter_data)
    except ValueError:
        return JSONResponse(
            status_code=404,
            content={"detail": "Мониторинг не найден."},
        )
    except Exception:
        logger.exception(
            "Ошибка обновления фильтра для monitoring_id={}", monitoring_id
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Внутренняя ошибка сервера"},
        )

    filter_view: MonitoringFilterView = {
        "date_from": filter_data["date_from"],
        "date_to": filter_data["date_to"],
        "time_from": filter_data["time_from"],
        "time_to": filter_data["time_to"],
        "specific_dates": cleaned_dates,
    }
    return {
        "status": "ok",
        "monitoring_id": monitoring_id,
        "filter": filter_view,
    }


@router.delete("/monitoring", response_model=None)
async def reset_all_monitoring(request: Request) -> dict[str, Any]:
    """Снять весь мониторинг пользователя (паритет с кнопкой бота).

    Идемпотентно: повторный вызов на пустом мониторинге — 200 с ``0``.
    Кэш слотов пользователя очищается, чтобы после сброса не осталось
    устаревших статусов.
    """
    db = _get_db(request)
    telegram_id = _get_telegram_id(request)

    user_data = await db.get_user_data(telegram_id)
    removed = sum(len(doctors) for doctors in user_data.get("monitoring", {}).values())

    await db.stop_all_monitoring(telegram_id)
    await delete_cache_keys_by_prefix(f"{telegram_id}_")

    masked = str(telegram_id)[-4:]
    logger.info(
        "Весь мониторинг сброшен из Mini App: uid=...{}, удалено={}",
        masked,
        removed,
    )
    return {"status": "reset", "scope": "all", "removed_doctors": removed}


@router.delete("/monitoring/patients/{patient_id}", response_model=None)
async def reset_patient_monitoring(
    request: Request, patient_id: str
) -> dict[str, Any] | JSONResponse:
    """Снять весь мониторинг пациента (паритет с кнопкой бота).

    Удаляются все пары пациент + врач, включая их фильтры отслеживания.
    Чужой/неизвестный ``patient_id`` — 404 (IDOR закрыт проверкой владельца);
    отсутствие врачей у своего пациента — идемпотентные 200 с ``0``.
    """
    db = _get_db(request)
    telegram_id = _get_telegram_id(request)

    try:
        _validate_numeric_id(patient_id, "patient_id")
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    user_data = await db.get_user_data(telegram_id)
    if patient_id not in user_data.get("patients", {}):
        return JSONResponse(status_code=404, content={"detail": "Пациент не найден."})

    removed = await db.remove_patient_monitoring(telegram_id, patient_id)
    await delete_cache_keys_by_prefix(f"{telegram_id}_{patient_id}_")

    # ID маскированы до последних 4 символов — приватные данные не раскрываются.
    masked_patient = str(patient_id)[-4:]
    masked_telegram = str(telegram_id)[-4:]
    logger.info(
        "Мониторинг пациента сброшен из Mini App: uid=...{}, p_id=...{}, удалено={}",
        masked_telegram,
        masked_patient,
        removed,
    )
    return {
        "status": "reset",
        "scope": "patient",
        "patient_id": patient_id,
        "removed_doctors": removed,
    }


@router.delete(
    "/monitoring/patients/{patient_id}/clinics/{clinic_id}", response_model=None
)
async def reset_clinic_monitoring(
    request: Request, patient_id: str, clinic_id: str
) -> dict[str, Any] | JSONResponse:
    """Снять мониторинг всех врачей клиники для пациента (паритет с ботом).

    Удаляются только пары указанной клиники, включая их фильтры. Чужой/
    неизвестный ``patient_id`` — 404; клиника без отслеживаемых врачей —
    идемпотентные 200 с ``0``.
    """
    db = _get_db(request)
    telegram_id = _get_telegram_id(request)

    try:
        _validate_numeric_id(patient_id, "patient_id")
        _validate_numeric_id(clinic_id, "clinic_id")
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    user_data = await db.get_user_data(telegram_id)
    if patient_id not in user_data.get("patients", {}):
        return JSONResponse(status_code=404, content={"detail": "Пациент не найден."})

    removed_ids = await db.remove_clinic_monitoring(telegram_id, patient_id, clinic_id)
    for d_id in removed_ids:
        await delete_cache_keys_by_prefix(f"{telegram_id}_{patient_id}_{d_id}")

    masked_patient = str(patient_id)[-4:]
    masked_telegram = str(telegram_id)[-4:]
    logger.info(
        "Мониторинг клиники сброшен из Mini App: uid=...{}, p_id=...{}, "
        "clinic_id={}, удалено={}",
        masked_telegram,
        masked_patient,
        clinic_id,
        len(removed_ids),
    )
    return {
        "status": "reset",
        "scope": "clinic",
        "patient_id": patient_id,
        "clinic_id": clinic_id,
        "removed_doctors": len(removed_ids),
    }
