"""
Статические утилиты сравнения JSON Schema для API zdrav.lenreg.ru.

Сравнивает эталонные JSON Schema из docs/schemas/ с текущими Pydantic-моделями.
Рантайм-проверка через HTTP-запросы отключена (Задача 2.8 ROADMAP) —
валидация выполняется статически через scripts/generate_api_schemas.py.

Использование:
    from src.services.schema_watcher import compare_schemas, load_reference_schemas

    ref = load_reference_schemas()
    current = MyModel.model_json_schema()
    diffs = compare_schemas(current, ref["MyModel"])
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Директория эталонных схем по умолчанию
_DEFAULT_SCHEMAS_DIR = Path("docs/schemas")


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
