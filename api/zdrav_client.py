import asyncio
import datetime
import logging
import random
from typing import Any, List, Optional, Tuple

import aiolimiter
import httpx

from api.models import (
    AppointmentListResponse,
    CheckPatientResponse,
    ClinicListResponse,
    DoctorListResponse,
    SpecialityListResponse,
)
from config import settings

logger = logging.getLogger(__name__)


class ZdravClient:
    def __init__(self):
        self.base_url = settings.API_BASE_URL
        self.limiter = aiolimiter.AsyncLimiter(
            max_rate=10, time_period=60
        )  # 10 запросов в минуту
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/120.0.0.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/121.0.0.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/122.0.0.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
        ]
        self._client: Optional[httpx.AsyncClient] = None

    def _get_headers(self):
        return {
            "User-Agent": random.choice(self.user_agents),
            "Referer": settings.REFERER_URL,
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }

    async def _get_client(self) -> httpx.AsyncClient:
        """Возвращает переиспользуемый httpx-клиент (создает при первом вызове).
        trust_env=False отключает чтение HTTP_PROXY/HTTPS_PROXY из переменных
        окружения, т.к. там может быть socks4:// — неподдерживаемая httpx схема.
        Прокси для API zdrav не требуется — он внутри РФ.
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=settings.API_TIMEOUT, trust_env=False
            )
        return self._client

    async def close(self):
        """Закрывает HTTP-клиент. Вызывать при остановке бота."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def fetch_patient_id(
        self, fio: str, bday_date: datetime.date, clinic_id: str
    ) -> Tuple[Optional[str], Optional[str]]:
        parts = [p.strip() for p in fio.split() if p.strip()]
        if len(parts) != 3:
            return None, "Пожалуйста, введите ФИО (3 слова) полностью через пробел."

        iso_bday = bday_date.strftime("%Y-%m-%dT00:00:00.000Z")
        payload = {
            "patient_form-first_name": parts[1],
            "patient_form-last_name": parts[0],
            "patient_form-middle_name": parts[2],
            "patient_form-insurance_series": "",
            "patient_form-insurance_number": "",
            "patient_form-birthday": iso_bday,
            "patient_form-clinic_id": clinic_id,
            "csrfmiddlewaretoken": settings.CSRF_TOKEN,
        }

        async with self.limiter:
            client = await self._get_client()
            try:
                res = await client.post(
                    f"{self.base_url}/check_patient/",
                    data=payload,
                    headers=self._get_headers(),
                )
                if res.status_code == 200:
                    model = CheckPatientResponse.model_validate(res.json())
                    p_id = model.response.patient_id
                    if p_id:
                        return str(p_id), None
                    return (
                        None,
                        "Пациент не найден в базе поликлиники. Проверьте правильность введенных данных.",
                    )
                elif res.status_code in [403, 429]:
                    return (
                        None,
                        "Портал временно недоступен (защита от ботов). Попробуйте позже.",
                    )
                return None, f"Портал временно недоступен ({res.status_code})"
            except Exception as e:
                logger.error(f"Ошибка API (fetch_patient_id): {e}")
                return None, "Сервер zdrav.lenreg.ru не отвечает (Таймаут)"

    async def fetch_speciality_list(
        self, patient_id: str, clinic_id: str
    ) -> List[dict]:
        payload = {
            "clinic_form-clinic_id": clinic_id,
            "clinic_form-history_id": "",
            "clinic_form-patient_id": patient_id,
        }
        async with self.limiter:
            client = await self._get_client()
            try:
                res = await client.post(
                    f"{self.base_url}/speciality_list/",
                    data=payload,
                    headers=self._get_headers(),
                )
                if res.status_code == 200:
                    model = SpecialityListResponse.model_validate(res.json())
                    if model.success:
                        # Обратная совместимость: возвращаем list[dict]
                        return [
                            item.model_dump(by_alias=True) for item in model.response
                        ]
                return []
            except Exception as e:
                logger.error(f"Ошибка API (fetch_speciality_list): {e}")
                return []

    async def check_slots(
        self, doc_id: str, patient_id: str, clinic_id: str
    ) -> Optional[List[str]]:
        payload = {
            "doctor_form-doctor_id": doc_id,
            "doctor_form-clinic_id": clinic_id,
            "doctor_form-patient_id": patient_id,
        }
        async with self.limiter:
            client = await self._get_client()
            for i in range(3):
                try:
                    res = await client.post(
                        f"{self.base_url}/appointment_list/",
                        data=payload,
                        headers=self._get_headers(),
                    )
                    if res.status_code == 200:
                        model = AppointmentListResponse.model_validate(res.json())
                        logger.info(f"API response for {doc_id}: {model.response}")
                        slots = []
                        for date, items in model.response.items():
                            for s in items:
                                t = s.date_start.time
                                if t:
                                    slots.append(f"{date} в {t}")
                        if not slots:
                            logger.info(f"API returned 200 but no slots for {doc_id}")
                        return slots
                    elif res.status_code in [403, 429]:
                        logger.warning(
                            f"Заблокировано API (check_slots): {res.status_code}"
                        )
                        return None
                    elif res.status_code >= 500:
                        await asyncio.sleep(2)
                        continue
                except Exception as e:
                    logger.error(f"Ошибка API (check_slots), попытка {i+1}: {e}")
                    await asyncio.sleep(2)
        return None

    async def fetch_all_doctors(
        self, specialty_id: str, patient_id: str, clinic_id: str
    ) -> List[dict]:
        payload = {
            "speciality_form-speciality_id": specialty_id,
            "speciality_form-clinic_id": clinic_id,
            "speciality_form-patient_id": patient_id,
            "speciality_form-history_id": "",
        }
        async with self.limiter:
            client = await self._get_client()
            for i in range(3):
                try:
                    res = await client.post(
                        f"{self.base_url}/doctor_list/",
                        data=payload,
                        headers=self._get_headers(),
                    )
                    if res.status_code == 200:
                        model = DoctorListResponse.model_validate(res.json())
                        if model.success:
                            # Обратная совместимость: возвращаем list[dict]
                            return [
                                item.model_dump(by_alias=True)
                                for item in model.response
                            ]
                    elif res.status_code >= 500:
                        await asyncio.sleep(2)
                        continue
                except Exception as e:
                    logger.error(f"Ошибка API (fetch_all_doctors), попытка {i+1}: {e}")
                    await asyncio.sleep(2)
        return []

    async def fetch_clinic_list(self, district_id: str = "4") -> list[dict]:
        """Получает список клиник для указанного района через /clinic_list/."""
        payload = {
            "district_form-district_id": district_id,
        }
        async with self.limiter:
            client = await self._get_client()
            try:
                res = await client.post(
                    f"{self.base_url}/clinic_list/",
                    data=payload,
                    headers=self._get_headers(),
                )
                if res.status_code == 200:
                    model = ClinicListResponse.model_validate(res.json())
                    if model.success:
                        # Обратная совместимость: возвращаем list[dict]
                        return [
                            item.model_dump(by_alias=True) for item in model.response
                        ]
                logger.warning(
                    f"clinic_list вернул {res.status_code} для района {district_id}"
                )
                return []
            except Exception as e:
                logger.error(f"Ошибка API (fetch_clinic_list): {e}")
                return []
