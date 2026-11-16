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

    date: str
    """Дата приёма в формате 'ДД.ММ.ГГГГ' (может быть пустой)."""

    date_from: NotRequired[str]
    """Начало интервала дат 'ГГГГ-ММ-ДД' (пусто — без ограничения)."""

    date_to: NotRequired[str]
    """Конец интервала дат 'ГГГГ-ММ-ДД' (пусто — без ограничения)."""

    time_from: NotRequired[str]
    """Начало интервала времени 'ЧЧ:ММ' (пусто — без ограничения)."""

    time_to: NotRequired[str]
    """Конец интервала времени 'ЧЧ:ММ' (пусто — без ограничения)."""

    specific_dates: NotRequired[str]
    """JSON-массив строк 'ГГГГ-ММ-ДД' с конкретными датами (по умолчанию '[]')."""


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


class BookingEntry(TypedDict):
    """Запись из таблицы ``bookings``."""

    booking_id: str
    """Составной ключ: ``{patient_id}_{doctor_id}_{appointment_id}``."""

    uid: str
    """ID пользователя Telegram."""

    p_id: str
    """ID пациента."""

    d_id: str
    """ID врача."""

    doctor_name: str
    """ФИО врача на момент записи."""

    patient_name: str
    """ФИО пациента на момент записи."""

    specialty: str
    """Специальность врача."""

    clinic_id: str
    """ID клиники."""

    clinic_name: str
    """Название клиники на момент записи."""

    slot_date: str
    """Дата приёма в формате 'ДД.ММ.ГГГГ'."""

    slot_time: str
    """Время приёма в формате 'ЧЧ:ММ'."""

    appointment_id: str
    """ID слота из API."""

    created_at: float
    """Unix-timestamp создания записи."""

    is_archived: int
    """0 = активная, 1 = архивная."""

    status: str
    """Состояние записи: pending | confirmed | failed."""


class AuditLogEntry(TypedDict):
    """Запись журнала действий администратора (таблица audit_logs)."""

    id: int
    """Идентификатор записи."""

    ts: float
    """Время события (Unix-время)."""

    actor: str
    """Кто выполнил действие (логин дашборда, system, bot)."""

    action: str
    """Машиночитаемый код действия."""

    target: str
    """Объект действия (файл, uid, ключ настройки)."""

    payload_json: str
    """Дополнительные данные в виде JSON-строки."""


class ScreenRecord(TypedDict):
    """Запись экрана чата (таблица ``user_chat_screen``).

    Один экран на пользователя и вид экрана: ``PRIMARY KEY (uid, kind)``.
    """

    uid: int
    """ID пользователя Telegram (целое, как и в остальных таблицах пользователей)."""

    kind: str
    """Вид экрана; для мониторинга — ``'monitor'``."""

    chat_id: int
    """ID чата, в котором живёт сообщение-экран."""

    msg_id: int
    """ID сообщения-экрана в Telegram.

    Запись создаётся только после успешной отправки, поэтому ``msg_id``
    всегда известен.
    """

    content_type: str
    """Тип вложения экрана (``'text'``); поле оставлено под будущий ``edit_media``."""

    render_hash: str
    """SHA-256 канонического состояния экрана — дедупликация обновлений."""

    last_seen_ts: int
    """Unix-время (секунды) последнего события, учтённого в экране."""

    updated_at: int
    """Unix-время (секунды) последнего обновления записи — база TTL-выборки."""

    last_check_at: int
    """Unix-время (секунды) последней итерации, в которой проверялись пары."""

    check_count: int
    """Число проверок пар с момента создания записи экрана."""

    error_count: int
    """Число неуспешных проверок пар."""

    last_event_at: int
    """Unix-время (секунды) последнего события, попавшего в экран."""

    new_events_count: int
    """Сколько новых событий показано в экране с прошлого визита пользователя."""
