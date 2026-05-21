"""
Pydantic-модели для запросов и ответов API zdrav.lenreg.ru.

Модели ответов валидируют форму ответа API.
Модели запросов (`*Request`) типизируют payload POST-запросов,
заменяя сырые dict-конструкторы.
"""

from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, Field


def _coerce_str(v: Any) -> str:
    """Приводит значение к строке (API иногда возвращает числа вместо строк)."""
    return str(v) if v is not None else ""


# ── Общие (shared) ────────────────────────────────────────────


class DateInfo(BaseModel):
    """Вложенный объект даты (LastDate, NearestDate, date_start, date_end)."""

    model_config = {"populate_by_name": True}

    year: str = ""
    day_verbose: str = Field(default="", alias="day_verbose")
    month: str = ""
    month_verbose: str = Field(default="", alias="month_verbose")
    time: str = ""
    iso: str = ""
    day: str = ""


class ApiError(BaseModel):
    """Объект ошибки (пока не документирован, оставляем гибким)."""

    model_config = {"extra": "allow"}


# ── Request models ────────────────────────────────────────────


class CheckPatientRequest(BaseModel):
    """Payload для /api/check_patient/."""

    first_name: str = Field(default="", alias="patient_form-first_name")
    last_name: str = Field(default="", alias="patient_form-last_name")
    middle_name: str = Field(default="", alias="patient_form-middle_name")
    insurance_series: str = Field(default="", alias="patient_form-insurance_series")
    insurance_number: str = Field(default="", alias="patient_form-insurance_number")
    birthday: str = Field(default="", alias="patient_form-birthday")
    clinic_id: str = Field(default="", alias="patient_form-clinic_id")
    csrfmiddlewaretoken: str = Field(default="")

    model_config = {"populate_by_name": True}


class SpecialityListRequest(BaseModel):
    """Payload для /api/speciality_list/."""

    clinic_id: str = Field(default="", alias="clinic_form-clinic_id")
    history_id: str = Field(default="", alias="clinic_form-history_id")
    patient_id: str = Field(default="", alias="clinic_form-patient_id")

    model_config = {"populate_by_name": True}


class DoctorListRequest(BaseModel):
    """Payload для /api/doctor_list/."""

    speciality_id: str = Field(default="", alias="speciality_form-speciality_id")
    clinic_id: str = Field(default="", alias="speciality_form-clinic_id")
    patient_id: str = Field(default="", alias="speciality_form-patient_id")
    history_id: str = Field(default="", alias="speciality_form-history_id")

    model_config = {"populate_by_name": True}


class AppointmentListRequest(BaseModel):
    """Payload для /api/appointment_list/."""

    doctor_id: str = Field(default="", alias="doctor_form-doctor_id")
    clinic_id: str = Field(default="", alias="doctor_form-clinic_id")
    patient_id: str = Field(default="", alias="doctor_form-patient_id")
    history_id: str = Field(default="", alias="doctor_form-history_id")
    appointment_type: str = Field(default="", alias="doctor_form-appointment_type")

    model_config = {"populate_by_name": True}


class ClinicListRequest(BaseModel):
    """Payload для /api/clinic_list/."""

    district_id: str = Field(default="", alias="district_form-district_id")

    model_config = {"populate_by_name": True}


# ── check_patient ─────────────────────────────────────────────


class CheckPatientData(BaseModel):
    """response.check_patient."""

    history_id: str | None = None
    patient_id: str | None = None


class CheckPatientResponse(BaseModel):
    """Ответ /api/check_patient/."""

    response: CheckPatientData = Field(default_factory=CheckPatientData)
    success: bool = False
    error: ApiError = Field(default_factory=ApiError)


# ── speciality_list ───────────────────────────────────────────


class SpecialityItem(BaseModel):
    """
    Один элемент списка специальностей.

    Поля NameSpesiality, FerIdSpesiality, IdSpesiality — опечатка
    внешнего API (zdrav.lenreg.ru), не контролируется нашей стороной.
    """

    model_config = {"populate_by_name": True}

    specialty_name: Annotated[str, BeforeValidator(_coerce_str)] = Field(
        default="", alias="NameSpesiality"
    )
    fer_id_specialty: Annotated[str, BeforeValidator(_coerce_str)] = Field(
        default="", alias="FerIdSpesiality"
    )
    specialty_id: Annotated[str, BeforeValidator(_coerce_str)] = Field(
        default="", alias="IdSpesiality"
    )
    CountFreeTicket: int = 0
    LastDate: DateInfo | None = None
    NearestDate: DateInfo | None = None
    CountFreeParticipantIE: int = 0


class SpecialityListResponse(BaseModel):
    """Ответ /api/speciality_list/."""

    response: list[SpecialityItem] = Field(default_factory=list)
    success: bool = False
    error: ApiError = Field(default_factory=ApiError)


# ── doctor_list ───────────────────────────────────────────────


class DoctorItem(BaseModel):
    """Один врач из списка."""

    AriaNumber: str | None = None
    Name: Annotated[str, BeforeValidator(_coerce_str)] = ""
    IdDoc: Annotated[str, BeforeValidator(_coerce_str)] = ""
    CountFreeTicket: int = 0
    LastDate: DateInfo | None = None
    NearestDate: DateInfo | None = None
    CountFreeParticipantIE: int = 0
    # Добавляется кодом, а не API:
    SpesialityName: str = ""


class DoctorListResponse(BaseModel):
    """Ответ /api/doctor_list/."""

    response: list[DoctorItem] = Field(default_factory=list)
    success: bool = False
    error: ApiError = Field(default_factory=ApiError)


# ── appointment_list ──────────────────────────────────────────


class AppointmentSlot(BaseModel):
    """Один слот в списке записи."""

    date_end: DateInfo = Field(default_factory=lambda: DateInfo())
    date_start: DateInfo = Field(default_factory=lambda: DateInfo())
    id: str = ""


class AppointmentListResponse(BaseModel):
    """Ответ /api/appointment_list/.

    response — dict[дата, list[слотов]], например:
    {"2026-05-19": [{...slot...}, ...]}
    """

    response: dict[str, list[AppointmentSlot]] = Field(default_factory=dict)
    success: bool | None = None  # не всегда приходит в этом эндпоинте
    error: ApiError = Field(default_factory=ApiError)


# ── clinic_list ───────────────────────────────────────────────


class ClinicItem(BaseModel):
    """Одна клиника из списка."""

    IdLPU: Annotated[str, BeforeValidator(_coerce_str)] = ""
    LpuName: str = ""
    LPUShortName: str = ""


class ClinicListResponse(BaseModel):
    """Ответ /api/clinic_list/."""

    response: list[ClinicItem] = Field(default_factory=list)
    success: bool = False
    error: ApiError = Field(default_factory=ApiError)
