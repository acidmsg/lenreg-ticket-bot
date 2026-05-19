import asyncio
import datetime
import json
import random
from typing import Any, TypeVar

import aiolimiter
import httpx
from loguru import logger
from pydantic import BaseModel, ValidationError

from src.api.models import (
    AppointmentListResponse,
    CheckPatientResponse,
    ClinicListResponse,
    DoctorListResponse,
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

    async def close(self):
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
            return json_data  # type: ignore[return-value]

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

        async with limiter or self.limiter:
            client = await self._get_client()
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
                elif res.status_code in [403, 429]:
                    return (
                        None,
                        _("api-blocked"),
                    )
                return None, _("api-temp-unavailable").format(status=res.status_code)
            except httpx.TimeoutException as e:
                logger.error(f"Таймаут API (fetch_patient_id): {e!r}")
                return None, _("api-timeout")
            except httpx.NetworkError as e:
                logger.error(f"Сетевая ошибка API (fetch_patient_id): {e!r}")
                return None, _("api-network-error")
            except (json.JSONDecodeError, ValidationError) as e:
                logger.error(f"Ошибка парсинга API (fetch_patient_id): {e!r}")
                return None, _("api-parse-error")
            except Exception as e:
                exc_repr = repr(e) if not str(e) else str(e)
                logger.error(f"Неожиданная ошибка API (fetch_patient_id): {exc_repr}")
                return None, _("api-timeout")

    async def fetch_speciality_list(
        self,
        patient_id: str,
        clinic_id: str,
        limiter: aiolimiter.AsyncLimiter | None = None,
    ) -> list[dict]:
        payload = {
            "clinic_form-clinic_id": clinic_id,
            "clinic_form-history_id": "",
            "clinic_form-patient_id": patient_id,
        }
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
                    elif res.status_code >= 500:
                        await asyncio.sleep(2)
                        continue
                    return []
                except httpx.TimeoutException as e:
                    logger.error(
                        f"Таймаут API (fetch_speciality_list), попытка {i + 1}: {e!r}"
                    )
                    if i < 2:
                        await asyncio.sleep(2)
                except httpx.NetworkError as e:
                    logger.error(
                        f"Сетевая ошибка API (fetch_speciality_list), "
                        f"попытка {i + 1}: {e!r}"
                    )
                    if i < 2:
                        await asyncio.sleep(2)
                except (json.JSONDecodeError, ValidationError) as e:
                    logger.error(
                        f"Ошибка парсинга API (fetch_speciality_list), "
                        f"попытка {i + 1}: {e!r}"
                    )
                    if i < 2:
                        await asyncio.sleep(2)
                except Exception as e:
                    exc_repr = repr(e) if not str(e) else str(e)
                    logger.error(
                        "Неожиданная ошибка API (fetch_speciality_list), "
                        f"попытка {i + 1}: {exc_repr}"
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
        payload = {
            "doctor_form-doctor_id": doc_id,
            "doctor_form-clinic_id": clinic_id,
            "doctor_form-patient_id": patient_id,
        }
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
                            f"Заблокировано API (check_slots): {res.status_code}"
                        )
                        return None
                    elif res.status_code >= 500:
                        await asyncio.sleep(2)
                        continue
                except httpx.TimeoutException as e:
                    logger.error(f"Таймаут API (check_slots), попытка {i + 1}: {e!r}")
                    await asyncio.sleep(2)
                except httpx.NetworkError as e:
                    logger.error(
                        f"Сетевая ошибка API (check_slots), попытка {i + 1}: {e!r}"
                    )
                    await asyncio.sleep(2)
                except (json.JSONDecodeError, ValidationError) as e:
                    logger.error(
                        f"Ошибка парсинга API (check_slots), попытка {i + 1}: {e!r}"
                    )
                    await asyncio.sleep(2)
                except Exception as e:
                    exc_repr = repr(e) if not str(e) else str(e)
                    logger.error(
                        f"Неожиданная ошибка API (check_slots), "
                        f"попытка {i + 1}: {exc_repr}"
                    )
                    await asyncio.sleep(2)
        return None

    async def fetch_all_doctors(
        self,
        specialty_id: str,
        patient_id: str,
        clinic_id: str,
        limiter: aiolimiter.AsyncLimiter | None = None,
    ) -> list[dict]:
        payload = {
            "speciality_form-speciality_id": specialty_id,
            "speciality_form-clinic_id": clinic_id,
            "speciality_form-patient_id": patient_id,
            "speciality_form-history_id": "",
        }
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
                            return [
                                item.model_dump(by_alias=True)
                                for item in model.response
                            ]
                    elif res.status_code >= 500:
                        await asyncio.sleep(2)
                        continue
                except httpx.TimeoutException as e:
                    logger.error(
                        f"Таймаут API (fetch_all_doctors), попытка {i + 1}: {e!r}"
                    )
                    await asyncio.sleep(2)
                except httpx.NetworkError as e:
                    logger.error(
                        f"Сетевая ошибка API (fetch_all_doctors), "
                        f"попытка {i + 1}: {e!r}"
                    )
                    await asyncio.sleep(2)
                except (json.JSONDecodeError, ValidationError) as e:
                    logger.error(
                        f"Ошибка парсинга API (fetch_all_doctors), "
                        f"попытка {i + 1}: {e!r}"
                    )
                    await asyncio.sleep(2)
                except Exception as e:
                    exc_repr = repr(e) if not str(e) else str(e)
                    logger.error(
                        f"Неожиданная ошибка API (fetch_all_doctors), "
                        f"попытка {i + 1}: {exc_repr}"
                    )
                    await asyncio.sleep(2)
        return []

    async def fetch_clinic_list(
        self,
        district_id: str = settings.DISTRICT_ID,
        limiter: aiolimiter.AsyncLimiter | None = None,
    ) -> list[dict]:
        """Получает список клиник для указанного района через /clinic_list/."""
        payload = {
            "district_form-district_id": district_id,
        }
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
                    elif res.status_code >= 500:
                        await asyncio.sleep(2)
                        continue
                    logger.warning(
                        f"clinic_list вернул {res.status_code} для района {district_id}"
                    )
                    return []
                except httpx.TimeoutException as e:
                    logger.error(
                        f"Таймаут API (fetch_clinic_list), попытка {i + 1}: {e!r}"
                    )
                    if i < 2:
                        await asyncio.sleep(2)
                except httpx.NetworkError as e:
                    logger.error(
                        f"Сетевая ошибка API (fetch_clinic_list), "
                        f"попытка {i + 1}: {e!r}"
                    )
                    if i < 2:
                        await asyncio.sleep(2)
                except (json.JSONDecodeError, ValidationError) as e:
                    logger.error(
                        f"Ошибка парсинга API (fetch_clinic_list), "
                        f"попытка {i + 1}: {e!r}"
                    )
                    if i < 2:
                        await asyncio.sleep(2)
                except Exception as e:
                    exc_repr = repr(e) if not str(e) else str(e)
                    logger.error(
                        f"Неожиданная ошибка API (fetch_clinic_list), "
                        f"попытка {i + 1}: {exc_repr}"
                    )
                    if i < 2:
                        await asyncio.sleep(2)
            return []
