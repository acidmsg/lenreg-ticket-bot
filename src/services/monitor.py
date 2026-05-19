import asyncio
import random
import time
from pathlib import Path

from aiogram import Bot
from loguru import logger

from src.api.zdrav_client import ZdravClient
from src.assets.utils import get_notify_image_path
from src.config import settings
from src.database.manager import DatabaseManager
from src.database.types import MonitoringEntry, PatientInfo
from src.handlers.common import _send_or_update_message
from src.i18n import _
from src.services.healthcheck import _safe_set
from src.utils.cache import swap_cache_key
from src.utils.helpers import (
    format_notification_text,
    format_slots,
    shorten_fio,
    shorten_specialty,
)


async def _send_notification(
    bot: Bot,
    uid: str,
    text: str,
    db: DatabaseManager,
    p_id: str,
    d_id: str,
    photo_path: Path | None = None,
) -> None:
    """Отправляет уведомление пользователю.

    При наличии photo_path использует send_photo (изображение + caption),
    иначе — обычное send_message. Старое сообщение предварительно удаляется
    для эффекта «приклеивания».
    """
    try:
        await _send_or_update_message(
            bot,
            int(uid),
            db,
            p_id,
            d_id,
            text,
            photo_path=photo_path,
        )
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления: {e}")


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
    bot: Bot,
    db: DatabaseManager,
    *,
    initial_sync: bool = False,
) -> None:
    """Проверяет слоты для одного врача и отправляет уведомления при изменениях.

    Выполняет полный цикл: jitter → API-запрос → классификация → уведомление.
    Семафор ограничивает количество одновременных HTTP-запросов к API.

    При ``initial_sync=True`` уведомления подавляются — кэш только заполняется.
    """
    # Jitter вне семафора — распределяем старты запросов во времени,
    # не занимая слоты семафора ожиданием
    await asyncio.sleep(random.uniform(1.0, 3.0))

    # Извлекаем данные врача
    if isinstance(d_info, dict):
        d_name = d_info.get("name", _("doctor-fallback-name"))
        d_spec = d_info.get("specialty", "")
        clinic_id = d_info.get(
            "clinic_id",
            p_info.get("clinic_id", settings.DEFAULT_CLINIC_ID),
        )
    else:
        d_name = d_info
        d_spec = ""
        clinic_id = p_info.get("clinic_id", settings.DEFAULT_CLINIC_ID)

    logger.info(
        "Monitor checking slots: d_id={}, p_id={}, clinic_id={}",
        d_id,
        p_id,
        clinic_id,
    )

    # Только API-запрос под семафором — ограничиваем конкурентность
    async with semaphore:
        slots = await api.check_slots(
            d_id, p_id, clinic_id, limiter=api.limiter_monitor
        )

    logger.info(f"API result for {d_id}: {slots}")

    if slots is None:
        logger.warning(f"API error for {d_id}, {p_id}. Skipping.")
        return

    cache_key = f"{uid}_{p_id}_{d_id}"

    # Защита от ложных пустых ответов (3 подряд) — под локом для потокобезопасности
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
                return
        else:
            empty_counts[cache_key] = 0

    # Atomically read old value and write new value.
    # swap_cache_key использует Redis GETSET — атомарно на уровне Redis.
    new_cache_value = slots if slots else "NONE"
    old_slots_data = await swap_cache_key(cache_key, new_cache_value)

    result = _classify_slot_change(slots, old_slots_data)

    # Логируем изменение в monitoring_log независимо от initial_sync
    if result is not None:
        header, display_slots, notify_type = result

        # Определяем статус для лога
        status_map = {
            "available": "появился",
            "new": "появился",
            "empty": "исчез",
            "decreased": "уменьшился",
        }
        log_status = status_map.get(notify_type, notify_type)

        # Берём первую дату слота (если есть) для slot_date
        slot_date = ""
        if slots:
            slot_date = slots[0].split(",")[0].strip() if "," in slots[0] else slots[0]

        p_label = p_info.get("alias") or p_info.get("fio", _("patient-fallback-name"))
        d_name = (
            d_info.get("name", _("doctor-fallback-name"))
            if isinstance(d_info, dict)
            else str(d_info)
        )
        d_spec = d_info.get("specialty", "") if isinstance(d_info, dict) else ""
        clinic_id = d_info.get("clinic_id", "") if isinstance(d_info, dict) else ""

        # Получаем название клиники
        clinic_name = ""
        if clinic_id:
            try:
                name = await db.get_clinic_name(clinic_id)
                if name:
                    clinic_name = name
            except Exception:
                logger.debug(
                    "Не удалось получить имя клиники clinic_id={} для p_id={}",
                    clinic_id,
                    p_id,
                )

        try:
            await db.add_monitoring_log(
                uid=uid,
                p_id=p_id,
                d_id=d_id,
                doctor_name=d_name,
                patient_name=p_label,
                specialty=d_spec,
                clinic_name=clinic_name,
                slot_date=slot_date,
                status=log_status,
                ts=time.time(),
            )
        except Exception as e:
            logger.debug(f"Не удалось записать лог мониторинга: {e}")
    else:
        return

    # Initial sync: только заполняем кэш, уведомления не отправляем
    if initial_sync:
        logger.info(
            "Initial sync — пропускаем уведомление для {} ({}), кэш заполнен",
            d_id,
            p_id,
        )
        return

    p_label = p_info.get("alias") or p_info.get("fio", _("patient-fallback-name"))
    d_name_display = shorten_fio(d_name)
    d_spec_display = shorten_specialty(d_spec)
    spec_text = f"[{d_spec_display}]\n" if d_spec_display else ""
    has_slots = bool(slots)
    link = _("signup-link-text").format(url=settings.SIGNUP_URL) if has_slots else ""

    if display_slots is None:
        # Номерки исчезли
        msg = format_notification_text(
            p_label,
            d_name_display,
            spec_text,
            header,
            _("slots-disappeared-body"),
        )
    else:
        slot_lines = format_slots(
            display_slots,
            detail_threshold=settings.SLOT_DETAIL_THRESHOLD,
            compact_threshold=settings.SLOT_COMPACT_THRESHOLD,
        )
        msg = format_notification_text(
            p_label,
            d_name_display,
            spec_text,
            header,
            "\n".join(slot_lines),
            link,
        )

    photo_path = get_notify_image_path(notify_type)
    await _send_notification(bot, uid, msg, db, p_id, d_id, photo_path=photo_path)


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
    await _safe_set("monitor_loop_alive", True)
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
            users_data = db.data

            # Очистка empty_counts от ключей, которых больше нет в активном мониторинге
            active_keys = {
                f"{uid}_{p_id}_{d_id}"
                for uid, u_info in users_data.items()
                for p_id, doctors in u_info.get("monitoring", {}).items()
                for d_id in doctors
            }
            async with empty_counts_lock:
                for stale in list(empty_counts.keys()):
                    if stale not in active_keys:
                        del empty_counts[stale]

            for uid, u_info in users_data.items():
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

                    # Собираем корутины проверки всех врачей пациента
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
                            initial_sync=_initial_sync,
                        )
                        doctor_tasks.append(task)

                    # Параллельный запуск проверки всех врачей пациента
                    await asyncio.gather(*doctor_tasks)

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
