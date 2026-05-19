"""
Pydantic-модели для ответов API zdrav.lenreg.ru.

Каждая модель валидирует форму ответа, заменяя сырые .get()-вызовы
на типизированный доступ с понятными сообщениями об ошибках.
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
    """Один элемент списка специальностей."""

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
