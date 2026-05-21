import asyncio
import random

from aiolimiter import AsyncLimiter
from loguru import logger

from src.api.models import SpecialityItem
from src.api.zdrav_client import ZdravClient
from src.config import settings
from src.database.database import Database


async def fetch_specialties(
    api: ZdravClient,
    patient_id: str,
    clinic_id: str,
    limiter: AsyncLimiter | None = None,
) -> list[SpecialityItem]:
    """Получает список специальностей (ID и имя) для данной клиники и пациента."""
    try:
        response = await api.fetch_speciality_list(
            patient_id, clinic_id, limiter=limiter
        )
        # Конвертируем сырые dict-ы в SpecialityItem для атрибутного доступа
        return [
            SpecialityItem(**item)
            for item in response
            if item.get("IdSpesiality") and item.get("NameSpesiality")
        ]
    except Exception as e:
        logger.error(
            f"Ошибка получения специальностей для {clinic_id}: {e}", exc_info=True
        )
        return []


async def _get_clinic_type_from_db(database: "Database", clinic_id: str) -> str:
    """Получает тип клиники из БД. Если не найден — возвращает 'adult'."""
    try:
        clinic_type = await database.get_clinic_type(str(clinic_id))
        if clinic_type:
            return clinic_type
    except Exception:
        logger.debug("Не удалось получить тип клиники clinic_id={} из БД", clinic_id)
    return "adult"


async def discovery_loop(
    api: ZdravClient,
    database: Database,
    patient_id_adult: str,
    patient_id_child: str,
) -> None:
    """Цикл Discovery врачей — итерирует все активные clinic_ids из БД."""

    logger.info("Цикл Discovery врачей запущен (агрегированный)")

    while True:
        clinic_ids = await database.get_active_clinic_ids()
        if not clinic_ids:
            logger.warning("Нет активных клиник для discovery, ждём...")
            await asyncio.sleep(settings.DISCOVERY_INTERVAL)
            continue

        for clinic_id in clinic_ids:
            try:
                cid = str(clinic_id)

                # Получаем тип клиники (из БД)
                clinic_type = await _get_clinic_type_from_db(database, cid)

                # Сначала проверяем per-клиника discovery пациентов из БД
                clinic_patient_adult, clinic_patient_child = "", ""
                (
                    clinic_patient_adult,
                    clinic_patient_child,
                ) = await database.get_clinic_discovery_patients(cid)

                # Определяем, какие patient_id использовать для данной клиники
                # Приоритет: per-клиника из БД > глобальные из settings
                if clinic_type == "child":
                    patient_ids = [clinic_patient_child or patient_id_child]
                elif clinic_type == "all":
                    patient_ids = [
                        clinic_patient_adult or patient_id_adult,
                        clinic_patient_child or patient_id_child,
                    ]
                else:
                    patient_ids = [clinic_patient_adult or patient_id_adult]

                total_doctors = 0
                for current_patient_id in patient_ids:
                    specialties_data = await fetch_specialties(
                        api, current_patient_id, cid, limiter=api.limiter_discovery
                    )

                    for specialty_info in specialties_data:
                        spec_id = specialty_info.specialty_id
                        spec_name = specialty_info.specialty_name

                        doctors = await api.fetch_all_doctors(
                            specialty_id=spec_id,
                            patient_id=current_patient_id,
                            clinic_id=cid,
                            limiter=api.limiter_discovery,
                        )
                        if doctors:
                            for doc in doctors:
                                doc["SpesialityName"] = spec_name
                            # TD-SVC-002: частичное сохранение после каждой спец-ти
                            await database.merge_doctors(cid, doctors)
                            total_doctors += len(doctors)
                            logger.info(
                                "Обновлены врачи для {} / specialty {}: {} записей",
                                cid,
                                spec_id,
                                len(doctors),
                            )
                        # TD-SVC-003: фиксированная пауза 0.7с вместо случайной 1-3с
                        await asyncio.sleep(0.7)

                if total_doctors > 0:
                    logger.info(
                        "Цикл завершён для {}: обработано {} записей",
                        cid,
                        total_doctors,
                    )

            except asyncio.CancelledError:
                logger.info("Цикл discovery остановлен (cancelled)")
                return
            except Exception as e:
                logger.error(
                    f"Ошибка в цикле discovery для {clinic_id}: {e}", exc_info=True
                )

        jitter = random.uniform(0.8, 1.2)
        await asyncio.sleep(settings.DISCOVERY_INTERVAL * jitter)


# Счётчик последовательных ошибок для sync_clinic_names
# TD-SVC-004: после 3 сбоев подряд exc_info отключается, чтобы не засорять лог
_sync_consecutive_errors: int = 0


async def sync_clinic_names(api: ZdravClient, database: Database) -> None:
    """Получает список клиник из API и сохраняет названия в БД."""
    global _sync_consecutive_errors
    try:
        clinics_data = await api.fetch_clinic_list()
        if not clinics_data:
            logger.warning("Не удалось получить список клиник из API")
            _sync_consecutive_errors = 0
            return

        updated = 0
        for clinic in clinics_data:
            raw_id = clinic.get("IdLPU")
            if raw_id is None:
                continue
            clinic_id = str(raw_id)
            clinic_name = clinic.get("LpuName") or clinic.get("LPUShortName", "")
            if clinic_id and clinic_name:
                await database.upsert_clinic(clinic_id, clinic_name)
                updated += 1

        logger.info(
            f"Синхронизировано названий клиник: {updated} из {len(clinics_data)}"
        )
        _sync_consecutive_errors = 0
    except Exception as e:
        _sync_consecutive_errors += 1
        use_exc_info = _sync_consecutive_errors <= 3
        logger.error(
            f"Ошибка синхронизации названий клиник: {e}",
            exc_info=use_exc_info,
        )
