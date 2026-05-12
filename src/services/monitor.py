import asyncio
import logging
import random

from aiogram import Bot

from src.api.zdrav_client import ZdravClient
from src.config import settings
from src.database.manager import DatabaseManager
from src.services.healthcheck import _safe_set
from src.utils.cache import swap_cache_key
from src.utils.helpers import shorten_fio, shorten_specialty

logger = logging.getLogger(__name__)


async def _send_notification(
    bot: Bot, uid: str, text: str, db: DatabaseManager, p_id: str, d_id: str
):
    try:
        # Для "приклеивания" (удаления старого сообщения) нужно хранить message_id
        last_msg_id = await db.get_last_message_id(uid, p_id, d_id)

        if last_msg_id:
            try:
                await bot.delete_message(uid, last_msg_id)
            except Exception:
                pass  # Сообщение могло быть удалено или устареть

        new_msg = await bot.send_message(uid, text, parse_mode="Markdown")
        await db.set_last_message_id(uid, p_id, d_id, new_msg.message_id)
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления: {e}")


def _classify_slot_change(slots, old_slots_data):
    """Определяет тип изменения слотов и возвращает (header, display_slots) или None если уведомлять не нужно."""
    if not slots:
        # Номерки исчезли
        if old_slots_data == "NONE":
            return None  # Уже было пусто, не дублируем
        if old_slots_data is None:
            # Первое обнаружение -- состояние синхронизировано через handlers/common.py
            return None
        header = "**Номерков в данный момент нет** 🤷‍♂️"
        return header, None

    # Есть слоты
    if old_slots_data == "NONE" or old_slots_data is None:
        return "🎉 **Появились свободные номерки!**", slots

    # Слоты были и раньше -- проверяем изменения
    old_list = old_slots_data if isinstance(old_slots_data, list) else []
    new_slots = [s for s in slots if s not in old_list]

    if new_slots:
        display_slots = []
        for s in slots:
            if s in new_slots:
                display_slots.append(f"[NEW] {s}")
            else:
                display_slots.append(s)
        return "🎉 **Появились НОВЫЕ номерки!**", display_slots

    # Проверяем уменьшение
    old_count = len(old_list)
    new_count = len(slots)

    if new_count < old_count:
        should_notify = False
        if new_count < settings.SLOT_THRESHOLD_ABSOLUTE:
            should_notify = True
        elif old_count > 0:
            percentage_decrease = (old_count - new_count) / old_count
            if percentage_decrease >= settings.SLOT_THRESHOLD_PERCENTAGE:
                should_notify = True

        if should_notify:
            header = f"⚠️ **Количество номерков уменьшилось до {new_count} (было {old_count})**"
            return header, slots

    return None  # Нет значимых изменений


async def monitor_loop(bot: Bot, api: ZdravClient, db: DatabaseManager):
    await _safe_set("monitor_loop_alive", True)
    logger.info("Цикл мониторинга запущен")

    empty_counts: dict[str, int] = {}

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
            for stale in list(empty_counts.keys()):
                if stale not in active_keys:
                    del empty_counts[stale]

            for uid, u_info in users_data.items():
                monitoring = u_info.get("monitoring", {})
                for p_id, doctors in monitoring.items():
                    for d_id, d_info in doctors.items():
                        p_info = u_info["patients"].get(p_id, {})
                        if isinstance(d_info, dict):
                            d_name = d_info.get("name", "Врач")
                            d_spec = d_info.get("specialty", "")
                            clinic_id = d_info.get(
                                "clinic_id",
                                p_info.get("clinic_id", settings.DEFAULT_CLINIC_ID),
                            )
                        else:
                            d_name = d_info
                            d_spec = ""
                            clinic_id = p_info.get(
                                "clinic_id", settings.DEFAULT_CLINIC_ID
                            )
                        logger.info(
                            f"Monitor checking slots: d_id={d_id}, p_id={p_id}, clinic_id={clinic_id}"
                        )

                        await asyncio.sleep(random.uniform(1.0, 3.0))

                        slots = await api.check_slots(
                            d_id, p_id, clinic_id, limiter=api.limiter_monitor
                        )
                        logger.info(f"API result for {d_id}: {slots}")

                        if slots is None:
                            logger.warning(f"API error for {d_id}, {p_id}. Skipping.")
                            continue

                        cache_key = f"{uid}_{p_id}_{d_id}"

                        # Защита от ложных пустых ответов (3 подряд)
                        if not slots:
                            empty_counts[cache_key] = empty_counts.get(cache_key, 0) + 1
                            if empty_counts[cache_key] < 3:
                                logger.info(
                                    f"Empty slots for {d_id}, {p_id}. Retry {empty_counts[cache_key]}/3"
                                )
                                continue
                        else:
                            empty_counts[cache_key] = 0

                        # Atomically read old value and write new value under a single
                        # lock acquisition.  This closes the TOCTOU window where a
                        # handler's update_cache_key / delete_cache_key could slip in
                        # between a separate read and write.
                        new_cache_value = slots if slots else "NONE"
                        old_slots_data = await swap_cache_key(
                            cache_key, new_cache_value
                        )

                        result = _classify_slot_change(slots, old_slots_data)

                        if result is None:
                            continue

                        header, display_slots = result

                        p_label = p_info.get("alias") or p_info.get("fio", "Пациент")
                        d_name_display = shorten_fio(d_name)
                        d_spec_display = shorten_specialty(d_spec)
                        spec_text = f"[{d_spec_display}]\n" if d_spec_display else ""
                        has_slots = bool(slots)
                        link = (
                            "\n\n🔗 [Записаться](https://zdrav.lenreg.ru/signup/free/)"
                            if has_slots
                            else ""
                        )

                        if display_slots is None:
                            # Номерки исчезли
                            msg = f"{spec_text}🧑‍⚕️ {d_name_display}\n👤 {p_label}\n{header}\n\nМы уведомим вас, когда появятся."
                        else:
                            msg = (
                                f"{spec_text}🧑‍⚕️ {d_name_display}\n👤 {p_label}\n{header}\n\n"
                                + "\n".join(display_slots)
                                + link
                            )

                        await _send_notification(bot, uid, msg, db, p_id, d_id)

            jitter = random.uniform(42, 85)
            await asyncio.sleep(jitter)

        except asyncio.CancelledError:
            logger.info("Цикл мониторинга остановлен (cancelled)")
            break
        except Exception as e:
            logger.error(f"Ошибка в цикле мониторинга: {e}", exc_info=True)
            await asyncio.sleep(60)
