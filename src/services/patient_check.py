"""Единый сервис проверки пациента: числится ли он в клиниках.

Используется в двух местах (P3-VERIFY):
- перед записью (P3-PREBOOK) — чтобы вместо ошибки ``signup`` отдать
  понятное «пациент не найден в клинике»;
- при актуализации карточки (P3-ACTUAL) — при открытии, по кнопке
  «проверить» и перед записью.

Один код и один кэш вместо независимых проверок: результат проверки
складывается в Redis с TTL, поэтому серия обращений к одной паре
(пользователь, пациент, клиника) не выжигает лимиты внешнего API.
"""

from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime

from loguru import logger

from src.config import settings
from src.database.types import PatientInfo
from src.i18n import _
from src.utils.cache import get_check_cache, set_check_cache

# Статусы проверки
CHECK_STATUS_VALID = "valid"
CHECK_STATUS_INVALID = "invalid"
CHECK_STATUS_UNKNOWN = "unknown"

# TTL кэша: подтверждённый пациент проверяется реже, «не найден» — чаще,
# чтобы исправленная карточка (P3-EDIT) вернулась в строй быстро.
VALID_CACHE_TTL = 6 * 3600
INVALID_CACHE_TTL = 1800

_BDAY_FORMATS = ("%d.%m.%Y", "%Y-%m-%d")


def _parse_bday(value: str) -> date_cls | None:
    """Разбирает дату рождения в поддерживаемых форматах хранения."""
    value = (value or "").strip()
    for fmt in _BDAY_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _mask_id(value: object) -> str:
    """Маскирует идентификатор до последних 4 символов для логов.

    Единая конвенция проекта: в лог не попадают полные ID пользователя
    и пациента (см. ``update_patient`` в ``web/routers/user_api.py``).
    """
    text = str(value or "")
    return f"...{text[-4:]}" if len(text) > 4 else "..."


def cache_key(uid: str, p_id: str, clinic_id: str) -> str:
    """Ключ кэша проверки: пара (пользователь, пациент) + клиника."""
    return f"{uid}:{p_id}:{clinic_id or 'global'}"


def _cache_key(uid: str, p_id: str, clinic_id: str) -> str:
    """Алиас для обратной совместимости внутренних вызовов."""
    return cache_key(uid, p_id, clinic_id)


def clinic_ids_for(
    p_info: PatientInfo | dict, clinic_ids: list[str] | None = None
) -> list[str]:
    """Определяет список клиник для проверки, без дублей.

    Приоритет: явно переданные клиники → клиника по умолчанию пациента →
    подтверждённые клиники → глобальная клиника из настроек.
    Пустая строка означает глобальный поиск и допускается только в конце.
    """
    if clinic_ids:
        ordered = [str(c) for c in clinic_ids]
    else:
        ordered = []
        default_clinic = str(p_info.get("clinic_id") or "")
        if default_clinic:
            ordered.append(default_clinic)
        ordered.extend(str(c) for c in p_info.get("confirmed_clinics") or [])
        ordered.append(str(settings.DEFAULT_CLINIC_ID))

    unique: list[str] = []
    for clinic_id in ordered:
        if clinic_id not in unique:
            unique.append(clinic_id)
    # Глобальный поиск (пустая клиника) имеет смысл только как последняя попытка
    if "" in unique:
        unique.remove("")
        unique.append("")
    return unique


def _is_not_found(err: str | None) -> bool:
    """Отличает «пациент не найден» от сбоя API по тексту ошибки клиента."""
    return bool(err) and err == _("api-patient-not-found")


async def check_patient_status(
    uid: str,
    p_id: str,
    p_info: PatientInfo | dict,
    api,
    db,
    *,
    clinic_ids: list[str] | None = None,
) -> str:
    """Проверяет, числится ли пациент хотя бы в одной из клиник.

    Результат кэшируется на ``VALID_CACHE_TTL``/``INVALID_CACHE_TTL``.
    Сбой API не считается «невалидным» — возвращается ``unknown``.

    Args:
        uid: Telegram ID пользователя.
        p_id: Идентификатор пациента (ключ записи у пользователя).
        p_info: Данные пациента (``fio``, ``bday``, клиники).
        api: Клиент zdrav.lenreg.ru.
        db: Менеджер базы данных (зарезервирован под расширение проверок).
        clinic_ids: Клиники для проверки; None — вывести из карточки пациента.

    Returns:
        Один из ``CHECK_STATUS_VALID`` / ``CHECK_STATUS_INVALID`` /
        ``CHECK_STATUS_UNKNOWN``.
    """
    fio = str(p_info.get("fio") or "").strip()
    if len(fio.split()) != 3:
        logger.debug(
            "Проверка пациента {}: ФИО не из трёх слов, статус unknown",
            _mask_id(p_id),
        )
        return CHECK_STATUS_UNKNOWN

    bday = _parse_bday(str(p_info.get("bday") or ""))
    if bday is None:
        logger.debug(
            "Проверка пациента {}: не разобрана дата рождения, статус unknown",
            _mask_id(p_id),
        )
        return CHECK_STATUS_UNKNOWN

    saw_error = False

    for clinic_id in clinic_ids_for(p_info, clinic_ids):
        key = _cache_key(str(uid), str(p_id), clinic_id)
        cached = await get_check_cache(key)
        if cached == CHECK_STATUS_VALID:
            return CHECK_STATUS_VALID
        if cached == CHECK_STATUS_INVALID:
            continue

        try:
            found_id, err = await api.fetch_patient_id(fio, bday, clinic_id)
        except Exception:
            logger.exception(
                "Проверка пациента {} в clinic_id={} завершилась ошибкой API",
                _mask_id(p_id),
                clinic_id,
            )
            saw_error = True
            continue

        if found_id is not None:
            if str(found_id) != str(p_id):
                # Пациент найден под другим id: дубль в базе клиники.
                logger.warning(
                    "Проверка пациента {} в clinic_id={}: найден другой id={}",
                    _mask_id(p_id),
                    clinic_id,
                    _mask_id(found_id),
                )
            await set_check_cache(key, CHECK_STATUS_VALID, VALID_CACHE_TTL)
            return CHECK_STATUS_VALID

        if _is_not_found(err):
            await set_check_cache(key, CHECK_STATUS_INVALID, INVALID_CACHE_TTL)
            continue

        # Не «не найден», а сбой/лимит/таймаут — не кэшируем.
        saw_error = True
        logger.warning(
            "Проверка пациента {} в clinic_id={}: сбой API ({})",
            _mask_id(p_id),
            clinic_id,
            err,
        )

    return CHECK_STATUS_UNKNOWN if saw_error else CHECK_STATUS_INVALID
