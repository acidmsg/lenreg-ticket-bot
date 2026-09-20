import asyncio
import json
import random
import time
from collections.abc import Mapping
from pathlib import Path

import aiolimiter
from aiogram import Bot
from aiogram import exceptions as tg_exceptions
from loguru import logger

from src.api.zdrav_client import ZdravClient
from src.assets.utils import get_notify_image_path
from src.config import settings
from src.database.manager import DatabaseManager
from src.database.types import MonitoringEntry, PatientInfo
from src.i18n import _
from src.services.telegram_health import (
    TELEGRAM_SEND_RATE_LIMIT,
    TELEGRAM_SEND_RATE_PERIOD,
    telegram_health,
)
from src.utils.cache import get_cache_key, swap_cache_key
from src.utils.helpers import (
    format_notification_text,
    format_slots,
    shorten_fio,
    shorten_specialty,
)
from src.utils.telegram_utils import send_or_update_message

# ── Rate limiter уведомлений Telegram (per-loop) ──────────────────────
# Telegram Bot API: ≤ 25 сообщений/сек суммарно — параметры лимита сохраняются.
_TELEGRAM_MAX_RATE = TELEGRAM_SEND_RATE_LIMIT
_TELEGRAM_TIME_PERIOD = TELEGRAM_SEND_RATE_PERIOD

# Реестр лимитеров по event loop'у. Ключ — сам loop (не id): id переиспользуется
# после сборки мусора, что привело бы к ложному попаданию в чужой лимитер.
_telegram_limiters: dict[asyncio.AbstractEventLoop, aiolimiter.AsyncLimiter] = {}


def _prune_closed_loops() -> None:
    """Удаляет из реестра лимитеры закрытых event loop'ов.

    ``WeakKeyDictionary`` здесь неприменим: ``aiolimiter.AsyncLimiter`` хранит в
    слоте ``_event_loop`` **сильную** ссылку на loop, поэтому значение удерживает
    свой ключ и слабое связывание не освобождает записи. Явная очистка по
    ``is_closed()`` делает рост структуры ограниченным числом живых loop'ов:
    в production loop ровно один, в тестах записи прежних loop'ов удаляются при
    следующем обращении.
    """
    for loop in [item for item in _telegram_limiters if item.is_closed()]:
        del _telegram_limiters[loop]


def _get_telegram_limiter() -> aiolimiter.AsyncLimiter:
    """Возвращает лимитер отправки уведомлений для текущего event loop.

    Лимитер — это пропускной шлюз, а не защита разделяемого состояния, поэтому
    его допустимо создавать per-loop (в отличие от ``Lock`` и ``Event``).
    Общая семантика 25 сообщений/с не нарушается: в production отправитель
    уведомлений ровно один — фоновая задача мониторинга в главном event loop,
    и она получает из реестра единственный экземпляр. В тестах каждый loop
    получает свежий лимитер, что устраняет перепривязку ``aiolimiter`` и
    ``RuntimeWarning`` о переиспользовании экземпляра между loop'ами.

    Вызывается только из корутины: без running loop ``get_running_loop()``
    возбуждает ``RuntimeError`` — это контракт, а не ошибка.
    """
    loop = asyncio.get_running_loop()
    _prune_closed_loops()
    limiter = _telegram_limiters.get(loop)
    if limiter is None:
        limiter = aiolimiter.AsyncLimiter(
            max_rate=_TELEGRAM_MAX_RATE,
            time_period=_TELEGRAM_TIME_PERIOD,
        )
        _telegram_limiters[loop] = limiter
    return limiter


async def _send_telegram_safe(
    bot: Bot,
    chat_id: int,
    db: DatabaseManager,
    p_id: str,
    d_id: str,
    text: str,
    *,
    photo_path: Path | None = None,
) -> bool:
    """Отправка уведомления в Telegram с rate limiting и обработкой 429.

    Обёртка над :func:`send_or_update_message`, которая:
    - Применяет per-loop лимитер ``_get_telegram_limiter()`` (≤25 сообщений/сек
      суммарно для отправителя).
    - Перехватывает ``TelegramRetryAfter`` (429), ждёт ``retry_after``
      и повторяет отправку один раз.
    - Логирует все ошибки отправки.
    - Пишет результат в :data:`~src.services.telegram_health.telegram_health`:
      глубина очереди, успешные/неудачные отправки, паузы по 429 (UX-7).

    Returns:
        True если отправка успешна, False при ошибке.
    """
    telegram_health.queue_enter()
    try:
        async with _get_telegram_limiter():
            try:
                await send_or_update_message(
                    bot,
                    chat_id,
                    db,
                    p_id,
                    d_id,
                    text,
                    photo_path=photo_path,
                )
            except tg_exceptions.TelegramRetryAfter as e:
                logger.warning(
                    "Telegram 429: retry after {:.1f}s for chat {}",
                    e.retry_after,
                    chat_id,
                )
                telegram_health.record_retry_after(e.retry_after)
                await asyncio.sleep(e.retry_after)
                try:
                    await send_or_update_message(
                        bot,
                        chat_id,
                        db,
                        p_id,
                        d_id,
                        text,
                        photo_path=photo_path,
                    )
                except Exception as e2:
                    logger.error(
                        "Telegram retry failed for chat {}: {}",
                        chat_id,
                        e2,
                        exc_info=True,
                    )
                    telegram_health.record_send_error()
                    return False
            except Exception as e:
                logger.error(
                    "Telegram send failed for chat {}: {}",
                    chat_id,
                    e,
                    exc_info=True,
                )
                telegram_health.record_send_error()
                return False

        telegram_health.record_send_ok()
        return True
    finally:
        telegram_health.queue_exit()


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

    date_from: str = str(monitoring_entry.get("date_from", "") or "")
    date_to: str = str(monitoring_entry.get("date_to", "") or "")
    time_from: str = str(monitoring_entry.get("time_from", "") or "")
    time_to: str = str(monitoring_entry.get("time_to", "") or "")
    specific_dates = _parse_specific_dates(monitoring_entry)

    from datetime import date, time

    filtered: list[str] = []
    for slot_str in slots:
        # Парсим слот: "YYYY-MM-DD в HH:MM"
        try:
            parts = slot_str.split(" в ")
            slot_date_str = parts[0].strip()
            slot_time_str = parts[1].strip() if len(parts) > 1 else ""

            slot_date = date.fromisoformat(slot_date_str)
            slot_time = time.fromisoformat(slot_time_str) if slot_time_str else None
        except (ValueError, IndexError):
            # Невозможно распарсить — пропускаем слот (не должны доходить сюда)
            continue

        # Фильтр по дате
        if date_from:
            try:
                df = date.fromisoformat(date_from)
                if slot_date < df:
                    continue
            except ValueError:
                pass
        if date_to:
            try:
                dt = date.fromisoformat(date_to)
                if slot_date > dt:
                    continue
            except ValueError:
                pass

        # Фильтр по времени
        if time_from and slot_time:
            try:
                tf = time.fromisoformat(time_from)
                if slot_time < tf:
                    continue
            except ValueError:
                pass
        if time_to and slot_time:
            try:
                tt = time.fromisoformat(time_to)
                if slot_time > tt:
                    continue
            except ValueError:
                pass

        # Фильтр по конкретным датам
        if specific_dates and slot_date_str not in specific_dates:
            continue

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


async def _log_monitoring_change(
    db: DatabaseManager,
    uid: str,
    p_id: str,
    d_id: str,
    d_info: MonitoringEntry | str,
    p_info: PatientInfo,
    slots: list[str] | None,
    notify_type: str,
) -> None:
    """Записывает изменение слотов в monitoring_log.

    Args:
        notify_type: "available" | "new" | "empty" | "decreased"
    """
    status_map = {
        "available": "появился",
        "new": "появился",
        "empty": "исчез",
        "decreased": "уменьшился",
    }
    log_status = status_map.get(notify_type, notify_type)

    slot_date = ""
    if slots:
        slot_date = slots[0].split(",")[0].strip() if "," in slots[0] else slots[0]

    patient_label = p_info.get("alias") or p_info.get("fio", _("patient-fallback-name"))
    d_name = (
        d_info.get("name", _("doctor-fallback-name"))
        if isinstance(d_info, dict)
        else str(d_info)
    )
    doctor_specialty = d_info.get("specialty", "") if isinstance(d_info, dict) else ""
    clinic_id_for_log = d_info.get("clinic_id", "") if isinstance(d_info, dict) else ""

    clinic_name = ""
    if clinic_id_for_log:
        try:
            name = await db.get_clinic_name(clinic_id_for_log)
            if name:
                clinic_name = name
        except Exception:
            logger.debug(
                "Не удалось получить имя клиники clinic_id={} для p_id={}",
                clinic_id_for_log,
                p_id,
            )

    try:
        await db.add_monitoring_log(
            uid=uid,
            p_id=p_id,
            d_id=d_id,
            doctor_name=d_name,
            patient_name=patient_label,
            specialty=doctor_specialty,
            clinic_name=clinic_name,
            slot_date=slot_date,
            status=log_status,
            ts=time.time(),
        )
    except Exception as e:
        logger.debug(f"Не удалось записать лог мониторинга: {e}")


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
    bot: Bot | None,
    uid: str,
    db: DatabaseManager,
    p_id: str,
    d_id: str,
    msg: str,
    notify_type: str,
) -> None:
    """Отправляет уведомление в Telegram, если передан bot.

    При ``bot=None`` (вызов из REST API) отправка пропускается.
    """
    if bot is not None:
        photo_path = get_notify_image_path(notify_type)
        await _send_telegram_safe(
            bot,
            int(uid),
            db,
            p_id,
            d_id,
            msg,
            photo_path=photo_path,
        )


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
    bot: Bot | None,
    db: DatabaseManager,
    *,
    initial_sync: bool = False,
) -> None:
    """Проверяет слоты для одного врача и отправляет уведомления при изменениях.

    Выполняет полный цикл: jitter → извлечение данных → API-запрос → проверка
    пустых ответов → кэш → классификация → логирование → уведомление.
    Семафор ограничивает количество одновременных HTTP-запросов к API.

    При ``initial_sync=True`` уведомления подавляются — кэш только заполняется.
    При ``bot=None`` уведомления не отправляются (используется из REST API).
    """
    # --- Шаг 1: jitter-задержка ---
    await _apply_jitter()

    # --- Шаг 2: извлечение данных врача ---
    d_name, doctor_specialty, clinic_id = await _extract_doctor_info(d_info, p_info)

    logger.info(
        "Monitor checking slots: d_id={}, p_id={}, clinic_id={}",
        d_id,
        p_id,
        clinic_id,
    )

    # --- Шаг 3: API-запрос под семафором ---
    async with semaphore:
        slots_result = await api.check_slots(
            d_id, p_id, clinic_id, limiter=api.limiter_monitor
        )

    logger.info(f"API result for {d_id}: {slots_result}")

    if slots_result is None:
        logger.warning(f"API error for {d_id}, {p_id}. Skipping.")
        return

    slots = slots_result.formatted
    cache_key = f"{uid}_{p_id}_{d_id}"

    # --- Шаг 4: защита от ложных пустых ответов ---
    if not await _check_empty_slots_protection(
        slots, cache_key, d_id, p_id, empty_counts_lock, empty_counts
    ):
        return

    # --- Шаг 5: атомарное обновление кэша ---
    # swap_cache_key использует Redis GETSET — атомарно на уровне Redis.
    new_cache_value = slots if slots else "NONE"
    old_slots_data = await swap_cache_key(cache_key, new_cache_value)

    # --- Шаг 6: классификация изменений ---
    result = _classify_slot_change(slots, old_slots_data)

    # Без изменений — выходим
    if result is None:
        return

    header, display_slots, notify_type = result

    # --- Шаг 6.5: фильтрация слотов по настройкам пользователя (T-18) ---
    if slots and isinstance(d_info, dict):
        filtered_slots = filter_slots_by_user_prefs(slots, d_info)
        if not filtered_slots:
            # После фильтрации слотов не осталось — пропускаем уведомление
            logger.info(
                "Все слоты отфильтрованы для d_id={} p_id={} (настройки пользователя)",
                d_id,
                p_id,
            )
            return
        # Обновляем display_slots: убираем те, что не прошли фильтр
        if display_slots is not None:
            # display_slots может содержать префикс [NEW], матчим по чистому слоту
            _new_prefix = "[NEW] "
            display_filtered: list[str] = []
            for ds in display_slots:
                clean = ds[len(_new_prefix) :] if ds.startswith(_new_prefix) else ds
                if clean in filtered_slots:
                    display_filtered.append(ds)
                elif ds.startswith(_new_prefix):
                    # [NEW] слот, который не прошёл фильтр — ищем без префикса
                    pass
            display_slots = display_filtered if display_filtered else filtered_slots
        slots = filtered_slots

    # --- Шаг 7: логирование изменения ---
    await _log_monitoring_change(
        db, uid, p_id, d_id, d_info, p_info, slots, notify_type
    )

    # --- Initial sync: только кэш, без уведомлений ---
    if initial_sync:
        logger.info(
            "Initial sync — пропускаем уведомление для {} ({}), кэш заполнен",
            d_id,
            p_id,
        )
        return

    # --- Шаг 8: формирование и отправка уведомления ---
    msg = _build_notification_message(
        p_info, d_name, doctor_specialty, header, display_slots, slots
    )
    await _send_notification(bot, uid, db, p_id, d_id, msg, notify_type)


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
    bot: Bot,
    db: DatabaseManager,
    *,
    initial_sync: bool = False,
) -> None:
    """Собирает и параллельно запускает проверку всех врачей одного пациента.

    Использует ``asyncio.gather()`` с ``return_exceptions=True`` — ошибки
    в отдельных задачах не прерывают проверку остальных врачей.
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
            bot=bot,
            db=db,
            initial_sync=initial_sync,
        )
        doctor_tasks.append(task)

    results = await asyncio.gather(*doctor_tasks, return_exceptions=True)
    for i, result in enumerate(results):
        if isinstance(result, BaseException):
            logger.error(
                "Doctor task {} failed: {}",
                i,
                result,
                exc_info=True,
            )


async def _run_monitoring_iteration(
    semaphore: asyncio.Semaphore,
    api: ZdravClient,
    bot: Bot,
    db: DatabaseManager,
    empty_counts_lock: asyncio.Lock,
    empty_counts: dict[str, int],
    *,
    initial_sync: bool = False,
) -> None:
    """Одна итерация мониторинга: обход всех пользователей, пациентов, врачей.

    Выполняет очистку устаревших ключей empty_counts, затем итерацию
    по всем активным цепочкам мониторинга.
    """
    users_data = db.data

    # Пользователи на паузе (DASH-8) пропускаются целиком: мониторинг
    # приостановлен, но цепочки пациент-врач сохранены.
    paused_uids = await db.get_paused_uids()

    # Очистка empty_counts от ключей, которых больше нет в активном мониторинге
    async with empty_counts_lock:
        _cleanup_stale_empty_counts(users_data, empty_counts, empty_counts_lock)

    for uid, u_info in users_data.items():
        if uid in paused_uids:
            continue
        monitoring = u_info.get("monitoring", {})
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

            await _run_patient_doctor_tasks(
                semaphore=semaphore,
                api=api,
                uid=uid,
                p_id=p_id,
                doctors=doctors,
                p_info=p_info,
                empty_counts_lock=empty_counts_lock,
                empty_counts=empty_counts,
                bot=bot,
                db=db,
                initial_sync=initial_sync,
            )


async def monitor_loop(
    bot: Bot,
    api: ZdravClient,
    db: DatabaseManager,
    *,
    initial_sync: bool = True,
) -> None:
    """Главный цикл мониторинга слотов.

    Пользователи → пациенты → врачи.  Проверка врачей внутри одного пациента
    выполняется параллельно через asyncio.gather() с семафором (10 одновременных
    HTTP-запросов).  Между полными циклами — jitter 42-85 секунд.

    Args:
        initial_sync: Если True, первый цикл только заполняет кэш без отправки
            уведомлений.  Используется для подавления ложных уведомлений
            после перезапуска бота.
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
                bot=bot,
                db=db,
                empty_counts_lock=empty_counts_lock,
                empty_counts=empty_counts,
                initial_sync=_initial_sync,
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
            logger.error(f"Ошибка в цикле мониторинга: {e}", exc_info=True)
            if _initial_sync:
                logger.info(
                    "Initial sync завершён с ошибками — уведомления разблокированы"
                )
                _initial_sync = False
            await asyncio.sleep(60)


async def _monitor_iteration(
    bot: Bot,
    api: ZdravClient,
    db: DatabaseManager,
    *,
    state: dict,
) -> None:
    """Одна итерация мониторинга слотов (для BackgroundTaskManager).

    Выполняет один полный цикл проверки всех активных цепочек мониторинга.
    Менеджер владеет ``while True``, sleep, retry и обработкой CancelledError.

    Args:
        bot: Экземпляр Telegram-бота.
        api: Клиент API zdrav.lenreg.ru.
        db: Менеджер базы данных.
        state: Словарь с мутабельным состоянием между итерациями:
            - ``initial_sync`` (bool): подавлять ли уведомления в первом цикле.
            - ``semaphore`` (asyncio.Semaphore): семафор конкурентности.
            - ``empty_counts`` (dict): счётчики пустых слотов.
            - ``empty_counts_lock`` (asyncio.Lock): лок для empty_counts.
    """
    initial_sync = state.get("initial_sync", True)

    await _run_monitoring_iteration(
        semaphore=state["semaphore"],
        api=api,
        bot=bot,
        db=db,
        empty_counts_lock=state["empty_counts_lock"],
        empty_counts=state["empty_counts"],
        initial_sync=initial_sync,
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
        bot=None,  # Без уведомлений
        db=db,
        initial_sync=True,
    )

    cache_key = f"{uid}_{p_id}_{d_id}"
    cached = await get_cache_key(cache_key)

    # Приводим к list[str] | None
    if isinstance(cached, list):
        return cached, cache_key
    return None, cache_key
