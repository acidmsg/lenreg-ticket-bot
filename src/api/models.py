"""
Pydantic-модели для запросов и ответов API zdrav.lenreg.ru.

Модели ответов валидируют форму ответа API.
Модели запросов (`*Request`) типизируют payload POST-запросов,
заменяя сырые dict-конструкторы.
"""

from dataclasses import dataclass, field
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, Field


def _coerce_str(v: Any) -> str:
    """Приводит значение к строке (API иногда возвращает числа или объекты).

    Обрабатывает три случая:
    1. None → ""
    2. dict с именем врача → извлекает строковое имя
    3. Всё остальное → str(v)
    """
    if v is None:
        return ""
    if isinstance(v, dict):
        # API zdrav.lenreg может вернуть Name как объект {"Id":"...","Name":"..."}
        # или как объект {"first_name":"...","last_name":"..."}
        name_value = v.get("Name") or v.get("name") or ""
        if name_value:
            return str(name_value)
        parts = [
            v.get(k, "") for k in ("last_name", "first_name", "middle_name") if v.get(k)
        ]
        if parts:
            return " ".join(parts)
        # В крайнем случае — сериализуем весь объект как JSON-строку
        return str(v)
    return str(v)


def _coerce_bool(v: Any) -> bool:
    """Приводит значение к булевому типу (API иногда возвращает строки или числа).

    Обрабатывает:
    1. Уже bool → возвращается как есть
    2. int → 0 = False, всё остальное = True
    3. str → "true"/"1"/"yes" → True, "false"/"0"/"no"/"" → False
    4. None → False
    """
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes")
    if v is None:
        return False
    return bool(v)


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


class SignupRequest(BaseModel):
    """Payload для POST /api/signup/ — бронирование талона."""

    clinic_id: str = Field(default="", alias="appointment_form-clinic_id")
    patient_id: str = Field(default="", alias="appointment_form-patient_id")
    appointment_id: str = Field(default="", alias="appointment_form-appointment_id")
    history_id: str = Field(default="", alias="appointment_form-history_id")
    referral_id: str = Field(default="", alias="appointment_form-referral_id")
    csrfmiddlewaretoken: str = Field(default="")

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
    error: dict[str, Any] = Field(default_factory=dict)


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
    is_doc: Annotated[bool, BeforeValidator(_coerce_bool)] = Field(
        default=False, alias="IsDoc"
    )
    is_tech: Annotated[bool, BeforeValidator(_coerce_bool)] = Field(
        default=False, alias="IsTech"
    )


class SpecialityListResponse(BaseModel):
    """Ответ /api/speciality_list/."""

    response: list[SpecialityItem] = Field(default_factory=list)
    success: bool = False
    error: dict[str, Any] = Field(default_factory=dict)


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
    error: dict[str, Any] = Field(default_factory=dict)


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
    error: dict[str, Any] = Field(default_factory=dict)


# ── signup ─────────────────────────────────────────────────────


class SignupError(BaseModel):
    """Ошибка бронирования (ответ API /api/signup/ при неудаче).

    Поля, возвращаемые API zdrav.lenreg.ru при ошибке:
    - ``IdError``: код ошибки (39 = слот занят).
    - ``ErrorDescription``: человекочитаемое описание.

    Поле ``detail`` используется для внутренних ошибок (сеть, таймаут, HTTP).
    """

    IdError: int = 0
    ErrorDescription: str = ""
    detail: str = ""

    model_config = {"extra": "allow"}


class SignupResponse(BaseModel):
    """Ответ POST /api/signup/ — результат бронирования талона."""

    success: bool = False
    response: dict[str, Any] = Field(default_factory=dict)
    error: SignupError = Field(default_factory=SignupError)


# ── составной результат check_slots ────────────────────────────


@dataclass
class CheckSlotsResult:
    """Результат проверки слотов: форматированные строки + сырые данные.

    Атрибуты:
        formatted: Список строк вида "ДД.ММ.ГГГГ в ЧЧ:ММ" для отображения.
        slots: Сырые слоты AppointmentSlot с id для бронирования.
        has_slots: True если есть хотя бы один слот.
    """

    formatted: list[str] = field(default_factory=list)
    slots: list[AppointmentSlot] = field(default_factory=list)

    @property
    def has_slots(self) -> bool:
        """True если есть хотя бы один доступный слот."""
        return len(self.formatted) > 0 or len(self.slots) > 0


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
    error: dict[str, Any] = Field(default_factory=dict)
