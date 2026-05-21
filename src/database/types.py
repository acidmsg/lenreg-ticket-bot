"""
Типизированные контейнеры (TypedDict) для типобезопасной работы с данными.

Заменяет неявные строковые литералы-ключи на проверяемые mypy аннотации.
Все ключи остаются строками на уровне рантайма — меняется только статическая типизация.
"""

from __future__ import annotations

from typing import NotRequired, TypedDict


class PatientInfo(TypedDict):
    """Информация о пациенте (ключ в ``user_data['patients']``)."""

    fio: str
    """ФИО пациента (например, 'Иванов Иван Иванович')."""

    bday: str
    """Дата рождения в формате 'ДД.ММ.ГГГГ'."""

    alias: NotRequired[str]
    """Псевдоним (отображаемое имя). Отсутствует в dict, если None."""

    confirmed_clinics: NotRequired[list[int]]
    """Список clinic_id подтверждённых клиник. Может отсутствовать при создании."""

    clinic_id: NotRequired[str]
    """ID клиники по умолчанию (используется как fallback в monitor.py)."""


class MonitoringEntry(TypedDict):
    """Запись об отслеживаемом враче (ключ в ``user_data['monitoring'][p_id]``)."""

    name: str
    """ФИО врача."""

    clinic_id: str
    """ID клиники (строка, т.к. хранится как TEXT в SQLite)."""

    specialty: str
    """Специальность врача."""


class LastMessageEntry(TypedDict):
    """Запись о последнем сообщении (ключ в user_data['last_messages'])."""

    msg_id: int
    """ID сообщения в Telegram."""

    ts: float
    """Unix-timestamp отправки."""


class UserData(TypedDict):
    """Корневая структура данных пользователя в кэше и БД."""

    patients: dict[str, PatientInfo]
    """Пациенты: ключ — p_id (строка), значение — ``PatientInfo``."""

    monitoring: dict[str, dict[str, MonitoringEntry]]
    """Мониторинг: внешний ключ — p_id, внутренний — d_id."""

    last_messages: dict[str, LastMessageEntry]
    """Последние сообщения: ключ — '{p_id}_{d_id}'."""


class UserDataUpdate(TypedDict, total=False):
    """Частичное обновление ``UserData`` (все поля опциональны).

    Используется в :meth:`~src.database.manager.DatabaseManager.update_user`
    для типобезопасной передачи частичного словаря-обновления.
    """

    patients: dict[str, PatientInfo]
    monitoring: dict[str, dict[str, MonitoringEntry]]
    last_messages: dict[str, LastMessageEntry]


class DoctorEntry(TypedDict):
    """Запись о враче из таблицы ``doctors`` (ключ — doctor_id)."""

    name: str
    """ФИО врача."""

    specialty: str
    """Специальность."""


class ClinicInfo(TypedDict):
    """Запись о клинике из таблицы ``clinics`` (включая discovery-поля)."""

    clinic_id: str
    """Уникальный ID клиники."""

    name: str
    """Название клиники."""

    type: str
    """Тип: 'adult' | 'child' | 'all'."""

    is_active: int
    """Флаг активности: 0 или 1 (SQLite boolean)."""

    city: str
    """Город/район (может быть пустой строкой)."""

    discovery_patient_adult: NotRequired[str]
    """ID взрослого пациента для discovery (per-клиника переопределение)."""

    discovery_patient_child: NotRequired[str]
    """ID детского пациента для discovery (per-клиника переопределение)."""


class MonitoringLogEntry(TypedDict):
    """Запись из таблицы ``monitoring_log``."""

    id: int
    uid: str
    p_id: str
    d_id: str
    doctor_name: str
    patient_name: str
    specialty: str
    clinic_name: str
    slot_date: str
    status: str  # 'появился' | 'исчез' | 'уменьшился'
    ts: float
