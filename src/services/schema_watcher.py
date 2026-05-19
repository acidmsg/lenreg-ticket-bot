"""
Детектор изменений API zdrav.lenreg.ru.

Сравнивает эталонные JSON Schema из docs/schemas/ с текущими Pydantic-моделями.
Запускается как фоновый asyncio-цикл с заданным интервалом.

Использование:
    from src.services.schema_watcher import schema_check_loop

    # В main.py:
    task = asyncio.create_task(
        schema_check_loop(api, error_notifier, prometheus_metrics)
    )
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from pathlib import Path
from typing import Any

from src.api.models import (
    AppointmentListResponse,
    CheckPatientResponse,
    ClinicListResponse,
    DoctorListResponse,
    SpecialityListResponse,
)
from src.config import settings

logger = logging.getLogger(__name__)

# Директория эталонных схем по умолчанию
_DEFAULT_SCHEMAS_DIR = Path("docs/schemas")

# Минимальные тестовые данные для проверки схем (clinic_id=1 — заглушка)
_SCHEMA_CHECK_PARAMS: dict[str, dict[str, Any]] = {
    "check_patient": {
        "first_name": "Иван",
        "last_name": "Иванов",
        "middle_name": "Иванович",
        "birthday": "01.01.1990",
        "clinic_id": 1,
    },
    "speciality_list": {
        "clinic_id": 1,
        "patient_id": 0,
        "history_id": 0,
    },
    "doctor_list": {
        "speciality_id": 1,
        "clinic_id": 1,
        "patient_id": 0,
        "history_id": 0,
    },
    "appointment_list": {
        "doctor_id": 1,
        "clinic_id": 1,
        "patient_id": 0,
        "history_id": 0,
        "appointment_type": "adult",
    },
    "clinic_list": {},  # без параметров — получит все клиники
}

# Маппинг endpoint -> Pydantic-модель
_ENDPOINT_MODELS: dict[str, type[Any]] = {
    "check_patient": CheckPatientResponse,
    "speciality_list": SpecialityListResponse,
    "doctor_list": DoctorListResponse,
    "appointment_list": AppointmentListResponse,
    "clinic_list": ClinicListResponse,
}


# ── Вспомогательные функции для сравнения схем ───────────────────


def _describe_type(prop: dict[str, Any]) -> str:
    """Человекочитаемое описание типа свойства."""
    if "$ref" in prop:
        return f"$ref:{prop['$ref'].split('/')[-1]}"
    if "anyOf" in prop:
        types: list[str] = [str(t.get("type", "?")) for t in prop["anyOf"]]
        return f"anyOf[{', '.join(types)}]"
    return str(prop.get("type", "?"))


def _normalize_anyof(anyof: list[dict[str, Any]]) -> set[str]:
    """Извлекает множество типов из anyOf (напр. {'string', 'null'})."""
    return {item.get("type", "?") for item in anyof}


def compare_schemas(
    current: dict[str, Any],
    reference: dict[str, Any],
    path: str = "root",
) -> list[str]:
    """Рекурсивно сравнивает две JSON Schema. Возвращает список расхождений.

    Сравниваемые аспекты:
    - type
    - additionalProperties
    - required (только для объектов)
    - properties (ключи и рекурсивно значения)
    - items (для массивов)
    - anyOf (nullable поля)

    Args:
        current: Текущая JSON Schema (из model_json_schema()).
        reference: Эталонная JSON Schema (из docs/schemas/).
        path: Путь в дереве схемы для сообщений об ошибках.

    Returns:
        Список строк с описанием расхождений. Пустой список — идентичны.
    """
    diffs: list[str] = []

    # 1. Сравнение type
    cur_type = current.get("type")
    ref_type = reference.get("type")
    if cur_type != ref_type:
        diffs.append(f"{path}: type изменился с '{ref_type}' на '{cur_type}'")

    # 2. Сравнение additionalProperties
    cur_ap = current.get("additionalProperties")
    ref_ap = reference.get("additionalProperties")
    if cur_ap != ref_ap:
        diffs.append(f"{path}: additionalProperties изменился с {ref_ap} на {cur_ap}")

    # 3. Сравнение required (только для объектов)
    if cur_type == "object" and ref_type == "object":
        cur_req = set(current.get("required", []))
        ref_req = set(reference.get("required", []))
        added = cur_req - ref_req
        removed = ref_req - cur_req
        if added:
            diffs.append(f"{path}: поля стали обязательными: {sorted(added)}")
        if removed:
            diffs.append(
                f"{path}: поля перестали быть обязательными: {sorted(removed)}"
            )

    # 4. Сравнение properties (только для объектов)
    if "properties" in current or "properties" in reference:
        cur_props = set(current.get("properties", {}).keys())
        ref_props = set(reference.get("properties", {}).keys())
        added = cur_props - ref_props
        removed = ref_props - cur_props
        for key in sorted(added):
            diffs.append(
                f"{path}.{key}: новое поле "
                f"(тип: {_describe_type(current['properties'][key])})"
            )
        for key in sorted(removed):
            diffs.append(
                f"{path}.{key}: поле удалено "
                f"(был тип: {_describe_type(reference['properties'][key])})"
            )
        # Рекурсивно сравниваем общие поля
        for key in sorted(cur_props & ref_props):
            diffs.extend(
                compare_schemas(
                    current["properties"][key],
                    reference["properties"][key],
                    f"{path}.{key}",
                )
            )

    # 5. Сравнение items (для массивов)
    if "items" in current or "items" in reference:
        diffs.extend(
            compare_schemas(
                current.get("items", {}),
                reference.get("items", {}),
                f"{path}.items",
            )
        )

    # 6. Сравнение anyOf (nullable поля)
    cur_anyof = _normalize_anyof(current.get("anyOf", []))
    ref_anyof = _normalize_anyof(reference.get("anyOf", []))
    if cur_anyof != ref_anyof:
        diffs.append(f"{path}: anyOf изменился с {ref_anyof} на {cur_anyof}")

    return diffs


# ── Загрузка эталонных схем ─────────────────────────────────────


def load_reference_schemas(
    schemas_dir: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Загружает эталонные JSON Schema из директории docs/schemas/.

    Args:
        schemas_dir: Путь к директории со схемами.
                     По умолчанию Path("docs/schemas").

    Returns:
        Словарь {ModelName: schema_dict}.
        Пустой словарь, если директория не найдена.
    """
    if schemas_dir is None:
        schemas_dir = _DEFAULT_SCHEMAS_DIR

    schemas: dict[str, dict[str, Any]] = {}

    if not schemas_dir.is_dir():
        logger.warning("Директория эталонных схем не найдена: {}", schemas_dir)
        return schemas

    for filepath in sorted(schemas_dir.glob("*.json")):
        model_name = filepath.stem  # имя файла без .json
        try:
            with open(filepath, encoding="utf-8") as f:
                schemas[model_name] = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Ошибка загрузки эталонной схемы {}: {}", filepath, e)

    logger.info("Загружено {} эталонных схем из {}", len(schemas), schemas_dir)
    return schemas


# ── Валидация одного эндпоинта ──────────────────────────────────


async def validate_endpoint_schema(
    client: Any,
    endpoint: str,
    reference_schemas: dict[str, dict[str, Any]],
) -> list[str]:
    """Делает тестовый запрос к эндпоинту, валидирует ответ,
    сравнивает схемы.

    Args:
        client: Экземпляр ZdravClient.
        endpoint: Название эндпоинта (ключ из _SCHEMA_CHECK_PARAMS).
        reference_schemas: Эталонные схемы {ModelName: schema}.

    Returns:
        Список расхождений. Пустой список — схемы совпадают.
    """
    model_class = _ENDPOINT_MODELS.get(endpoint)
    if model_class is None:
        logger.warning("schema_check: неизвестный эндпоинт '{}'", endpoint)
        return []

    ref_schema = reference_schemas.get(model_class.__name__)
    if ref_schema is None:
        logger.warning("schema_check: нет эталонной схемы для {}", model_class.__name__)
        return []

    try:
        # Выполняем тестовый запрос в зависимости от эндпоинта
        result = await _call_endpoint(client, endpoint)

        # Если API вернул None или ошибку — пропускаем проверку схемы
        if result is None:
            logger.warning("schema_check: {} — API вернул None, пропускаем", endpoint)
            return []

        # Если результат — кортеж (patient_id, error) и patient_id=None
        if isinstance(result, tuple) and result[0] is None:
            logger.warning(
                "schema_check: {} — API не нашёл данные, пропускаем", endpoint
            )
            return []

        # Получаем текущую JSON Schema из модели
        current_schema = model_class.model_json_schema()

        # Сравниваем с эталоном
        diffs = compare_schemas(current_schema, ref_schema)
        return diffs

    except Exception as e:
        logger.error("schema_check: ошибка проверки {}: {}", endpoint, e)
        # Не фатально — возвращаем пустой список
        return []


async def _call_endpoint(client: Any, endpoint: str) -> Any:
    """Вызывает соответствующий метод ZdravClient для эндпоинта.

    Args:
        client: Экземпляр ZdravClient.
        endpoint: Название эндпоинта.

    Returns:
        Результат вызова метода API.
        None при ошибке or пустом ответе.
    """
    params = _SCHEMA_CHECK_PARAMS.get(endpoint, {})
    limiter = getattr(client, "limiter_healthcheck", None)

    if endpoint == "check_patient":
        # Формируем ФИО из параметров
        fio = f"{params['last_name']} {params['first_name']} {params['middle_name']}"
        bday = datetime.datetime.strptime(params["birthday"], "%d.%m.%Y").date()
        return await client.fetch_patient_id(
            fio=fio,
            bday_date=bday,
            clinic_id=str(params["clinic_id"]),
            limiter=limiter,
        )

    elif endpoint == "speciality_list":
        return await client.fetch_speciality_list(
            patient_id=str(params["patient_id"]),
            clinic_id=str(params["clinic_id"]),
            limiter=limiter,
        )

    elif endpoint == "doctor_list":
        # Получаем список специальностей, берём первую
        specialties = await client.fetch_speciality_list(
            patient_id=str(params["patient_id"]),
            clinic_id=str(params["clinic_id"]),
            limiter=limiter,
        )
        if not specialties:
            return None
        # Пробуем получить ID специальности
        first = specialties[0]
        specialty_id = first.get("FerIdSpesiality") or first.get("IdSpesiality")
        if not specialty_id:
            return None
        return await client.fetch_all_doctors(
            specialty_id=str(specialty_id),
            patient_id=str(params["patient_id"]),
            clinic_id=str(params["clinic_id"]),
            limiter=limiter,
        )

    elif endpoint == "appointment_list":
        # Цепочка: speciality_list -> doctor_list -> appointment_list
        specialties = await client.fetch_speciality_list(
            patient_id=str(params["patient_id"]),
            clinic_id=str(params["clinic_id"]),
            limiter=limiter,
        )
        if not specialties:
            return None
        first_spec = specialties[0]
        specialty_id = first_spec.get("FerIdSpesiality") or first_spec.get(
            "IdSpesiality"
        )
        if not specialty_id:
            return None

        doctors = await client.fetch_all_doctors(
            specialty_id=str(specialty_id),
            patient_id=str(params["patient_id"]),
            clinic_id=str(params["clinic_id"]),
            limiter=limiter,
        )
        if not doctors:
            return None
        first_doc = doctors[0]
        doc_id = first_doc.get("IdDoc")
        if not doc_id:
            return None

        return await client.check_slots(
            doc_id=str(doc_id),
            patient_id=str(params["patient_id"]),
            clinic_id=str(params["clinic_id"]),
            limiter=limiter,
        )

    elif endpoint == "clinic_list":
        return await client.fetch_clinic_list(
            district_id=settings.DISTRICT_ID,
            limiter=limiter,
        )

    logger.warning("schema_check: неизвестный эндпоинт '{}'", endpoint)
    return None


# ── Фоновый цикл ────────────────────────────────────────────────


async def schema_check_loop(
    client: Any,
    error_notifier: Any,
    metrics: Any,
    interval: int = 3600,
) -> None:
    """Фоновый цикл проверки схем API.

    Загружает эталонные схемы один раз при старте, затем в бесконечном
    цикле проверяет все 5 эндпоинтов с заданным интервалом.

    Args:
        client: Экземпляр ZdravClient.
        error_notifier: Экземпляр ErrorNotifier.
        metrics: Экземпляр PrometheusMetrics.
        interval: Интервал проверки в секундах (по умолчанию 3600).
    """
    # Загружаем эталонные схемы однократно
    reference_schemas = load_reference_schemas()
    if not reference_schemas:
        logger.error("Эталонные схемы не найдены, проверка схем API отключена")
        return

    logger.info("Цикл проверки схем API запущен (интервал: {}с)", interval)

    while True:
        try:
            for endpoint in _SCHEMA_CHECK_PARAMS:
                try:
                    diffs = await validate_endpoint_schema(
                        client, endpoint, reference_schemas
                    )

                    if diffs:
                        logger.error(
                            "Обнаружено расхождение схемы API: {} ({} расхождений)",
                            endpoint,
                            len(diffs),
                        )
                        for d in diffs:
                            logger.error("  {}", d)

                        # Алерт через ErrorNotifier
                        await error_notifier.notify_schema_change(
                            endpoint=endpoint,
                            diffs=diffs,
                        )

                        # Метрики
                        metrics.set_schema_drift(endpoint, True)
                        metrics.inc_schema_changes(endpoint, count=len(diffs))
                    else:
                        logger.debug("schema_check: {} — схемы совпадают", endpoint)
                        metrics.set_schema_drift(endpoint, False)

                except Exception as e:
                    logger.error(
                        "schema_check: ошибка проверки {}: {}",
                        endpoint,
                        e,
                    )
                    # Не фатально — продолжаем со следующим эндпоинтом

            # Пауза до следующего цикла
            await asyncio.sleep(interval)

        except asyncio.CancelledError:
            logger.info("Цикл проверки схем API остановлен (cancelled)")
            break
        except Exception as e:
            logger.error("Ошибка в цикле проверки схем: {}", e, exc_info=True)
            await asyncio.sleep(60)  # пауза перед retry
