"""
API-эндпоинты для Telegram Mini App.

Все эндпоинты требуют аутентификации через initData (middleware
``TelegramInitDataMiddleware``), который сохраняет ``telegram_id``
в ``request.state.telegram_id``.

Роутер монтируется с префиксом ``/api/user``.
"""

import datetime
import logging
from typing import Any, cast

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.config import settings
from src.database.manager import DatabaseManager
from src.database.types import PatientInfo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/user", tags=["Mini App"])


# ── Pydantic-модели для тел запросов ─────────────────────────


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


class AddPatientRequest(BaseModel):
    """Тело запроса на добавление пациента."""

    full_name: str = Field(..., description="ФИО пациента (три слова через пробел)")
    birth_date: str = Field(..., description="Дата рождения в формате ДД.ММ.ГГГГ")
    policy: str = Field(default="", description="Номер полиса ОМС (необязательно)")


# ── Вспомогательные функции ──────────────────────────────────


def _get_telegram_id(request: Request) -> str:
    """Извлекает telegram_id из состояния запроса и приводит к строке."""
    return str(request.state.telegram_id)


def _get_db(request: Request) -> DatabaseManager:
    """Возвращает DatabaseManager из app.state."""
    return cast(DatabaseManager, request.app.state.db)


def _get_api(request: Request):
    """Возвращает ZdravClient из app.state.

    На момент написания ZdravClient ещё не зарегистрирован в app.state —
    будет добавлен на этапе регистрации роутера в ``app.py``.
    """

    api = getattr(request.app.state, "zdrav_client", None)
    if api is None:
        raise RuntimeError(
            "ZdravClient не найден в app.state.zdrav_client. "
            "Добавьте его при регистрации роутера в app.py."
        )
    return api


def _monitoring_id_to_parts(monitoring_id: str) -> tuple[str, str]:
    """Разбирает monitoring_id вида '{p_id}_{d_id}' на компоненты."""
    parts = monitoring_id.split("_", 1)
    if len(parts) != 2:
        raise ValueError(
            f"Неверный формат monitoring_id: {monitoring_id}. "
            "Ожидается формат '{patient_id}_{doctor_id}'."
        )
    return parts[0], parts[1]


# ── Вспомогательная: безопасное извлечение строки имени ────────


def _safe_name(value: Any) -> str:
    """Извлекает строковое имя врача из значения, которое может быть объектом.

    Используется как fallback, если _coerce_str в models.py не сработал
    (например, при чтении из БД старых данных, где name сохранён как dict).
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        # Пытаемся извлечь Name, name, или собрать из ФИО
        name_value = value.get("Name") or value.get("name") or ""
        if name_value and isinstance(name_value, str):
            return name_value
        parts = [
            value.get(k, "")
            for k in ("last_name", "first_name", "middle_name")
            if value.get(k)
        ]
        if parts:
            return " ".join(parts)
    return str(value)


# ── Эндпоинты ────────────────────────────────────────────────


@router.get("/profile")
async def get_profile(request: Request) -> dict[str, Any]:
    """Получить профиль пользователя (ФИО, список пациентов, статистику мониторинга)."""
    db = _get_db(request)
    telegram_id = _get_telegram_id(request)

    user_data = await db.get_user_data(telegram_id)

    patients_list: list[dict[str, Any]] = []
    for p_id, p_info in user_data.get("patients", {}).items():
        patient_entry: dict[str, Any] = {
            "patient_id": p_id,
            "fio": p_info.get("fio", ""),
            "bday": p_info.get("bday", ""),
        }
        if "alias" in p_info:
            patient_entry["alias"] = p_info["alias"]
        if "confirmed_clinics" in p_info:
            patient_entry["confirmed_clinics"] = p_info["confirmed_clinics"]
        patients_list.append(patient_entry)

    monitoring = user_data.get("monitoring", {})
    monitoring_count = sum(len(doctors) for doctors in monitoring.values())

    return {
        "telegram_id": telegram_id,
        "patients": patients_list,
        "monitoring_count": monitoring_count,
        "stats": {
            "total_patients": len(user_data.get("patients", {})),
            "total_monitored_doctors": sum(
                len(doctors) for doctors in monitoring.values()
            ),
        },
    }


@router.get("/doctors")
async def get_doctors(
    request: Request,
    patient_id: str | None = Query(None, description="Фильтр по пациенту"),
) -> dict[str, Any]:
    """Список отслеживаемых врачей со статусом слотов."""
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

            # Статус — пока заглушка; реальный статус обновляется monitor.py
            doctors_list.append(
                {
                    "monitoring_id": f"{p_id}_{d_id}",
                    "patient_id": p_id,
                    "patient_name": patient_name,
                    "doctor_id": d_id,
                    "doctor_name": _safe_name(d_info.get("name", "")),
                    "specialty": d_info.get("specialty", ""),
                    "clinic_id": d_info.get("clinic_id", ""),
                    "clinic_name": clinic_name or "",
                    "status": "checking",
                    "free_tickets": 0,
                    "last_check": None,
                }
            )

    return {"doctors": doctors_list}


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

        # Имя врача и специальность: используем переданные из Mini App, если есть
        doctor_name = body.doctor_name or body.doctor_id
        specialty_name = body.specialty_name or body.specialty_id

        # Если имена не переданы клиентом — делаем живой запрос к API
        if not body.doctor_name or not body.specialty_name:
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
                            doctor_name = _safe_name(doc.get("Name", doctor_name))
                        if not body.specialty_name:
                            specialty_name = doc.get("SpesialityName", specialty_name)
                        break
            except Exception:
                # API lookup failed — используем fallback-имена
                pass

        clinic_name = await db.get_clinic_name(body.clinic_id) or body.clinic_id

        await db.toggle_monitoring(
            uid=telegram_id,
            p_id=body.patient_id,
            d_id=body.doctor_id,
            d_name=doctor_name,
            clinic_id=body.clinic_id,
            d_spec=specialty_name,
        )

        return {
            "status": "added",
            "doctor_name": doctor_name,
            "specialty": specialty_name,
            "clinic_name": clinic_name,
        }

    except httpx.TimeoutException:
        logger.error(
            "Таймаут API при добавлении врача %s для пользователя %s",
            body.doctor_id,
            telegram_id,
        )
        return JSONResponse(
            status_code=504,
            content={"detail": "Таймаут при запросе к API zdrav.lenreg.ru"},
        )
    except httpx.NetworkError:
        logger.error(
            "Сетевая ошибка API при добавлении врача %s для пользователя %s",
            body.doctor_id,
            telegram_id,
        )
        return JSONResponse(
            status_code=502,
            content={"detail": "API zdrav.lenreg.ru недоступно"},
        )
    except Exception:
        logger.exception(
            "Ошибка при добавлении врача %s для пользователя %s",
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
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"detail": str(e)},
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
        d_spec=specialty,
    )

    return {
        "status": "removed",
        "doctor_name": doctor_name,
    }


@router.get("/clinics")
async def get_clinics(request: Request) -> dict[str, Any]:
    """Список поликлиник (из кэша БД)."""
    db = _get_db(request)

    active_clinics = await db._db.get_active_clinics()

    clinics_list: list[dict[str, Any]] = []
    for clinic in active_clinics:
        clinics_list.append(
            {
                "clinic_id": clinic["clinic_id"],
                "name": clinic["name"],
                "short_name": clinic.get("short_name", clinic["name"]),
                "type": clinic["type"],
                "city": clinic.get("city", ""),
                "is_active": bool(clinic["is_active"]),
            }
        )

    return {"clinics": clinics_list}


@router.get("/specialties", response_model=None)
async def get_specialties(
    request: Request,
    clinic_id: str = Query(..., description="ID клиники (обязательный)"),
    patient_id: str | None = Query(None, description="ID пациента (опционально)"),
) -> dict[str, Any] | JSONResponse:
    """Список специальностей в выбранной поликлинике (из БД, таблица doctors)."""
    db = _get_db(request)

    try:
        specialties_raw = await db._db.get_clinic_specialties(clinic_id)
    except Exception:
        logger.exception(
            "Ошибка при получении специальностей из БД для clinic_id=%s", clinic_id
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Внутренняя ошибка сервера"},
        )

    specialties: list[dict[str, Any]] = []
    for spec in specialties_raw:
        specialties.append(
            {
                "specialty_id": spec["specialty_id"],
                "name": spec["specialty"],
                "is_tech": False,
                "is_doc": True,
            }
        )

    return {
        "clinic_id": clinic_id,
        "specialties": specialties,
    }


@router.get("/doctors/available", response_model=None)
async def get_available_doctors(
    request: Request,
    clinic_id: str = Query(..., description="ID клиники (обязательный)"),
    patient_id: str = Query(..., description="ID пациента (обязательный)"),
    specialty_id: str | None = Query(
        None,
        description="ID специальности (опционально; не указан — все врачи клиники)",
    ),
) -> dict[str, Any] | JSONResponse:
    """Список врачей в поликлинике (из БД + API для слотов).

    Имена врачей и специальности — из таблицы ``doctors`` (как у бота).
    Слоты (CountFreeTicket, NearestDate) — живой запрос к API zdrav.lenreg.ru.
    Если врачей в БД нет — срабатывает on-demand discovery (аналогично боту).
    """
    db = _get_db(request)
    api = _get_api(request)

    # 1. Получаем врачей из БД
    doctors_dict = await db.get_doctors_for_clinic(clinic_id)

    # 2. Если врачей нет — on-demand discovery
    #    (аналогично common._discover_doctors_on_demand в боте)
    if not doctors_dict:
        logger.info(
            "Врачи для clinic_id=%s не найдены в БД, запускаем on-demand discovery",
            clinic_id,
        )
        try:
            from src.handlers.common import _discover_doctors_on_demand

            doctors_dict = await _discover_doctors_on_demand(
                api, db, clinic_id, patient_id
            )
        except Exception:
            logger.exception("Ошибка on-demand discovery для clinic_id=%s", clinic_id)
            # Если discovery упал — возвращаем пустой список, но не 500
            doctors_dict = {}

    # 3. Получаем свежие слоты из API (один batch-запрос)
    slots_map: dict[str, dict[str, Any]] = {}
    try:
        if specialty_id:
            # Конкретная специальность — один запрос
            api_doctors = await api.fetch_all_doctors(
                specialty_id=specialty_id,
                patient_id=patient_id,
                clinic_id=clinic_id,
                limiter=api.limiter,
            )
        else:
            # Все специальности — batch-запрос
            api_doctors = await api.fetch_all_doctors_for_clinic(
                patient_id=patient_id,
                clinic_id=clinic_id,
                limiter=api.limiter,
            )
        for doc in api_doctors:
            doc_id = str(doc.get("IdDoc", ""))
            if doc_id:
                slots_map[doc_id] = {
                    "free_tickets": int(doc.get("CountFreeTicket", 0)),
                    "nearest_date": doc.get("NearestDate"),
                }
    except httpx.TimeoutException:
        logger.warning(
            "Таймаут API слотов для clinic_id=%s, возвращаем врачей без слотов",
            clinic_id,
        )
    except httpx.NetworkError:
        logger.warning(
            "Сетевая ошибка API слотов для clinic_id=%s, возвращаем врачей без слотов",
            clinic_id,
        )
    except Exception:
        logger.exception(
            "Ошибка получения слотов для clinic_id=%s, возвращаем врачей без слотов",
            clinic_id,
        )

    # 4. Формируем ответ: врачи из БД + слоты из API
    doctors: list[dict[str, Any]] = []
    for doc_id, doc_info in doctors_dict.items():
        doc_specialty = doc_info.get("specialty", "")

        # Фильтр по specialty_id: точное совпадение по имени специальности
        if specialty_id and doc_specialty != specialty_id:
            continue

        slots = slots_map.get(doc_id, {})
        doctors.append(
            {
                "doctor_id": doc_id,
                "name": _safe_name(doc_info.get("name", "")),
                "specialty_name": doc_specialty,
                "specialty_id": specialty_id or "",
                "free_tickets": slots.get("free_tickets", 0),
                "nearest_date": slots.get("nearest_date"),
            }
        )

    return {
        "clinic_id": clinic_id,
        "specialty_id": specialty_id,
        "doctors": doctors,
    }


@router.get("/doctors/search")
async def search_doctors(
    request: Request,
    q: str = Query(
        ..., min_length=2, description="Поисковый запрос (минимум 2 символа)"
    ),
    patient_id: str = Query(..., description="ID пациента для проверки слотов"),
) -> dict[str, Any] | JSONResponse:
    """Поиск врачей по подстроке в имени (глобально, по всем клиникам).

    Возвращает врачей из всех клиник с информацией о свободных слотах.
    """
    db = _get_db(request)
    api = _get_api(request)

    try:
        doctors = await db._db.search_doctors_by_name(q, limit=20)
    except Exception:
        logger.exception("Ошибка поиска врачей по запросу '%s'", q)
        return JSONResponse(
            status_code=500,
            content={"detail": "Внутренняя ошибка сервера при поиске врачей."},
        )

    result: list[dict[str, Any]] = []
    for doc in doctors:
        # Проверяем слоты через API
        free_tickets = 0
        try:
            slots = await api.check_slots(
                doc_id=doc["doctor_id"],
                patient_id=patient_id,
                clinic_id=doc["clinic_id"],
                limiter=api.limiter,
            )
            free_tickets = len(slots) if slots else 0
        except Exception:
            free_tickets = 0

        result.append(
            {
                "doctor_id": doc["doctor_id"],
                "name": doc["name"],
                "specialty_name": doc.get("specialty", ""),
                "clinic_id": doc["clinic_id"],
                "clinic_name": doc.get("clinic_name", ""),
                "free_tickets": free_tickets,
            }
        )

    return {"doctors": result}


@router.get("/patients")
async def get_patients(request: Request) -> dict[str, Any]:
    """Список пациентов пользователя."""
    db = _get_db(request)
    telegram_id = _get_telegram_id(request)

    user_data = await db.get_user_data(telegram_id)

    patients_list: list[dict[str, Any]] = []
    for p_id, p_info in user_data.get("patients", {}).items():
        patient_entry: dict[str, Any] = {
            "patient_id": p_id,
            "fio": p_info.get("fio", ""),
            "bday": p_info.get("bday", ""),
        }
        if "alias" in p_info:
            patient_entry["alias"] = p_info["alias"]
        if "confirmed_clinics" in p_info:
            patient_entry["confirmed_clinics"] = p_info["confirmed_clinics"]
        patients_list.append(patient_entry)

    return {"patients": patients_list}


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

    # Формируем список clinic_id для перебора
    clinic_ids_to_try: list[str] = []

    # Этап 1: клиника по умолчанию
    clinic_ids_to_try.append(settings.DEFAULT_CLINIC_ID)

    # Этап 2: глобальный поиск
    clinic_ids_to_try.append("")

    # Этап 3: все активные clinic_id из БД
    try:
        active_ids = await db._db.get_active_clinic_ids()
        for cid in active_ids:
            if cid not in clinic_ids_to_try:
                clinic_ids_to_try.append(cid)
    except Exception:
        logger.warning(
            "Не удалось получить список активных clinic_id для пользователя %s",
            telegram_id,
        )

    # Поиск пациента
    p_id: str | None = None
    last_err: str | None = None

    for clinic_id in clinic_ids_to_try:
        try:
            p_id, err = await api.fetch_patient_id(fio, bday_date, clinic_id)
        except httpx.TimeoutException:
            logger.error(
                "Таймаут API при поиске пациента '%s' в clinic_id=%s",
                fio,
                clinic_id,
            )
            continue
        except httpx.NetworkError:
            logger.error(
                "Сетевая ошибка API при поиске пациента '%s' в clinic_id=%s",
                fio,
                clinic_id,
            )
            continue
        except Exception:
            logger.exception(
                "Ошибка при поиске пациента '%s' в clinic_id=%s",
                fio,
                clinic_id,
            )
            continue

        if p_id is not None:
            logger.info(
                "Пациент '%s' найден: p_id=%s, clinic_id=%s",
                fio,
                p_id,
                clinic_id,
            )
            break
        last_err = err

    if p_id is None:
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

    try:
        await db.add_patient(uid=telegram_id, p_id=p_id, p_info=p_info)
    except Exception:
        logger.exception(
            "Ошибка сохранения пациента p_id=%s для пользователя %s",
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


@router.get("/slots", response_model=None)
async def get_slots(
    request: Request,
    monitoring_id: str = Query(
        ..., description="ID мониторинга: {patient_id}_{doctor_id}"
    ),
) -> dict[str, Any] | JSONResponse:
    """Свободные слоты для отслеживаемого врача."""
    db = _get_db(request)
    api = _get_api(request)
    telegram_id = _get_telegram_id(request)

    try:
        p_id, d_id = _monitoring_id_to_parts(monitoring_id)
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"detail": str(e)},
        )

    # Проверяем, что врач действительно отслеживается
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

    doctor_info = patient_doctors[d_id]
    doctor_name = doctor_info.get("name", d_id)
    clinic_id = doctor_info.get("clinic_id", "")
    specialty = doctor_info.get("specialty", "")
    clinic_name = await db.get_clinic_name(clinic_id) or clinic_id

    # Живой запрос слотов
    try:
        slots_raw = await api.check_slots(
            doc_id=d_id,
            patient_id=p_id,
            clinic_id=clinic_id,
            limiter=api.limiter,
        )
    except httpx.TimeoutException:
        logger.error(
            "Таймаут API при получении слотов для monitoring_id=%s",
            monitoring_id,
        )
        return JSONResponse(
            status_code=504,
            content={"detail": "Таймаут при запросе к API zdrav.lenreg.ru"},
        )
    except httpx.NetworkError:
        logger.error(
            "Сетевая ошибка API при получении слотов для monitoring_id=%s",
            monitoring_id,
        )
        return JSONResponse(
            status_code=502,
            content={"detail": "API zdrav.lenreg.ru недоступно"},
        )
    except Exception:
        logger.exception(
            "Ошибка при получении слотов для monitoring_id=%s",
            monitoring_id,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Внутренняя ошибка сервера"},
        )

    # Форматирование слотов
    # check_slots возвращает list[str] вида "ДД.ММ.ГГГГ в ЧЧ:ММ" или None/[]
    slots: list[dict[str, str]] = []
    if slots_raw:
        for slot_str in slots_raw:
            # Разбираем строку "ДД.ММ.ГГГГ в ЧЧ:ММ"
            parts = slot_str.split(" в ", 1)
            date_str = parts[0] if len(parts) > 0 else slot_str
            time_str = parts[1] if len(parts) > 1 else ""
            slots.append(
                {
                    "date": date_str.strip(),
                    "time": time_str.strip(),
                    "clinic_id": clinic_id,
                }
            )

    return {
        "monitoring_id": monitoring_id,
        "doctor_name": doctor_name,
        "specialty": specialty,
        "clinic_name": clinic_name,
        "slots": slots,
        "total": len(slots),
    }
