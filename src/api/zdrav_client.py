import asyncio
import datetime
import json
import random
from typing import Any, TypeVar, cast

import aiolimiter
import httpx
from loguru import logger
from pydantic import BaseModel, ValidationError

from src.api.models import (
    AppointmentListRequest,
    AppointmentListResponse,
    CheckPatientRequest,
    CheckPatientResponse,
    ClinicListRequest,
    ClinicListResponse,
    DoctorListRequest,
    DoctorListResponse,
    SpecialityListRequest,
    SpecialityListResponse,
)
from src.config import settings
from src.i18n import _

# TypeVar для сохранения конкретного типа Pydantic-модели в _validate_response
M = TypeVar("M", bound=BaseModel)


class ZdravClient:
    def __init__(self):
        self.base_url = settings.API_BASE_URL
        # Отдельные лимитеры для разных фоновых задач (R7)
        self.limiter_monitor = aiolimiter.AsyncLimiter(
            max_rate=10, time_period=60
        )  # мониторинг слотов
        self.limiter_discovery = aiolimiter.AsyncLimiter(
            max_rate=5, time_period=60
        )  # discovery врачей
        self.limiter_healthcheck = aiolimiter.AsyncLimiter(
            max_rate=30, time_period=60
        )  # healthcheck
        self.limiter = aiolimiter.AsyncLimiter(
            max_rate=10, time_period=60
        )  # для хендлеров (пользовательские запросы)
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/120.0.0.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/121.0.0.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/122.0.0.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) "
            "Gecko/20100101 Firefox/123.0",
        ]
        self._base_headers = {
            "Referer": settings.REFERER_URL,
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-CSRFToken": settings.CSRF_TOKEN,
            "Cookie": f"csrftoken={settings.CSRF_TOKEN}",
            "Origin": settings.ORIGIN_URL,
            "X-Client-Version": settings.API_VERSION,
        }
        self._client: httpx.AsyncClient | None = None

    def _get_headers(self):
        return {
            **self._base_headers,
            "User-Agent": random.choice(self.user_agents),
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

    async def close(self) -> None:
        """Закрывает HTTP-клиент. Вызывать при остановке бота."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _validate_response(
        self,
        json_data: dict[str, Any],
        model_class: type[M],
        endpoint_name: str,
        request_url: str,
    ) -> M:
        """Валидирует JSON-ответ API через Pydantic-модель.

        Если API_VALIDATE_RESPONSES=True — при ошибке валидации логирует
        детали расхождения (эндпоинт, поля, типы, URL) и пробрасывает
        ValidationError.
        Если API_VALIDATE_RESPONSES=False — ошибка только логируется,
        исключение не пробрасывается.
        """
        try:
            return model_class.model_validate(json_data)
        except ValidationError as e:
            # Детальное логирование каждого ошибочного поля
            for error in e.errors():
                field_path = ".".join(str(loc) for loc in error["loc"])
                logger.error(
                    "Несоответствие схемы API | Эндпоинт: %s | "
                    "Поле: %s | Ожидаемый тип: %s | Получено: %s | URL: %s",
                    endpoint_name,
                    field_path,
                    error.get("type", "?"),
                    repr(error.get("input", "?")),
                    request_url,
                )
            if settings.API_VALIDATE_RESPONSES:
                raise
            logger.warning(
                "Валидация ответа API отключена, продолжаю с сырыми данными "
                "(эндпоинт: %s, URL: %s)",
                endpoint_name,
                request_url,
            )
            return cast(M, json_data)

    async def fetch_patient_id(
        self,
        fio: str,
        bday_date: datetime.date,
        clinic_id: str,
        limiter: aiolimiter.AsyncLimiter | None = None,
    ) -> tuple[str | None, str | None]:
        parts = [p.strip() for p in fio.split() if p.strip()]
        if len(parts) != 3:
            return (
                None,
                _("api-fio-3-words-error"),
            )

        iso_bday = bday_date.strftime("%Y-%m-%dT00:00:00.000Z")
        payload = CheckPatientRequest.model_validate(
            {
                "patient_form-first_name": parts[1],
                "patient_form-last_name": parts[0],
                "patient_form-middle_name": parts[2],
                "patient_form-insurance_series": "",
                "patient_form-insurance_number": "",
                "patient_form-birthday": iso_bday,
                "patient_form-clinic_id": clinic_id,
                "csrfmiddlewaretoken": settings.CSRF_TOKEN,
            }
        ).model_dump(by_alias=True)

        async with limiter or self.limiter:
            client = await self._get_client()
            for i in range(3):
                try:
                    res = await client.post(
                        f"{self.base_url}/check_patient/",
                        data=payload,
                        headers=self._get_headers(),
                    )
                    if res.status_code == 200:
                        model = self._validate_response(
                            res.json(),
                            CheckPatientResponse,
                            "check_patient",
                            f"{self.base_url}/check_patient/",
                        )
                        p_id = model.response.patient_id
                        if p_id:
                            return str(p_id), None
                        return (
                            None,
                            _("api-patient-not-found"),
                        )
                    elif res.status_code == 403:
                        logger.error(
                            "Доступ запрещён (fetch_patient_id): статус 403, "
                            "возможно истекла сессия/CSRF",
                            exc_info=True,
                        )
                        return None, _("api-forbidden")
                    elif res.status_code == 429:
                        logger.warning(
                            "Превышен лимит запросов (fetch_patient_id): статус 429",
                            exc_info=True,
                        )
                        return None, _("api-rate-limited")
                    elif res.status_code >= 500:
                        await asyncio.sleep(2)
                        continue
                    return None, _("api-temp-unavailable").format(
                        status=res.status_code
                    )
                except httpx.TimeoutException as e:
                    logger.error(
                        f"Таймаут API (fetch_patient_id), попытка {i + 1}: {e!r}",
                        exc_info=True,
                    )
                    if i < 2:
                        await asyncio.sleep(2)
                except httpx.NetworkError as e:
                    logger.error(
                        f"Сетевая ошибка API (fetch_patient_id), "
                        f"попытка {i + 1}: {e!r}",
                        exc_info=True,
                    )
                    if i < 2:
                        await asyncio.sleep(2)
                except (json.JSONDecodeError, ValidationError) as e:
                    logger.error(
                        f"Ошибка парсинга API (fetch_patient_id), "
                        f"попытка {i + 1}: {e!r}",
                        exc_info=True,
                    )
                    if i < 2:
                        await asyncio.sleep(2)
                except Exception as e:
                    exc_repr = repr(e) if not str(e) else str(e)
                    logger.error(
                        "Неожиданная ошибка API (fetch_patient_id), "
                        f"попытка {i + 1}: {exc_repr}",
                        exc_info=True,
                    )
                    if i < 2:
                        await asyncio.sleep(2)
            return None, _("api-timeout")

    async def fetch_speciality_list(
        self,
        patient_id: str,
        clinic_id: str,
        limiter: aiolimiter.AsyncLimiter | None = None,
    ) -> list[dict]:
        payload = SpecialityListRequest.model_validate(
            {
                "clinic_form-clinic_id": clinic_id,
                "clinic_form-history_id": "",
                "clinic_form-patient_id": patient_id,
            }
        ).model_dump(by_alias=True)
        async with limiter or self.limiter:
            client = await self._get_client()
            for i in range(3):
                try:
                    res = await client.post(
                        f"{self.base_url}/speciality_list/",
                        data=payload,
                        headers=self._get_headers(),
                    )
                    if res.status_code == 200:
                        model = self._validate_response(
                            res.json(),
                            SpecialityListResponse,
                            "speciality_list",
                            f"{self.base_url}/speciality_list/",
                        )
                        if model.success:
                            # Обратная совместимость: возвращаем list[dict]
                            return [
                                item.model_dump(by_alias=True)
                                for item in model.response
                            ]
                    elif res.status_code == 403:
                        logger.error(
                            "Доступ запрещён (fetch_speciality_list): статус 403, "
                            "возможно истекла сессия/CSRF",
                            exc_info=True,
                        )
                        return []
                    elif res.status_code == 429:
                        logger.warning(
                            "Превышен лимит запросов (fetch_speciality_list): "
                            "статус 429",
                            exc_info=True,
                        )
                        return []
                    elif res.status_code >= 500:
                        await asyncio.sleep(2)
                        continue
                    return []
                except httpx.TimeoutException as e:
                    logger.error(
                        f"Таймаут API (fetch_speciality_list), попытка {i + 1}: {e!r}",
                        exc_info=True,
                    )
                    if i < 2:
                        await asyncio.sleep(2)
                except httpx.NetworkError as e:
                    logger.error(
                        f"Сетевая ошибка API (fetch_speciality_list), "
                        f"попытка {i + 1}: {e!r}",
                        exc_info=True,
                    )
                    if i < 2:
                        await asyncio.sleep(2)
                except (json.JSONDecodeError, ValidationError) as e:
                    logger.error(
                        f"Ошибка парсинга API (fetch_speciality_list), "
                        f"попытка {i + 1}: {e!r}",
                        exc_info=True,
                    )
                    if i < 2:
                        await asyncio.sleep(2)
                except Exception as e:
                    exc_repr = repr(e) if not str(e) else str(e)
                    logger.error(
                        "Неожиданная ошибка API (fetch_speciality_list), "
                        f"попытка {i + 1}: {exc_repr}",
                        exc_info=True,
                    )
                    if i < 2:
                        await asyncio.sleep(2)
            return []

    async def check_slots(
        self,
        doc_id: str,
        patient_id: str,
        clinic_id: str,
        limiter: aiolimiter.AsyncLimiter | None = None,
    ) -> list[str] | None:
        """Проверяет доступные слоты для записи к указанному врачу.

        Выполняет POST-запрос к эндпоинту /appointment_list/ и возвращает
        отсортированный список доступных слотов.

        Args:
            doc_id: Идентификатор врача.
            patient_id: Идентификатор пациента.
            clinic_id: Идентификатор клиники.
            limiter: Опциональный aiolimiter для контроля частоты запросов.
                     Если не указан, используется limiter по умолчанию.

        Returns:
            None — ошибка API (исчерпаны попытки, 403/429 и т.п.).
            [] — успешный запрос, но слотов нет.
            ["DD.MM.YYYY в HH:MM", ...] — список доступных дат и времени.

        Raises:
            ZdravTimeoutError: При таймауте запроса (внутреннее логирование,
                               метод возвращает None).
            ZdravNetworkError: При сетевой ошибке (внутреннее логирование,
                               метод возвращает None).
            ZdravParseError: При ошибке парсинга ответа (внутреннее
                             логирование, метод возвращает None).
        """
        payload = AppointmentListRequest.model_validate(
            {
                "doctor_form-doctor_id": doc_id,
                "doctor_form-clinic_id": clinic_id,
                "doctor_form-patient_id": patient_id,
                "doctor_form-history_id": "",
                "doctor_form-appointment_type": "",
            }
        ).model_dump(by_alias=True)
        async with limiter or self.limiter:
            client = await self._get_client()
            for i in range(3):
                try:
                    res = await client.post(
                        f"{self.base_url}/appointment_list/",
                        data=payload,
                        headers=self._get_headers(),
                    )
                    if res.status_code == 200:
                        model = self._validate_response(
                            res.json(),
                            AppointmentListResponse,
                            "appointment_list",
                            f"{self.base_url}/appointment_list/",
                        )
                        logger.info(f"API response for {doc_id}: {model.response}")
                        slots = []
                        for date, items in model.response.items():
                            for s in items:
                                t = s.date_start.time
                                if t:
                                    slots.append(f"{date} в {t}")
                        # Сортируем слоты по дате и времени (п.4)
                        slots.sort()
                        if not slots:
                            logger.info(f"API returned 200 but no slots for {doc_id}")
                        return slots
                    elif res.status_code in [403, 429]:
                        logger.warning(
                            f"Заблокировано API (check_slots): {res.status_code}",
                            exc_info=True,
                        )
                        return None
                    elif res.status_code >= 500:
                        await asyncio.sleep(2)
                        continue
                except httpx.TimeoutException as e:
                    logger.error(
                        f"Таймаут API (check_slots), попытка {i + 1}: {e!r}",
                        exc_info=True,
                    )
                    await asyncio.sleep(2)
                except httpx.NetworkError as e:
                    logger.error(
                        f"Сетевая ошибка API (check_slots), попытка {i + 1}: {e!r}",
                        exc_info=True,
                    )
                    await asyncio.sleep(2)
                except (json.JSONDecodeError, ValidationError) as e:
                    logger.error(
                        f"Ошибка парсинга API (check_slots), попытка {i + 1}: {e!r}",
                        exc_info=True,
                    )
                    await asyncio.sleep(2)
                except Exception as e:
                    exc_repr = repr(e) if not str(e) else str(e)
                    logger.error(
                        f"Неожиданная ошибка API (check_slots), "
                        f"попытка {i + 1}: {exc_repr}",
                        exc_info=True,
                    )
                    await asyncio.sleep(2)
        return None

    async def fetch_all_doctors(
        self,
        specialty_id: str = "",
        patient_id: str = "",
        clinic_id: str = "",
        limiter: aiolimiter.AsyncLimiter | None = None,
        specialty_name: str = "",
    ) -> list[dict]:
        """Получает список врачей для указанной специальности.

        Args:
            specialty_id: ID специальности (пустая строка — без фильтрации).
            patient_id: ID пациента.
            clinic_id: ID клиники.
            limiter: Опциональный лимитер запросов.
            specialty_name: Название специальности (проставляется в _specialty_name).

        Returns:
            Список словарей с данными врачей.
        """
        payload = DoctorListRequest.model_validate(
            {
                "speciality_form-speciality_id": specialty_id,
                "speciality_form-clinic_id": clinic_id,
                "speciality_form-patient_id": patient_id,
                "speciality_form-history_id": "",
            }
        ).model_dump(by_alias=True)
        async with limiter or self.limiter:
            client = await self._get_client()
            for i in range(3):
                try:
                    res = await client.post(
                        f"{self.base_url}/doctor_list/",
                        data=payload,
                        headers=self._get_headers(),
                    )
                    if res.status_code == 200:
                        model = self._validate_response(
                            res.json(),
                            DoctorListResponse,
                            "doctor_list",
                            f"{self.base_url}/doctor_list/",
                        )
                        if model.success:
                            # Обратная совместимость: возвращаем list[dict]
                            result = [
                                item.model_dump(by_alias=True)
                                for item in model.response
                            ]
                            # Проставляем specialty_name если передан
                            if specialty_name:
                                for doc in result:
                                    doc["_specialty_name"] = specialty_name
                            return result
                    elif res.status_code == 403:
                        logger.error(
                            "Доступ запрещён (fetch_all_doctors): статус 403, "
                            "возможно истекла сессия/CSRF",
                            exc_info=True,
                        )
                        return []
                    elif res.status_code == 429:
                        logger.warning(
                            "Превышен лимит запросов (fetch_all_doctors): статус 429",
                            exc_info=True,
                        )
                        return []
                    elif res.status_code >= 500:
                        await asyncio.sleep(2)
                        continue
                except httpx.TimeoutException as e:
                    logger.error(
                        f"Таймаут API (fetch_all_doctors), попытка {i + 1}: {e!r}",
                        exc_info=True,
                    )
                    await asyncio.sleep(2)
                except httpx.NetworkError as e:
                    logger.error(
                        f"Сетевая ошибка API (fetch_all_doctors), "
                        f"попытка {i + 1}: {e!r}",
                        exc_info=True,
                    )
                    await asyncio.sleep(2)
                except (json.JSONDecodeError, ValidationError) as e:
                    logger.error(
                        f"Ошибка парсинга API (fetch_all_doctors), "
                        f"попытка {i + 1}: {e!r}",
                        exc_info=True,
                    )
                    await asyncio.sleep(2)
                except Exception as e:
                    exc_repr = repr(e) if not str(e) else str(e)
                    logger.error(
                        f"Неожиданная ошибка API (fetch_all_doctors), "
                        f"попытка {i + 1}: {exc_repr}",
                        exc_info=True,
                    )
                    await asyncio.sleep(2)
        return []

    async def fetch_all_doctors_for_clinic(
        self,
        patient_id: str,
        clinic_id: str,
        limiter: aiolimiter.AsyncLimiter | None = None,
    ) -> list[dict]:
        """Получает список ВСЕХ врачей клиники (по всем специальностям).

        Сначала получает список специальностей через ``fetch_speciality_list``,
        фильтрует только врачебные (is_doc=True, is_tech=False), затем для каждой
        специальности получает врачей через ``fetch_all_doctors``.

        Args:
            patient_id: ID пациента.
            clinic_id: ID клиники.
            limiter: Опциональный лимитер запросов.

        Returns:
            Объединённый список врачей всех специальностей.
            Каждый врач содержит поле ``_specialty_name`` с названием специальности.
        """
        # Шаг 1: получаем список специальностей
        specialties_raw = await self.fetch_speciality_list(
            patient_id=patient_id,
            clinic_id=clinic_id,
            limiter=limiter,
        )

        if not specialties_raw:
            logger.warning(
                "fetch_all_doctors_for_clinic: специальности не найдены "
                "для clinic_id=%s, patient_id=%s",
                clinic_id,
                patient_id,
            )
            return []

        # Фильтруем: только врачебные, не технические
        doc_specialties: list[dict] = []
        for spec in specialties_raw:
            is_doc = spec.get("IsDoc", False)
            is_tech = spec.get("IsTech", False)
            if is_doc and not is_tech:
                doc_specialties.append(spec)

        if not doc_specialties:
            logger.warning(
                "fetch_all_doctors_for_clinic: нет врачебных специальностей "
                "для clinic_id=%s",
                clinic_id,
            )
            return []

        logger.info(
            "fetch_all_doctors_for_clinic: загружаем врачей по %d специальностям "
            "для clinic_id=%s",
            len(doc_specialties),
            clinic_id,
        )

        # Шаг 2: параллельно получаем врачей для каждой специальности
        # Используем semaphore для ограничения конкурентности
        sem = asyncio.Semaphore(3)

        async def _fetch_for_specialty(spec: dict) -> list[dict]:
            spec_id = str(spec.get("IdSpesiality", ""))
            spec_name = spec.get("NameSpesiality", "") or spec.get("Name", "")
            async with sem:
                doctors = await self.fetch_all_doctors(
                    specialty_id=spec_id,
                    patient_id=patient_id,
                    clinic_id=clinic_id,
                    limiter=limiter,
                    specialty_name=spec_name,
                )
                # Добавляем IdSpesiality в каждого врача для обратной совместимости
                for doc in doctors:
                    doc["IdSpesiality"] = spec_id
                return doctors

        tasks = [_fetch_for_specialty(spec) for spec in doc_specialties]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Шаг 3: объединяем всех врачей
        all_doctors: list[dict] = []
        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                spec_name = doc_specialties[i].get("NameSpesiality", "?")
                logger.error(
                    "Ошибка загрузки врачей для специальности '%s': %s",
                    spec_name,
                    result,
                )
                continue
            all_doctors.extend(cast(list[dict], result))

        logger.info(
            "fetch_all_doctors_for_clinic: загружено %d врачей для clinic_id=%s",
            len(all_doctors),
            clinic_id,
        )

        return all_doctors

    async def fetch_clinic_list(
        self,
        district_id: str = settings.DISTRICT_ID,
        limiter: aiolimiter.AsyncLimiter | None = None,
    ) -> list[dict]:
        """Получает список клиник для указанного района через /clinic_list/."""
        payload = ClinicListRequest.model_validate(
            {
                "district_form-district_id": district_id,
            }
        ).model_dump(by_alias=True)
        async with limiter or self.limiter:
            client = await self._get_client()
            for i in range(3):
                try:
                    res = await client.post(
                        f"{self.base_url}/clinic_list/",
                        data=payload,
                        headers=self._get_headers(),
                    )
                    if res.status_code == 200:
                        model = self._validate_response(
                            res.json(),
                            ClinicListResponse,
                            "clinic_list",
                            f"{self.base_url}/clinic_list/",
                        )
                        if model.success:
                            # Обратная совместимость: возвращаем list[dict]
                            return [
                                item.model_dump(by_alias=True)
                                for item in model.response
                            ]
                    elif res.status_code == 403:
                        logger.error(
                            "Доступ запрещён (fetch_clinic_list): статус 403, "
                            "возможно истекла сессия/CSRF",
                            exc_info=True,
                        )
                        return []
                    elif res.status_code == 429:
                        logger.warning(
                            "Превышен лимит запросов (fetch_clinic_list): статус 429",
                            exc_info=True,
                        )
                        return []
                    elif res.status_code >= 500:
                        await asyncio.sleep(2)
                        continue
                    logger.warning(
                        f"clinic_list вернул {res.status_code} для района "
                        f"{district_id}",
                        exc_info=True,
                    )
                    return []
                except httpx.TimeoutException as e:
                    logger.error(
                        f"Таймаут API (fetch_clinic_list), попытка {i + 1}: {e!r}",
                        exc_info=True,
                    )
                    if i < 2:
                        await asyncio.sleep(2)
                except httpx.NetworkError as e:
                    logger.error(
                        f"Сетевая ошибка API (fetch_clinic_list), "
                        f"попытка {i + 1}: {e!r}",
                        exc_info=True,
                    )
                    if i < 2:
                        await asyncio.sleep(2)
                except (json.JSONDecodeError, ValidationError) as e:
                    logger.error(
                        f"Ошибка парсинга API (fetch_clinic_list), "
                        f"попытка {i + 1}: {e!r}",
                        exc_info=True,
                    )
                    if i < 2:
                        await asyncio.sleep(2)
                except Exception as e:
                    exc_repr = repr(e) if not str(e) else str(e)
                    logger.error(
                        f"Неожиданная ошибка API (fetch_clinic_list), "
                        f"попытка {i + 1}: {exc_repr}",
                        exc_info=True,
                    )
                    if i < 2:
                        await asyncio.sleep(2)
            return []
