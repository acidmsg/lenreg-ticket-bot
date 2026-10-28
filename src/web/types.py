"""
Доменные типы словарей на границе слоя ``web``.

Модуль фиксирует форму JSON-структур, которые роутеры дашборда отдают в шаблоны
Jinja2, в JSON-ответы и в SSE-поток. До введения типов такие структуры
описывались как ``dict[str, Any]``: имена ключей нигде не проверялись, а
опечатка проявлялась только в рантайме (пример — чтение ``patients_count``
вместо ``patient_count`` в CSV-выгрузке пользователей).

Все ключи остаются строками на уровне рантайма — меняется только статическая
типизация. Подход наследует TD-UTL-004
([`specs/design/td-utl-004-typeddict-design.md`]): ``TypedDict`` из stdlib,
``NotRequired`` для необязательных полей, поля — с докстрингами.
"""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict


class DashboardUserRow(TypedDict):
    """Строка списка пользователей дашборда (``get_users_data()``)."""

    uid: str
    """Telegram ID пользователя."""

    patient_count: int
    """Количество пациентов в карточке пользователя."""

    monitoring_count: int
    """Суммарное количество цепочек мониторинга по всем пациентам."""

    last_activity_ts: float
    """Unix-timestamp последнего сообщения бота (``0.0`` — активности не было)."""


class DashboardClinicRow(TypedDict):
    """Строка списка клиник дашборда (``get_clinics_data()``)."""

    clinic_id: str
    """ID клиники."""

    name: str
    """Название клиники."""

    type: str
    """Тип клиники: ``adult`` | ``child`` | ``all``."""

    city: str
    """Город/район (может быть пустой строкой)."""

    is_active: int
    """Флаг активности: ``0`` или ``1`` (SQLite boolean)."""

    doctor_count: int
    """Количество врачей в реестре клиники."""


class PatientViewRow(TypedDict):
    """Пациент в JSON-ответах Mini App (``_serialize_patients()``).

    Производная от ``PatientInfo``: ключи переименованы и нормализованы для
    клиента (``p_id`` → ``patient_id``, дата рождения — всегда ``ДД.ММ.ГГГГ``).
    """

    patient_id: str
    """ID пациента (ключ словаря ``user_data['patients']``)."""

    fio: str
    """ФИО пациента."""

    bday: str
    """Дата рождения в формате ``ДД.ММ.ГГГГ``."""

    alias: NotRequired[str]
    """Псевдоним (отображаемое имя); отсутствует, если не задан."""

    confirmed_clinics: NotRequired[list[int]]
    """ID клиник, где пациент подтверждён; отсутствует, если список не задан."""

    needs_check: NotRequired[bool]
    """Флаг «пациента стоит перепроверить» (P3-ACTUAL).

    Заполняется только в списке ``GET /api/user/patients`` по кэшу проверок;
    в профиле и в ответах правки поле отсутствует.
    """


class MonitoringFilterView(TypedDict):
    """Фильтр отслеживания врача в виде для JSON-ответа (Mini App, §9.8)."""

    date_from: str
    """Начало интервала дат ``ГГГГ-ММ-ДД`` (пусто — без ограничения)."""

    date_to: str
    """Конец интервала дат ``ГГГГ-ММ-ДД`` (пусто — без ограничения)."""

    time_from: str
    """Начало интервала времени ``ЧЧ:ММ`` (пусто — без ограничения)."""

    time_to: str
    """Конец интервала времени ``ЧЧ:ММ`` (пусто — без ограничения)."""

    specific_dates: list[str]
    """Конкретные даты ``ГГГГ-ММ-ДД`` (пустой список — отбор отключён)."""


class LiveDisplayValues(TypedDict):
    """Готовые к вставке строки блока ``display`` SSE-снапшота.

    Форматирование выполняется на сервере: клиент вставляет значения как есть,
    поэтому все поля — строки.
    """

    uptime: str
    """Время работы процесса."""

    total_users: str
    """Количество пользователей."""

    total_patients: str
    """Количество пациентов."""

    total_monitored_doctors: str
    """Количество отслеживаемых врачей."""

    active_monitorings: str
    """Количество активных цепочек мониторинга."""

    doctors_discovered: str
    """Счётчик обнаруженных врачей (Prometheus)."""

    doctors_last_scan: str
    """Время последнего скана врачей."""

    api_health: str
    """Строка здоровья внешнего API."""

    api_last_check: str
    """Возраст последней проверки API."""

    api_checks: str
    """Всего проверок API."""

    api_errors: str
    """Всего ошибок API."""

    api_availability: str
    """Доступность API в процентах."""

    notifications: str
    """Количество отправленных уведомлений мониторинга."""

    planner: str
    """Короткая строка состояния фоновых задач."""

    tg_mode: str
    """Режим получения обновлений Telegram (метка)."""

    tg_api_health: str
    """Строка здоровья Telegram Bot API."""

    tg_api_last_check: str
    """Возраст последней проверки Telegram Bot API."""

    tg_api_latency: str
    """Задержка Telegram Bot API."""

    tg_queue: str
    """Глубина очереди отправки."""

    tg_sends: str
    """Счётчик отправок и ошибок отправки."""

    tg_retry_after: str
    """Срабатывания лимита 429."""


class LiveFlags(TypedDict):
    """Флаги для бейджей живого обновления (блок ``flags``)."""

    api_ok: bool
    """Внешний API доступен."""

    tg_api_ok: bool
    """Telegram Bot API доступен."""


class DashboardLivePayload(TypedDict):
    """Кадр SSE-потока ``GET /api/dashboard/stream`` (§DASH-1)."""

    ts: int
    """Unix-timestamp сборки снапшота."""

    interval: int
    """Интервал между кадрами в секундах."""

    display: LiveDisplayValues
    """Готовые строки для вставки в разметку."""

    flags: LiveFlags
    """Флаги состояния внешних сервисов."""


class DashboardStreamError(TypedDict):
    """Кадр SSE-потока при сбое сборки снапшота.

    Поток не рвётся: клиент получает признак ошибки и продолжает жить.
    """

    ts: int
    """Unix-timestamp кадра."""

    error: str
    """Код ошибки (``snapshot_failed``)."""


class TrackedDoctorView(TypedDict):
    """Отслеживаемый врач в ответе ``GET /api/user/doctors`` (§9.8).

    Форма зафиксирована схемой ``TrackedDoctorsResponse.items`` в
    ``specs/openapi.yaml``: набор ключей и типы значений обязаны совпадать.
    """

    monitoring_id: str
    """ID мониторинга в формате ``{patient_id}_{doctor_id}``."""

    patient_id: str
    """ID пациента."""

    patient_name: str
    """ФИО пациента (``p_id``, если записи пациента нет)."""

    doctor_id: str
    """ID врача."""

    doctor_name: str
    """ФИО врача."""

    specialty: str
    """Название специальности."""

    clinic_id: str
    """ID поликлиники."""

    clinic_name: str
    """Название поликлиники (пустая строка, если неизвестно)."""

    status: str
    """Статус из Redis-кэша: ``slots_available`` | ``no_slots`` | ``checking``."""

    free_tickets: int
    """Количество свободных талонов (общее)."""

    matching_free_tickets: int
    """Талонов, подходящих под фильтр отслеживания (§7.3)."""

    last_check: str | None
    """Время последней проверки (ISO 8601) либо ``None``."""

    filter: MonitoringFilterView
    """Сохранённый фильтр отслеживания для предзаполнения формы."""


class TrackedDoctorsResponse(TypedDict):
    """Ответ ``GET /api/user/doctors`` (``TrackedDoctorsResponse`` спеки)."""

    doctors: list[TrackedDoctorView]
    """Отслеживаемые врачи пользователя."""


class ForceCheckSlotView(TypedDict):
    """Слот в ответе ``POST /api/user/doctors/check``."""

    date: str
    """Дата слота в формате ``ДД.ММ.ГГГГ``."""

    time: str
    """Время слота в формате ``ЧЧ:ММ``."""

    clinic_id: str
    """ID поликлиники."""


class ForceCheckResponse(TypedDict):
    """Ответ ``POST /api/user/doctors/check`` (``ForceCheckResponse`` спеки)."""

    status: str
    """Статус операции (``ok``)."""

    monitoring_id: str
    """ID мониторинга в формате ``{patient_id}_{doctor_id}``."""

    doctor_name: str
    """ФИО врача."""

    specialty: str
    """Название специальности."""

    clinic_name: str
    """Название поликлиники."""

    slot_status: str
    """Наличие слотов: ``slots_available`` | ``no_slots``."""

    total: int
    """Общее количество слотов."""

    slots: list[ForceCheckSlotView]
    """Список доступных слотов."""

    checked_at: str
    """Время проверки в ISO 8601."""


class AvailableDoctorsResponse(TypedDict):
    """Ответ ``GET /api/user/doctors/available`` (``AvailableDoctorsResponse`` спеки).

    Список ``doctors`` намеренно остаётся нетипизированным: строки производит
    :func:`src.services.doctor_catalog.build_doctors`, а слой ``services`` не
    может импортировать ``web`` (контракт import-linter). Тип элемента — следующий
    срез TD-039; до него форма строки закреплена тестом
    ``tests/web/test_web_types.py`` по схеме ``AvailableDoctor``.
    """

    clinic_id: str
    """ID клиники."""

    specialty_id: str | None
    """ID специальности (``None``, если параметр не передан)."""

    slots_fresh: bool
    """Кэш талонов клиники свеж (скелетон списка при ``False``)."""

    doctors: list[dict[str, Any]]
    """Врачи клиники с талонами из кэша (схема ``AvailableDoctor``)."""


class UserSlotsResponse(TypedDict):
    """Ответ ``GET /api/user/slots`` (``UserSlotsResponse`` спеки).

    ``slots`` — ``list[dict[str, str]]``: строку слота целиком строит
    :func:`src.services.slot_query.format_slots`, набор ключей зафиксирован
    схемой ``UserSlot`` (``date``, ``time``, ``appointment_id``, ``slot_id``,
    ``clinic_id``), все значения — строки.
    """

    monitoring_id: str
    """ID мониторинга в формате ``{patient_id}_{doctor_id}``."""

    doctor_name: str
    """ФИО врача."""

    specialty: str
    """Название специальности."""

    clinic_name: str
    """Название поликлиники."""

    slots: list[dict[str, str]]
    """Свободные слоты врача (схема ``UserSlot``)."""

    total: int
    """Общее количество слотов."""


class PreheatResponse(TypedDict):
    """Ответ ``POST /api/user/clinics/{clinic_id}/slots/preheat``."""

    status: str
    """Статус операции (``ok``)."""

    clinic_id: str
    """ID клиники."""
