import asyncio
import random

from loguru import logger

from src.api.models import SpecialityItem
from src.api.zdrav_client import ZdravClient
from src.config import settings
from src.database.database import Database


async def fetch_specialties(
    api: ZdravClient, patient_id: str, clinic_id: str, limiter=None
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
):
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
                all_doctors_with_specialty = []

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
                            all_doctors_with_specialty.extend(doctors)
                        await asyncio.sleep(random.uniform(1.0, 3.0))

                if all_doctors_with_specialty:
                    await database.merge_doctors(cid, all_doctors_with_specialty)
                    logger.info(
                        "Обновлен список врачей для %s: всего %s записей",
                        cid,
                        len(all_doctors_with_specialty),
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


async def sync_clinic_names(api: ZdravClient, database: Database):
    """Получает список клиник из API и сохраняет названия в БД."""
    try:
        clinics_data = await api.fetch_clinic_list()
        if not clinics_data:
            logger.warning("Не удалось получить список клиник из API")
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
    except Exception as e:
        logger.error(f"Ошибка синхронизации названий клиник: {e}", exc_info=True)
