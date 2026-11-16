import asyncio
import json
import random
from collections.abc import Mapping
from datetime import date, time
from typing import NamedTuple

from loguru import logger

from src.api.models import CheckSlotsResult
from src.api.zdrav_client import ZdravClient
from src.config import settings
from src.database.manager import DatabaseManager
from src.database.types import MonitoringEntry, PatientInfo, UserData
from src.i18n import _, resolve_language, use_language
from src.services.notification_port import NotificationPort
from src.services.screen_collect import PairState, build_screen_items, parse_id
from src.services.screen_port import ScreenServicePort
from src.utils.cache import get_cache_key, swap_cache_key
from src.utils.helpers import (
    format_notification_text,
    format_slots,
    shorten_fio,
    shorten_specialty,
)


def _parse_specific_dates(monitoring_entry: MonitoringEntry) -> list[str]:
    """Разбирает поле ``specific_dates`` (JSON-строка из БД) в список дат.

    Дополнительно поддерживается уже распарсенный список — на случай вызовов
    вне слоя БД.
    """
    raw = monitoring_entry.get("specific_dates", "") or ""
    if isinstance(raw, list):
        return [str(item) for item in raw]
    try:
        parsed = json.loads(raw) if raw else []
    except (ValueError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def has_slot_filters(monitoring_entry: MonitoringEntry) -> bool:
    """Проверяет, задан ли хотя бы один фильтр слотов в записи мониторинга."""
    return bool(
        monitoring_entry.get("date_from")
        or monitoring_entry.get("date_to")
        or monitoring_entry.get("time_from")
        or monitoring_entry.get("time_to")
        or _parse_specific_dates(monitoring_entry)
    )


class _ParsedSlot(NamedTuple):
    """Разобранный слот: исходная строка, строковая дата, дата и время."""

    raw: str
    date_str: str
    slot_date: date
    slot_time: time | None


class _SlotFilters(NamedTuple):
    """Нормализованные фильтры слотов из записи мониторинга."""

    date_from: str
    date_to: str
    time_from: str
    time_to: str
    specific_dates: list[str]


def _parse_date_bound(raw: str) -> date | None:
    """Разбирает границу диапазона дат.

    Returns:
        Дата или None, если граница не задана либо записана некорректно.
    """
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _parse_time_bound(raw: str) -> time | None:
    """Разбирает границу диапазона времени.

    Returns:
        Время или None, если граница не задана либо записана некорректно.
    """
    if not raw:
        return None
    try:
        return time.fromisoformat(raw)
    except ValueError:
        return None


def _parse_slot_value(slot_str: str) -> _ParsedSlot | None:
    """Разбирает слот формата ``"YYYY-MM-DD в HH:MM"``.

    Returns:
        Разобранный слот или None, если строка не поддаётся разбору.
    """
    parts = slot_str.split(" в ")
    date_str = parts[0].strip()
    time_str = parts[1].strip() if len(parts) > 1 else ""

    try:
        slot_date = date.fromisoformat(date_str)
    except ValueError:
        # Невозможно распарсить дату — пропускаем слот (не должны доходить сюда)
        return None

    slot_time: time | None = None
    if time_str:
        try:
            slot_time = time.fromisoformat(time_str)
        except ValueError:
            return None

    return _ParsedSlot(slot_str, date_str, slot_date, slot_time)


def _build_slot_filters(monitoring_entry: MonitoringEntry) -> _SlotFilters:
    """Извлекает и нормализует фильтры слотов из записи мониторинга."""
    return _SlotFilters(
        date_from=str(monitoring_entry.get("date_from", "") or ""),
        date_to=str(monitoring_entry.get("date_to", "") or ""),
        time_from=str(monitoring_entry.get("time_from", "") or ""),
        time_to=str(monitoring_entry.get("time_to", "") or ""),
        specific_dates=_parse_specific_dates(monitoring_entry),
    )


def _is_inside_date_range(slot_date: date, filters: _SlotFilters) -> bool:
    """Проверяет попадание даты слота в интервал ``[date_from, date_to]``."""
    lower = _parse_date_bound(filters.date_from)
    if lower is not None and slot_date < lower:
        return False
    upper = _parse_date_bound(filters.date_to)
    return not (upper is not None and slot_date > upper)


def _is_inside_time_range(slot_time: time | None, filters: _SlotFilters) -> bool:
    """Проверяет попадание времени слота в интервал ``[time_from, time_to]``."""
    if slot_time is None:
        return True
    lower = _parse_time_bound(filters.time_from)
    if lower is not None and slot_time < lower:
        return False
    upper = _parse_time_bound(filters.time_to)
    return not (upper is not None and slot_time > upper)


def _matches_specific_dates(slot_date_str: str, filters: _SlotFilters) -> bool:
    """Проверяет, входит ли дата слота в список конкретных дат (если он задан)."""
    if not filters.specific_dates:
        return True
    return slot_date_str in filters.specific_dates


def _slot_matches_filters(slot: _ParsedSlot, filters: _SlotFilters) -> bool:
    """Проверяет слот по всем заданным фильтрам в исходном порядке."""
    return (
        _is_inside_date_range(slot.slot_date, filters)
        and _is_inside_time_range(slot.slot_time, filters)
        and _matches_specific_dates(slot.date_str, filters)
    )


def filter_slots_by_user_prefs(
    slots: list[str],
    monitoring_entry: MonitoringEntry,
) -> list[str]:
    """Фильтрует слоты согласно настройкам пользователя (T-18).

    Если фильтры не заданы (поля отсутствуют или пустые) — возвращает все слоты.

    Args:
        slots: Список слотов в формате ``"YYYY-MM-DD в HH:MM"``.
        monitoring_entry: Запись мониторинга с опциональными полями фильтра.

    Returns:
        Отфильтрованный список слотов.
    """
    if not slots:
        return slots

    # Поля фильтра объявлены как NotRequired: отсутствие = «без ограничения»
    if not has_slot_filters(monitoring_entry):
        return slots

    filters = _build_slot_filters(monitoring_entry)
    filtered: list[str] = []
    for slot_str in slots:
        parsed_slot = _parse_slot_value(slot_str)
        if parsed_slot is None:
            continue
        if _slot_matches_filters(parsed_slot, filters):
            filtered.append(slot_str)
    return filtered


def _handle_disappeared(
    old_slots_data: list[str] | str | None,
) -> tuple[str, None, str] | None:
    """Обрабатывает случай, когда слоты исчезли.

    Returns:
        (header, None, "empty") если слоты исчезли и об этом нужно уведомить,
        None если уведомление не требуется (уже было пусто или первое обнаружение).
    """
    if old_slots_data == "NONE" or old_slots_data is None:
        # Уже было пусто — не дублируем / Первое обнаружение
        return None
    return _("slots-disappeared-header"), None, "empty"


def _handle_appeared(
    slots: list[str],
    old_slots_data: list[str] | str | None,
) -> tuple[str, list[str], str] | None:
    """Обрабатывает случай, когда слоты появились (впервые или новые).

    Returns:
        (header, display_slots, notify_type) для "available" или "new",
        None если новых слотов нет.
    """
    if old_slots_data == "NONE" or old_slots_data is None:
        return _("slots-appeared-header"), slots, "available"

    # Слоты были и раньше — проверяем, появились ли новые
    old_list = old_slots_data if isinstance(old_slots_data, list) else []
    new_slots = [s for s in slots if s not in old_list]

    if not new_slots:
        return None

    display_slots = [f"[NEW] {s}" if s in new_slots else s for s in slots]
    return _("slots-new-header"), display_slots, "new"


def _handle_decrease(
    slots: list[str],
    old_slots_data: list[str] | str | None,
) -> tuple[str, list[str], str] | None:
    """Обрабатывает случай, когда количество слотов уменьшилось.

    Уведомление отправляется только если новое количество ниже порога
    ``SLOT_THRESHOLD_ABSOLUTE`` или процент уменьшения превышает
    ``SLOT_THRESHOLD_PERCENTAGE``.

    Returns:
        (header, slots, "decreased") если нужно уведомить об уменьшении,
        None если изменений нет или они незначительны.
    """
    old_list = old_slots_data if isinstance(old_slots_data, list) else []
    old_count = len(old_list)
    new_count = len(slots)

    if new_count >= old_count:
        return None

    should_notify = False
    if new_count < settings.SLOT_THRESHOLD_ABSOLUTE:
        should_notify = True
    elif old_count > 0:
        percentage_decrease = (old_count - new_count) / old_count
        if percentage_decrease >= settings.SLOT_THRESHOLD_PERCENTAGE:
            should_notify = True

    if not should_notify:
        return None

    header = _("slots-decreased-header").format(new=new_count, old=old_count)
    return header, slots, "decreased"


def _classify_slot_change(
    slots: list[str] | None, old_slots_data: list[str] | str | None
) -> tuple[str, list[str] | None, str] | None:
    """Классификация изменений слотов.

    Разбита на три вспомогательных метода для снижения цикломатической сложности:

    - :func:`_handle_disappeared` — слоты исчезли
    - :func:`_handle_appeared` — слоты появились (впервые или новые)
    - :func:`_handle_decrease` — количество слотов уменьшилось

    Returns:
        (header, display_slots, notify_type) или None если уведомлять не нужно.
        notify_type: "empty" | "available" | "new" | "decreased"
    """
    if not slots:
        return _handle_disappeared(old_slots_data)

    result = _handle_appeared(slots, old_slots_data)
    if result is not None:
        return result

    return _handle_decrease(slots, old_slots_data)


async def _extract_doctor_info(
    d_info: MonitoringEntry | str,
    p_info: PatientInfo,
) -> tuple[str, str, str]:
    """Извлекает имя врача, специальность и clinic_id из данных мониторинга.

    Returns:
        Кортеж (d_name, doctor_specialty, clinic_id).
    """
    if isinstance(d_info, dict):
        d_name = d_info.get("name", _("doctor-fallback-name"))
        doctor_specialty = d_info.get("specialty", "")
        clinic_id = d_info.get(
            "clinic_id",
            p_info.get("clinic_id", settings.DEFAULT_CLINIC_ID),
        )
    else:
        d_name = d_info
        doctor_specialty = ""
        clinic_id = p_info.get("clinic_id", settings.DEFAULT_CLINIC_ID)
    return d_name, doctor_specialty, clinic_id


async def _apply_jitter(min_delay: float = 1.0, max_delay: float = 3.0) -> None:
    """Случайная задержка для распределения стартов запросов во времени."""
    await asyncio.sleep(random.uniform(min_delay, max_delay))


class _SlotsFetchCache:
    """Один live-запрос на пару (клиника, врач) в рамках одной итерации.

    Эндпоинт ``/appointment_list/`` принимает ``patient_id``, но ответ по одной
    паре (clinic_id, doctor_id) совпадает для разных пациентов: проверено на
    проде 26.09.2026 (clinic_id=62, d_id=49709000 — 52 слота, наборы идентичны
    для двух пациентов). Поэтому повторные запросы в одной итерации не нужны —
    результат берётся из кэша, а первый запрос переиспользуется остальными
    мониторингами той же пары.

    Кэш живёт одну итерацию монитора: между циклами данные считаются свежими.
    """

    def __init__(self) -> None:
        self._tasks: dict[tuple[str, str], asyncio.Task[CheckSlotsResult | None]] = {}
        self._lock = asyncio.Lock()

    async def get(
        self,
        api: ZdravClient,
        d_id: str,
        p_id: str,
        clinic_id: str,
        semaphore: asyncio.Semaphore,
    ) -> CheckSlotsResult | None:
        """Возвращает результат запроса, переиспользуя незавершённый/готовый.

        Args:
            api: Клиент zdrav.lenreg.ru.
            d_id: Идентификатор врача.
            p_id: Идентификатор пациента (из первого запроса по паре).
            clinic_id: Идентификатор клиники.
            semaphore: Семафор конкурентности HTTP-запросов.

        Returns:
            ``CheckSlotsResult | None`` — тот же тип, что у ``api.check_slots``.
        """
        key = (str(clinic_id), str(d_id))
        async with self._lock:
            task = self._tasks.get(key)
            if task is None:
                task = asyncio.create_task(
                    self._fetch(api, d_id, p_id, clinic_id, semaphore)
                )
                self._tasks[key] = task
        return await task

    @staticmethod
    async def _fetch(
        api: ZdravClient,
        d_id: str,
        p_id: str,
        clinic_id: str,
        semaphore: asyncio.Semaphore,
    ) -> CheckSlotsResult | None:
        async with semaphore:
            return await api.check_slots(
                d_id, p_id, clinic_id, limiter=api.limiter_monitor
            )


async def _check_empty_slots_protection(
    slots: list[str] | None,
    cache_key: str,
    d_id: str,
    p_id: str,
    empty_counts_lock: asyncio.Lock,
    empty_counts: dict[str, int],
) -> bool:
    """Защита от ложных пустых ответов API (требуется 3 пустых подряд).

    Returns:
        True если слоты можно обрабатывать дальше, False если нужно пропустить
        (ещё не набрано 3 пустых подряд).
    """
    async with empty_counts_lock:
        if not slots:
            empty_counts[cache_key] = empty_counts.get(cache_key, 0) + 1
            if empty_counts[cache_key] < 3:
                logger.info(
                    "Empty slots for {}, {}. Retry {}/3",
                    d_id,
                    p_id,
                    empty_counts[cache_key],
                )
                return False
        else:
            empty_counts[cache_key] = 0
    return True


def _build_notification_message(
    p_info: PatientInfo,
    d_name: str,
    doctor_specialty: str,
    header: str,
    display_slots: list[str] | None,
    slots: list[str],
) -> str:
    """Форматирует текст уведомления об изменении слотов.

    Args:
        display_slots: None если слоты исчезли, иначе список для отображения.

    Returns:
        Готовый текст для отправки в Telegram.
    """
    patient_label = p_info.get("alias") or p_info.get("fio", _("patient-fallback-name"))
    d_name_display = shorten_fio(d_name)
    d_spec_display = shorten_specialty(doctor_specialty)
    spec_text = f"[{d_spec_display}]\n" if d_spec_display else ""
    has_slots = bool(slots)
    link = _("signup-link-text").format(url=settings.SIGNUP_URL) if has_slots else ""

    if display_slots is None:
        return format_notification_text(
            patient_label,
            d_name_display,
            spec_text,
            header,
            _("slots-disappeared-body"),
        )

    slot_lines = format_slots(
        display_slots,
        detail_threshold=settings.SLOT_DETAIL_THRESHOLD,
        compact_threshold=settings.SLOT_COMPACT_THRESHOLD,
    )
    return format_notification_text(
        patient_label,
        d_name_display,
        spec_text,
        header,
        "\n".join(slot_lines),
        link,
    )


async def _send_notification(
    notifier: NotificationPort | None,
    uid: str,
    p_id: str,
    d_id: str,
    msg: str,
    notify_type: str,
) -> None:
    """Отправляет уведомление через порт, если он передан.

    При ``notifier=None`` (вызов из REST API) отправка пропускается.
    """
    if notifier is None:
        return
    await notifier.notify(int(uid), p_id, d_id, msg, notify_type)


async def _notify_pair(
    notifier: NotificationPort | None,
    db: DatabaseManager,
    uid: str,
    p_id: str,
    d_id: str,
    p_info: PatientInfo,
    d_name: str,
    doctor_specialty: str,
    header: str,
    display_slots: list[str] | None,
    slots: list[str],
    notify_type: str,
) -> None:
    """Отправляет уведомление о событии пары (путь ``SCREEN_ENABLED=false``).

    Локаль получателя: текст и клавиатура — на языке клиента.
    """
    if notifier is None:
        return
    recipient_lang = resolve_language(await db.get_user_language(uid))
    with use_language(recipient_lang):
        msg = _build_notification_message(
            p_info, d_name, doctor_specialty, header, display_slots, slots
        )
        await _send_notification(notifier, uid, p_id, d_id, msg, notify_type)


async def _fetch_slots(
    api: ZdravClient,
    d_id: str,
    p_id: str,
    clinic_id: str,
    semaphore: asyncio.Semaphore,
    slots_cache: _SlotsFetchCache | None,
) -> CheckSlotsResult | None:
    """Запрашивает слоты врача: через кэш итерации либо напрямую под семафором."""
    if slots_cache is not None:
        return await slots_cache.get(api, d_id, p_id, clinic_id, semaphore)
    async with semaphore:
        return await api.check_slots(d_id, p_id, clinic_id, limiter=api.limiter_monitor)


def _clean_slot(display_slot: str, prefix: str) -> str:
    """Отбрасывает служебный префикс ``[NEW]`` у строки для сравнения."""
    return (
        display_slot[len(prefix) :] if display_slot.startswith(prefix) else display_slot
    )


def _filter_pair_slots(
    d_info: MonitoringEntry | str,
    slots: list[str],
    display_slots: list[str] | None,
) -> tuple[list[str], list[str] | None] | None:
    """Фильтрует слоты пары по настройкам пользователя (T-18).

    Returns:
        ``(slots, display_slots)`` после фильтра либо ``None``, если после
        фильтрации показывать нечего (уведомление и строка экрана не нужны).
    """
    if not slots or not isinstance(d_info, dict):
        return slots, display_slots
    filtered_slots = filter_slots_by_user_prefs(slots, d_info)
    if not filtered_slots:
        return None
    if display_slots is None:
        return filtered_slots, None
    new_prefix = "[NEW] "
    kept = [ds for ds in display_slots if _clean_slot(ds, new_prefix) in filtered_slots]
    return filtered_slots, kept or filtered_slots


async def _check_single_doctor(
    semaphore: asyncio.Semaphore,
    api: ZdravClient,
    uid: str,
    p_id: str,
    d_id: str,
    d_info: MonitoringEntry | str,
    p_info: PatientInfo,
    empty_counts_lock: asyncio.Lock,
    empty_counts: dict[str, int],
    notifier: NotificationPort | None,
    db: DatabaseManager,
    slots_cache: _SlotsFetchCache | None = None,
    *,
    initial_sync: bool = False,
    notify_via_port: bool = True,
) -> PairState | None:
    """Проверяет слоты одного врача: кэш, классификация, уведомление или состояние.

    Полный цикл: jitter → извлечение данных → API-запрос → проверка пустых
    ответов → кэш → классификация → фильтрация → уведомление/состояние пары.
    Семафор ограничивает количество одновременных HTTP-запросов к API.

    Args:
        notify_via_port: ``True`` — прежний путь: уведомление отправляется
            здесь же (``SCREEN_ENABLED=false``). ``False`` — режим единого
            экрана: отправки нет, возвращается состояние пары, чтобы монитор
            сделал один вызов ``update_screen`` на пользователя за итерацию.
        initial_sync: подавлять события первого цикла (кэш только заполняется).

    Returns:
        :class:`~src.services.screen_collect.PairState` в режиме экрана либо
        ``None`` (нет данных, событий, отправлено уведомление и т.п.).
    """
    await _apply_jitter()

    d_name, doctor_specialty, clinic_id = await _extract_doctor_info(d_info, p_info)

    logger.debug(
        "Monitor checking slots: d_id={}, p_id={}, clinic_id={}",
        d_id,
        p_id,
        clinic_id,
    )

    # Один live-запрос на пару (clinic_id, doctor_id) за итерацию.
    slots_result = await _fetch_slots(
        api, d_id, p_id, clinic_id, semaphore, slots_cache
    )
    logger.debug(f"API result for {d_id}: {slots_result}")

    if slots_result is None:
        logger.warning(f"API error for {d_id}, {p_id}. Skipping.")
        return None

    slots = slots_result.formatted
    cache_key = f"{uid}_{p_id}_{d_id}"

    # Защита от ложных пустых ответов API (3 пустых подряд).
    if not await _check_empty_slots_protection(
        slots, cache_key, d_id, p_id, empty_counts_lock, empty_counts
    ):
        return None

    # swap_cache_key использует Redis GETSET — атомарно на уровне Redis.
    old_slots_data = await swap_cache_key(cache_key, slots if slots else "NONE")
    result = _classify_slot_change(slots, old_slots_data)

    if result is None:
        # События нет: пара всё равно остаётся в сводке экрана (без маркера).
        return PairState(p_id=p_id, d_id=d_id, has_new_events=False, slots=tuple(slots))

    header, display_slots, notify_type = result
    filtered = _filter_pair_slots(d_info, slots, display_slots)
    if filtered is None:
        logger.debug(
            "Все слоты отфильтрованы для d_id={} p_id={} (настройки пользователя)",
            d_id,
            p_id,
        )
        return None
    slots, display_slots = filtered

    if initial_sync:
        logger.debug(
            "Initial sync — пропускаем уведомление для {} ({}), кэш заполнен",
            d_id,
            p_id,
        )
        return None

    if notify_via_port:
        await _notify_pair(
            notifier,
            db,
            uid,
            p_id,
            d_id,
            p_info,
            d_name,
            doctor_specialty,
            header,
            display_slots,
            slots,
            notify_type,
        )
        return None

    return PairState(
        p_id=p_id,
        d_id=d_id,
        has_new_events=True,
        display_slots=None if display_slots is None else tuple(display_slots),
        slots=tuple(slots),
    )


def _cleanup_stale_empty_counts(
    users_data: dict,
    empty_counts: dict[str, int],
    empty_counts_lock: asyncio.Lock,
) -> None:
    """Удаляет ключи empty_counts, которых больше нет в активном мониторинге.

    Вызывается синхронно, но принимает ``empty_counts_lock`` для совместимости —
    вызывающий код обязан захватить лок перед вызовом.
    """
    active_keys = {
        f"{uid}_{p_id}_{d_id}"
        for uid, u_info in users_data.items()
        for p_id, doctors in u_info.get("monitoring", {}).items()
        for d_id in doctors
    }
    for stale in list(empty_counts.keys()):
        if stale not in active_keys:
            del empty_counts[stale]


async def _run_patient_doctor_tasks(
    semaphore: asyncio.Semaphore,
    api: ZdravClient,
    uid: str,
    p_id: str,
    doctors: Mapping[str, MonitoringEntry | str],
    p_info: PatientInfo,
    empty_counts_lock: asyncio.Lock,
    empty_counts: dict[str, int],
    notifier: NotificationPort | None,
    db: DatabaseManager,
    slots_cache: _SlotsFetchCache | None = None,
    *,
    initial_sync: bool = False,
    notify_via_port: bool = True,
) -> list[PairState]:
    """Собирает и параллельно запускает проверку всех врачей одного пациента.

    Использует ``asyncio.gather()`` с ``return_exceptions=True`` — ошибки
    в отдельных задачах не прерывают проверку остальных врачей.

    Returns:
        Состояния пар в режиме единого экрана (``notify_via_port=False``);
        в прежнем режиме список пуст — уведомления отправлены внутри задач.
    """
    doctor_tasks = []
    for d_id, d_info in doctors.items():
        task = _check_single_doctor(
            semaphore=semaphore,
            api=api,
            uid=uid,
            p_id=p_id,
            d_id=d_id,
            d_info=d_info,
            p_info=p_info,
            empty_counts_lock=empty_counts_lock,
            empty_counts=empty_counts,
            notifier=notifier,
            db=db,
            slots_cache=slots_cache,
            initial_sync=initial_sync,
            notify_via_port=notify_via_port,
        )
        doctor_tasks.append(task)

    results = await asyncio.gather(*doctor_tasks, return_exceptions=True)
    states: list[PairState] = []
    for i, result in enumerate(results):
        if isinstance(result, BaseException):
            logger.opt(exception=True).error(
                "Doctor task {} failed: {}",
                i,
                result,
            )
        elif result is not None:
            states.append(result)
    return states


async def _fill_clinic_names(
    db: DatabaseManager,
    monitoring: Mapping[str, Mapping[str, MonitoringEntry | str]],
    cache: dict[str, str],
) -> None:
    """Дополняет кэш названий клиник для пар текущей итерации.

    Кэш живёт одну итерацию мониторинга: название клиники меняется редко, а
    запрос по каждому врачу каждого пользователя был бы лишним.
    """
    for doctors in monitoring.values():
        for d_info in doctors.values():
            clinic_id = (
                str(d_info.get("clinic_id", "")) if isinstance(d_info, dict) else ""
            )
            if not clinic_id or clinic_id in cache:
                continue
            cache[clinic_id] = await db.get_clinic_name(clinic_id) or ""


async def _update_user_screen(
    screen_service: ScreenServicePort,
    db: DatabaseManager,
    uid: str,
    user_info: UserData,
    monitoring: Mapping[str, Mapping[str, MonitoringEntry | str]],
    states: list[PairState],
    clinic_names: dict[str, str],
) -> None:
    """Обновляет единый экран пользователя одним вызовом за итерацию.

    Ошибка экрана не прерывает итерацию мониторинга: она логируется на уровне
    ERROR, остальные пользователи обрабатываются как обычно.
    """
    chat_id = parse_id(uid)
    try:
        recipient_lang = resolve_language(await db.get_user_language(uid))
        await _fill_clinic_names(db, monitoring, clinic_names)
        with use_language(recipient_lang):
            items = build_screen_items(
                user_info.get("patients", {}),
                monitoring,
                states=states,
                clinic_names=clinic_names,
            )
            await screen_service.update_screen(chat_id, chat_id, items)
    except Exception:
        logger.opt(exception=True).error(
            "Не удалось обновить экран чата uid={} — итерация продолжается", uid
        )


async def _run_monitoring_iteration(
    semaphore: asyncio.Semaphore,
    api: ZdravClient,
    notifier: NotificationPort | None,
    db: DatabaseManager,
    empty_counts_lock: asyncio.Lock,
    empty_counts: dict[str, int],
    *,
    initial_sync: bool = False,
    screen_service: ScreenServicePort | None = None,
) -> None:
    """Одна итерация мониторинга: обход всех пользователей, пациентов, врачей.

    Выполняет очистку устаревших ключей empty_counts, затем итерацию
    по всем активным цепочкам мониторинга.

    При ``SCREEN_ENABLED=true`` и переданном ``screen_service`` уведомления не
    отправляются внутри ``gather`` по врачам: сначала собираются состояния всех
    пар пользователя, затем выполняется **один** ``update_screen`` на
    пользователя за итерацию (естественный коалесинг). Иначе работает прежний
    путь — уведомление на каждую пару (точка отката ``SCREEN_ENABLED=false``).
    """
    users_data = db.data

    # Один live-запрос на пару (клиника, врач) за итерацию (MA-2): повторные
    # запросы той же пары от других пациентов берут готовый результат.
    slots_cache = _SlotsFetchCache()

    # Пользователи на паузе (DASH-8) пропускаются целиком: мониторинг
    # приостановлен, но цепочки пациент-врач сохранены.
    paused_uids = await db.get_paused_uids()

    # Очистка empty_counts от ключей, которых больше нет в активном мониторинге
    async with empty_counts_lock:
        _cleanup_stale_empty_counts(users_data, empty_counts, empty_counts_lock)

    screen_mode = screen_service is not None and settings.SCREEN_ENABLED
    clinic_names: dict[str, str] = {}

    for uid, u_info in users_data.items():
        if uid in paused_uids:
            continue
        monitoring = u_info.get("monitoring", {})
        states: list[PairState] = []
        for p_id, doctors in monitoring.items():
            p_info = u_info["patients"].get(p_id)
            if p_info is None:
                logger.warning(
                    "Мониторинг ссылается на несуществующего пациента "
                    "p_id={} (uid={}), пропускаю",
                    p_id,
                    uid,
                )
                continue

            states.extend(
                await _run_patient_doctor_tasks(
                    semaphore=semaphore,
                    api=api,
                    uid=uid,
                    p_id=p_id,
                    doctors=doctors,
                    p_info=p_info,
                    empty_counts_lock=empty_counts_lock,
                    empty_counts=empty_counts,
                    notifier=notifier,
                    db=db,
                    slots_cache=slots_cache,
                    initial_sync=initial_sync,
                    notify_via_port=not screen_mode,
                )
            )

        # Экран обновляется один раз на пользователя; пользователи без
        # мониторинга экран не получают (его удалит TTL-ветка очистки).
        if screen_service is not None and screen_mode and any(monitoring.values()):
            await _update_user_screen(
                screen_service,
                db,
                uid,
                u_info,
                monitoring,
                states,
                clinic_names,
            )


async def monitor_loop(
    notifier: NotificationPort | None,
    api: ZdravClient,
    db: DatabaseManager,
    *,
    initial_sync: bool = True,
    screen_service: ScreenServicePort | None = None,
) -> None:
    """Главный цикл мониторинга слотов.

    Пользователи → пациенты → врачи.  Проверка врачей внутри одного пациента
    выполняется параллельно через asyncio.gather() с семафором (10 одновременных
    HTTP-запросов).  Между полными циклами — jitter 42-85 секунд.

    Args:
        initial_sync: Если True, первый цикл только заполняет кэш без отправки
            уведомлений.  Используется для подавления ложных уведомлений
            после перезапуска бота.
        screen_service: Сервис единого экрана чата. При ``SCREEN_ENABLED=true``
            уведомления заменяются одним обновлением экрана на пользователя
            за итерацию; ``None`` — прежний путь уведомлений.
    """
    logger.info("Цикл мониторинга запущен")

    empty_counts: dict[str, int] = {}
    empty_counts_lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(10)

    # Флаг начальной синхронизации: первый цикл только заполняет кэш,
    # не отправляя уведомления, чтобы избежать спама после перезапуска.
    _initial_sync = initial_sync
    if _initial_sync:
        logger.info("Initial sync active — уведомления подавлены до заполнения кэша")

    while True:
        try:
            await _run_monitoring_iteration(
                semaphore=semaphore,
                api=api,
                notifier=notifier,
                db=db,
                empty_counts_lock=empty_counts_lock,
                empty_counts=empty_counts,
                initial_sync=_initial_sync,
                screen_service=screen_service,
            )

            # Первый полный цикл завершён — снимаем флаг начальной синхронизации
            if _initial_sync:
                logger.info("Initial sync completed — уведомления разблокированы")
                _initial_sync = False

            jitter = random.uniform(42, 85)
            await asyncio.sleep(jitter)

        except asyncio.CancelledError:
            logger.info("Цикл мониторинга остановлен (cancelled)")
            break
        except Exception as e:
            logger.opt(exception=True).error(f"Ошибка в цикле мониторинга: {e}")
            if _initial_sync:
                logger.info(
                    "Initial sync завершён с ошибками — уведомления разблокированы"
                )
                _initial_sync = False
            await asyncio.sleep(60)


async def _monitor_iteration(
    notifier: NotificationPort | None,
    api: ZdravClient,
    db: DatabaseManager,
    *,
    state: dict,
    screen_service: ScreenServicePort | None = None,
) -> None:
    """Одна итерация мониторинга слотов (для BackgroundTaskManager).

    Выполняет один полный цикл проверки всех активных цепочек мониторинга.
    Менеджер владеет ``while True``, sleep, retry и обработкой CancelledError.

    Args:
        notifier: Порт отправки уведомлений (None — отправка не выполняется).
        api: Клиент API zdrav.lenreg.ru.
        db: Менеджер базы данных.
        state: Словарь с мутабельным состоянием между итерациями:
            - ``initial_sync`` (bool): подавлять ли уведомления в первом цикле.
            - ``semaphore`` (asyncio.Semaphore): семафор конкурентности.
            - ``empty_counts`` (dict): счётчики пустых слотов.
            - ``empty_counts_lock`` (asyncio.Lock): лок для empty_counts.
        screen_service: Сервис единого экрана чата (``SCREEN_ENABLED``).
    """
    initial_sync = state.get("initial_sync", True)

    await _run_monitoring_iteration(
        semaphore=state["semaphore"],
        api=api,
        notifier=notifier,
        db=db,
        empty_counts_lock=state["empty_counts_lock"],
        empty_counts=state["empty_counts"],
        initial_sync=initial_sync,
        screen_service=screen_service,
    )

    if initial_sync:
        logger.info("Initial sync completed — уведомления разблокированы")
        state["initial_sync"] = False


async def force_check_single_doctor(
    api: ZdravClient,
    uid: str,
    p_id: str,
    d_id: str,
    d_info: MonitoringEntry | str,
    p_info: PatientInfo,
    db: DatabaseManager,
) -> tuple[list[str] | None, str]:
    """Принудительная проверка слотов одного врача без отправки уведомлений.

    Использует :func:`_check_single_doctor` с ``initial_sync=True`` —
    выполняет живой запрос к API, обновляет кэш мониторинга и пишет лог,
    но НЕ отправляет Telegram-уведомления.

    Используется REST API ``POST /api/user/doctors/check`` для мгновенной
    проверки слотов по запросу пользователя.

    Returns:
        (slots, cache_key) — сырые слоты (list[str] или None при ошибке)
        и ключ кэша для последующего чтения статуса.
    """
    semaphore = asyncio.Semaphore(1)
    empty_counts: dict[str, int] = {}
    empty_counts_lock = asyncio.Lock()

    await _check_single_doctor(
        semaphore=semaphore,
        api=api,
        uid=uid,
        p_id=p_id,
        d_id=d_id,
        d_info=d_info,
        p_info=p_info,
        empty_counts_lock=empty_counts_lock,
        empty_counts=empty_counts,
        notifier=None,  # Без уведомлений
        db=db,
        initial_sync=True,
    )

    cache_key = f"{uid}_{p_id}_{d_id}"
    cached = await get_cache_key(cache_key)

    # Приводим к list[str] | None
    if isinstance(cached, list):
        return cached, cache_key
    return None, cache_key
