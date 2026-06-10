"""
Скрипт генерации эталонных JSON Schema для Pydantic-моделей API zdrav.lenreg.ru.

Запуск:
    python scripts/generate_api_schemas.py

Создаёт директорию docs/schemas/ и сохраняет в ней .json файлы для каждой
Pydantic-модели из src/api/models.py с помощью model_json_schema().

Сгенерированные схемы коммитятся в Git — это эталон, с которым
сравнивается рантайм в schema_watcher.py.
"""

import json
import logging
import sys
from pathlib import Path

from pydantic import BaseModel

# Добавляем корень проекта в sys.path для импорта src.*
_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

from src.api.models import (  # noqa: E402
    AppointmentListResponse,
    AppointmentSlot,
    CheckPatientData,
    CheckPatientResponse,
    ClinicItem,
    ClinicListResponse,
    DateInfo,
    DoctorItem,
    DoctorListResponse,
    SpecialityItem,
    SpecialityListResponse,
)

logger = logging.getLogger(__name__)

# Список Pydantic-моделей для генерации схем
MODELS: list[type[BaseModel]] = [
    CheckPatientResponse,
    CheckPatientData,
    SpecialityListResponse,
    SpecialityItem,
    DoctorListResponse,
    DoctorItem,
    AppointmentListResponse,
    AppointmentSlot,
    ClinicListResponse,
    ClinicItem,
    DateInfo,
]

SCHEMAS_DIR = Path("docs/schemas")


def main() -> None:
    """Генерирует эталонные JSON Schema и сохраняет в docs/schemas/."""
    # Создаём директорию, если её нет
    SCHEMAS_DIR.mkdir(parents=True, exist_ok=True)

    for model in MODELS:
        schema = model.model_json_schema()
        filepath = SCHEMAS_DIR / f"{model.__name__}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=2, ensure_ascii=False)
        logger.info("Сгенерирована схема: %s → %s", model.__name__, filepath)

    logger.info(
        "Генерация завершена. Создано %d схем в %s",
        len(MODELS),
        SCHEMAS_DIR,
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    main()
