import asyncio
import logging
import random
from typing import Dict, List

from api.zdrav_client import ZdravClient
from config import settings
from database.doctor_manager import DoctorManager

logger = logging.getLogger(__name__)


async def fetch_specialties(
    api: ZdravClient, patient_id: str, clinic_id: str
) -> List[Dict[str, str]]:
    """Получает список специальностей (ID и имя) для данной клиники и пациента."""
    try:
        response = await api.fetch_speciality_list(patient_id, clinic_id)
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

            current_patient_id = patient_id_adult
            if str(clinic_id) == "161":  # Детская
                current_patient_id = patient_id_child

            specialties_data = await fetch_specialties(
                api, current_patient_id, clinic_id
            )

            for specialty_info in specialties_data:
                spec_id = specialty_info["IdSpesiality"]
                spec_name = specialty_info["NameSpesiality"]

                doctors = await api.fetch_all_doctors(
                    specialty_id=spec_id,
                    patient_id=current_patient_id,
                    clinic_id=str(clinic_id),
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
