import asyncio
import logging
import random
from typing import Dict, List

from src.api.zdrav_client import ZdravClient
from src.config import settings
from src.database.database import Database
from src.database.doctor_manager import DoctorManager

logger = logging.getLogger(__name__)


async def fetch_specialties(
    api: ZdravClient, patient_id: str, clinic_id: str, limiter=None
) -> List[Dict[str, str]]:
    """Получает список специальностей (ID и имя) для данной клиники и пациента."""
    try:
        response = await api.fetch_speciality_list(
            patient_id, clinic_id, limiter=limiter
        )
        # Приводим к типу List[Dict[str, str]], гарантируя, что значения - строки
        return [
            {
                "IdSpesiality": str(s.get("IdSpesiality", "")),
                "NameSpesiality": str(s.get("NameSpesiality", "")),
            }
            for s in response
            if s.get("IdSpesiality") and s.get("NameSpesiality")
        ]
    except Exception as e:
        logger.error(
            f"Ошибка получения специальностей для {clinic_id}: {e}", exc_info=True
        )
        return []


async def _get_clinic_type_from_db(database, clinic_id: str) -> str:
    """Получает тип клиники из БД. Если не найден — возвращает 'adult'."""
    try:
        clinic_type = await database.get_clinic_type(str(clinic_id))
        if clinic_type:
            return clinic_type
    except Exception:
        pass
    return "adult"


async def discovery_loop(
    api: ZdravClient,
    doctor_manager: DoctorManager,
    clinic_id: str,
    patient_id_adult: str,
    patient_id_child: str,
):
    logger.info(f"Цикл Discovery врачей для поликлиники {clinic_id} запущен")

    while True:
        try:
            all_doctors_with_specialty = []

            db = doctor_manager._db

            # Получаем тип клиники (из БД)
            clinic_type = await _get_clinic_type_from_db(db, clinic_id)

            # Сначала проверяем per-клиника discovery пациентов из БД
            clinic_patient_adult, clinic_patient_child = "", ""
            if db:
                (
                    clinic_patient_adult,
                    clinic_patient_child,
                ) = await db.get_clinic_discovery_patients(clinic_id)

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
                    api, current_patient_id, clinic_id, limiter=api.limiter_discovery
                )

                for specialty_info in specialties_data:
                    spec_id = specialty_info["IdSpesiality"]
                    spec_name = specialty_info["NameSpesiality"]

                    doctors = await api.fetch_all_doctors(
                        specialty_id=spec_id,
                        patient_id=current_patient_id,
                        clinic_id=str(clinic_id),
                        limiter=api.limiter_discovery,
                    )
                    if doctors:
                        for doc in doctors:
                            doc["SpesialityName"] = (
                                spec_name  # Добавляем имя специальности к каждому врачу
                            )
                        all_doctors_with_specialty.extend(doctors)
                    await asyncio.sleep(
                        random.uniform(1.0, 3.0)
                    )  # Случайная пауза между запросами специальностей

            if all_doctors_with_specialty:
                await doctor_manager.merge_doctors(
                    str(clinic_id), all_doctors_with_specialty
                )
                logger.info(
                    f"Обновлен список врачей для {clinic_id}: всего {len(all_doctors_with_specialty)} записей"
                )

            jitter = random.uniform(0.8, 1.2)
            await asyncio.sleep(settings.DISCOVERY_INTERVAL * jitter)
        except asyncio.CancelledError:
            logger.info(f"Цикл discovery для {clinic_id} остановлен (cancelled)")
            break
        except Exception as e:
            logger.error(
                f"Ошибка в цикле discovery для {clinic_id}: {e}", exc_info=True
            )
            await asyncio.sleep(300)


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
