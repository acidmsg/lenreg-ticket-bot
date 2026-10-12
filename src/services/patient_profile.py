"""
Доменная логика правки карточки пациента (P3-EDIT).

Модуль не зависит от HTTP и БД: валидирует поля правки, определяет факт
изменения ФИО или даты рождения и собирает новую карточку. Повторная
верификация пациента через внешний API остаётся в web-слое — там же, где
доступ к клиенту API и обработка HTTP-ответов.
"""

import datetime
from dataclasses import dataclass
from typing import Any, cast

from src.database.types import PatientInfo

_BDAY_FORMAT = "%d.%m.%Y"
_BDAY_MIN = datetime.date(1900, 1, 1)
_FIO_ERROR = "ФИО должно состоять из трёх слов: Фамилия Имя Отчество"
_BDAY_INPUT_ERROR = (
    "Неверный формат даты рождения. Ожидается ДД.ММ.ГГГГ (например, 01.01.1990)"
)
_BDAY_STORED_ERROR = "Неверная дата рождения."


@dataclass(frozen=True, slots=True)
class PatientUpdatePlan:
    """Результат валидации правки: что менять и нужно ли верифицировать заново."""

    fio: str
    bday_display: str
    data_changed: bool
    target_bday: datetime.date | None


def validate_fio(fio: str) -> None:
    """Проверяет, что ФИО состоит из трёх слов.

    Raises:
        ValueError: Если слов не три.
    """
    if len([part for part in fio.split() if part]) != 3:
        raise ValueError(_FIO_ERROR)


def parse_birth_date_input(value: str) -> datetime.date:
    """Разбирает введённую пользователем дату ``ДД.ММ.ГГГГ`` в диапазоне 1900→сегодня.

    Raises:
        ValueError: Если формат или диапазон даты некорректны.
    """
    try:
        parsed = datetime.datetime.strptime(value.strip(), _BDAY_FORMAT).date()
        if not (_BDAY_MIN <= parsed <= datetime.date.today()):
            raise ValueError(_BDAY_INPUT_ERROR)
    except ValueError as exc:
        raise ValueError(_BDAY_INPUT_ERROR) from exc
    return parsed


def parse_stored_bday(value: str) -> datetime.date:
    """Разбирает дату рождения из карточки без проверки диапазона.

    Raises:
        ValueError: Если формат даты некорректен.
    """
    try:
        return datetime.datetime.strptime(value, _BDAY_FORMAT).date()
    except ValueError as exc:
        raise ValueError(_BDAY_STORED_ERROR) from exc


def build_update_plan(
    existing_fio: str,
    existing_bday: str,
    full_name: str | None,
    birth_date: str | None,
) -> PatientUpdatePlan:
    """Валидирует правку и определяет, изменились ли ФИО или дата рождения.

    ``existing_bday`` приходит уже нормализованной web-слоем (``ДД.ММ.ГГГГ``).

    Raises:
        ValueError: Если новые ФИО или дата рождения некорректны.
    """
    fio = existing_fio
    if full_name is not None:
        fio = full_name.strip()
        validate_fio(fio)

    bday_display = existing_bday
    if birth_date is not None:
        bday_display = parse_birth_date_input(birth_date).strftime(_BDAY_FORMAT)

    data_changed = fio != existing_fio or bday_display != existing_bday
    target_bday = parse_stored_bday(bday_display) if data_changed else None
    return PatientUpdatePlan(
        fio=fio,
        bday_display=bday_display,
        data_changed=data_changed,
        target_bday=target_bday,
    )


def build_card(
    existing: PatientInfo | dict[str, Any],
    plan: PatientUpdatePlan,
    alias: str | None,
) -> PatientInfo:
    """Собирает новую карточку пациента из существующей и плана правки.

    Псевдоним: ``None`` — не менять; пустая строка — удалить.
    """
    new_info: dict[str, Any] = dict(existing)
    new_info["fio"] = plan.fio
    new_info["bday"] = plan.bday_display
    if alias is not None:
        clean_alias = alias.strip()
        if clean_alias:
            new_info["alias"] = clean_alias
        else:
            new_info.pop("alias", None)
    new_info.setdefault("confirmed_clinics", [])
    return cast(PatientInfo, new_info)
