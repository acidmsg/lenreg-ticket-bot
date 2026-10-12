"""
Доменная логика экрана «Выберите врача» Mini App.

Модуль не зависит от HTTP: собирает список врачей клиники с талонами из кэша,
подходящими под фильтр талонов и отметками мониторинга. Discovery-оркестрация
остаётся в web-слое: ``services`` не имеет права зависеть от ``handlers``.
"""

from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from src.database.manager import DatabaseManager
from src.database.types import MonitoringEntry
from src.utils.cache import get_cache_key
from src.utils.helpers import safe_name


@dataclass(frozen=True, slots=True)
class DoctorCatalogQuery:
    """Параметры экрана «Выберите врача»."""

    clinic_id: str
    patient_id: str
    specialty_id: str | None = None


@dataclass(frozen=True, slots=True)
class MonitoringSnapshot:
    """Мониторинг пользователя: отслеживаемые врачи и фильтры пациента."""

    monitored_ids: frozenset[str] = frozenset()
    patient_monitoring: dict[str, MonitoringEntry] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CatalogContext:
    """Данные, собранные для сборки ответа экрана врачей."""

    doctors: dict[str, Any]
    visible_ids: list[str]
    specialty_id: str | None
    slots_map: dict[str, dict[str, Any]]
    monitoring: MonitoringSnapshot
    telegram_id: str
    patient_id: str


def visible_doctor_ids(doctors: dict[str, Any], specialty_id: str | None) -> list[str]:
    """ID врачей, видимых после фильтра специальности (пустой фильтр — все)."""
    return [
        doc_id
        for doc_id, doc_info in doctors.items()
        if not specialty_id or doc_info.get("specialty", "") == specialty_id
    ]


async def load_monitoring(
    db: DatabaseManager, telegram_id: str, patient_id: str
) -> MonitoringSnapshot:
    """Читает мониторинг пользователя для отметок ``is_monitored`` и фильтров.

    Ошибка чтения данных не ломает экран: возвращается пустой снимок.
    """
    monitored_ids: set[str] = set()
    patient_monitoring: dict[str, MonitoringEntry] = {}
    try:
        user_data = await db.get_user_data(telegram_id)
        monitoring = user_data.get("monitoring", {})
        for _p_id, monitored_doctors in monitoring.items():
            for d_id in monitored_doctors:
                monitored_ids.add(d_id)
        patient_monitoring = dict(monitoring.get(patient_id, {}))
    except Exception:
        logger.exception("Ошибка получения данных мониторинга для uid={}", telegram_id)
    return MonitoringSnapshot(
        monitored_ids=frozenset(monitored_ids),
        patient_monitoring=patient_monitoring,
    )


async def matching_free_tickets(
    telegram_id: str,
    p_id: str,
    d_id: str,
    monitoring_entry: MonitoringEntry | None,
    free_tickets: int,
) -> int:
    """Вычисляет число талонов, подходящих под фильтр отслеживания.

    Живой ответ API содержит только счётчик свободных талонов, поэтому фильтр
    применяется к списку слотов из Redis-кэша мониторинга. Если фильтр не
    задан — возвращается общий счётчик ``free_tickets``.
    """
    from src.services.monitor import filter_slots_by_user_prefs, has_slot_filters

    if monitoring_entry is None or not has_slot_filters(monitoring_entry):
        return free_tickets

    cache_key = f"{telegram_id}_{p_id}_{d_id}"
    cached_value = await get_cache_key(cache_key)
    if not isinstance(cached_value, list) or not cached_value:
        return 0

    return len(filter_slots_by_user_prefs(list(cached_value), monitoring_entry))


async def build_doctors(ctx: CatalogContext) -> list[dict[str, Any]]:
    """Собирает список врачей ответа: талоны из кэша + флаг мониторинга."""
    doctors: list[dict[str, Any]] = []
    for doc_id in ctx.visible_ids:
        doc_info = ctx.doctors[doc_id]
        slots = ctx.slots_map.get(doc_id, {})
        free_tickets = int(slots.get("free_tickets", 0))
        doctors.append(
            {
                "doctor_id": doc_id,
                "name": safe_name(doc_info.get("name", "")),
                "specialty_name": doc_info.get("specialty", ""),
                "specialty_id": ctx.specialty_id or "",
                "free_tickets": free_tickets,
                "matching_free_tickets": await matching_free_tickets(
                    telegram_id=ctx.telegram_id,
                    p_id=ctx.patient_id,
                    d_id=doc_id,
                    monitoring_entry=ctx.monitoring.patient_monitoring.get(doc_id),
                    free_tickets=free_tickets,
                ),
                "nearest_date": slots.get("nearest_date"),
                "is_monitored": doc_id in ctx.monitoring.monitored_ids,
            }
        )
    return doctors
