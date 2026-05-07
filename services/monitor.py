import shutil
import asyncio
import logging
import json
import os
import random
import aiofiles
from aiogram import Bot
from api.zdrav_client import ZdravClient
from database.manager import DatabaseManager
from config import settings

logger = logging.getLogger(__name__)
cache_lock = asyncio.Lock()

async def _save_cache(data, path):
    try:
        temp_path = path + ".tmp"
        async with cache_lock:
            async with aiofiles.open(temp_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=4))
            os.replace(temp_path, path)
    except Exception as e:
        logger.error(f"Ошибка сохранения кэша: {e}")

async def _send_notification(bot: Bot, uid: str, text: str, db: DatabaseManager, p_id: str, d_id: str):
    try:
        # Для "приклеивания" (удаления старого сообщения) нужно хранить message_id
        last_msg_id = db.get_last_message_id(uid, p_id, d_id)

        if last_msg_id:
            try:
                await bot.delete_message(uid, last_msg_id)
            except Exception:
                pass # Сообщение могло быть удалено или устареть

        new_msg = await bot.send_message(uid, text, parse_mode="Markdown")
        await db.set_last_message_id(uid, p_id, d_id, new_msg.message_id)
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления: {e}")

async def monitor_loop(bot: Bot, api: ZdravClient, db: DatabaseManager):
    logger.info("Цикл мониторинга запущен")

    cache_path = settings.CACHE_PATH
    empty_counts = {}

    while True:
        try:
            last_seen_cache = {}
            if os.path.exists(cache_path):
                try:
                    async with cache_lock:
                        async with aiofiles.open(cache_path, 'r', encoding='utf-8') as f:
                            content = await f.read()
                            last_seen_cache = json.loads(content)
                except Exception as e:
                    logger.error(f"Ошибка чтения кэша: {e}")
                    pass

            users_data = db.data.copy()

            for uid, u_info in users_data.items():
                monitoring = u_info.get("monitoring", {})
                for p_id, doctors in monitoring.items():
                    for d_id, d_info in doctors.items():
                        p_info = u_info["patients"].get(p_id, {})
                        if isinstance(d_info, dict):
                            d_name = d_info.get("name", "Врач")
                            d_spec = d_info.get("specialty", "")
                            clinic_id = d_info.get("clinic_id", p_info.get("clinic_id", "272"))
                        else:
                            d_name = d_info
                            d_spec = ""
                            clinic_id = p_info.get("clinic_id", "272")
                        logger.info(f"Monitor checking slots: d_id={d_id}, p_id={p_id}, clinic_id={clinic_id}")


                        await asyncio.sleep(random.uniform(1.0, 3.0))

                        slots = await api.check_slots(d_id, p_id, clinic_id)
                        logger.info(f"API result for {d_id}: {slots}")

                        if slots is None:
                            logger.warning(f"API error for {d_id}, {p_id}. Skipping.")
                            continue

                        cache_key = f"{uid}_{p_id}_{d_id}"
                        old_slots_data = last_seen_cache.get(cache_key)

                        if not slots:
                            empty_counts[cache_key] = empty_counts.get(cache_key, 0) + 1
                            if empty_counts[cache_key] < 3:
                                logger.info(f"Empty slots for {d_id}, {p_id}. Retry {empty_counts[cache_key]}/3")
                                continue

                            logger.info(f"No slots found for {d_id}, {p_id}. Cache: {old_slots_data}")
                            if old_slots_data != "NONE":
                                last_seen_cache[cache_key] = "NONE"
                                await _save_cache(last_seen_cache, cache_path)

                                p_label = p_info.get("alias") or p_info.get("fio", "Пациент")
                                msg = f"📭 **Номерков в данный момент нет**\n🧑‍⚕️ {d_name}\n👤 {p_label}\n\nМы уведомим вас, когда они появятся."
                                await _send_notification(bot, uid, msg, db, p_id, d_id)
                            # В случае, если old_slots_data был None, это означает, что запись только что добавлена в мониторинг
                            # и первое уведомление уже отправлено в handlers/common.py.
                            # Поэтому здесь не нужно дублировать сообщение об отсутствии номерков.
                            # Однако, кэш нужно обновить, чтобы в будущем отслеживать изменения.
                            elif old_slots_data is None:
                                # Если это первое обнаружение, то состояние уже должно быть
                                # синхронизировано через handlers/common.py.
                                # Просто обновляем кэш, чтобы отслеживать дальнейшие изменения.
                                # При этом `slots` пуст, поэтому кэш будет "NONE".
                                last_seen_cache[cache_key] = "NONE"
                                await _save_cache(last_seen_cache, cache_path)
                            continue

                        # Логика для случая, когда номерки ПОЯВИЛИСЬ или ИЗМЕНИЛИСЬ
                        # Если раньше не было номерков (NONE) или это первое обнаружение (None)
                        # (Второе условие `old_slots_data is None` нужно, если `handlers/common.py` не смог записать начальное состояние в кэш)
                        empty_counts[cache_key] = 0
                        if old_slots_data == "NONE" or old_slots_data is None:
                            header = "🔔 **Появились свободные номерки!**"
                            display_slots = slots
                        else: # Если номерки были и до этого, проверяем на изменения
                            new_slots = [s for s in slots if s not in (old_slots_data if isinstance(old_slots_data, list) else [])]
                            if not new_slots and len(slots) < len(old_slots_data if isinstance(old_slots_data, list) else []):
                                header = "⚠️ **Количество номерков уменьшилось**"
                                display_slots = slots
                            elif new_slots:
                                header = "🔔 **Появились НОВЫЕ номерки!**"
                                display_slots = []
                                for s in slots:
                                    if s in new_slots:
                                        display_slots.append(f"✨ [NEW] {s}")
                                    else:
                                        display_slots.append(s)
                            else: # Если номерки были и до этого, проверяем на изменения
                                old_slots_count = len(old_slots_data) if isinstance(old_slots_data, list) else 0
                                new_slots_count = len(slots)
                                # Проверяем гибридное пороговое значение
                                should_notify_decrease = False
                                if new_slots_count < old_slots_count:
                                    # Абсолютное уменьшение
                                    if new_slots_count < settings.SLOT_THRESHOLD_ABSOLUTE:
                                        should_notify_decrease = True
                                    # Процентное уменьшение (избегаем деления на ноль)
                                    elif old_slots_count > 0:
                                        percentage_decrease = (old_slots_count - new_slots_count) / old_slots_count
                                        if percentage_decrease >= settings.SLOT_THRESHOLD_PERCENTAGE:
                                            should_notify_decrease = True

                                if should_notify_decrease:
                                    header = f"⚠️ **Количество номерков уменьшилось до {new_slots_count} (было {old_slots_count})**"
                                    display_slots = slots
                                else:
                                    continue

                        if old_slots_data != slots:
                            last_seen_cache[cache_key] = slots
                            await _save_cache(last_seen_cache, cache_path)


                        p_label = p_info.get("alias") or p_info.get("fio", "Пациент")
                        spec_text = f"[{d_spec}]\n" if d_spec else ""
                        has_slots = bool(slots)
                        # Ссылка на запись только при наличии номерков.
                        link = f"\n\n🔗 [Записаться](https://zdrav.lenreg.ru/signup/free/)" if has_slots else ""
                        msg = f"{spec_text}🧑‍⚕️{d_name}:\n👤 {p_label}\n{header}\n\n" + "\n".join(display_slots) + link







                        await _send_notification(bot, uid, msg, db, p_id, d_id)

            jitter = random.uniform(42, 85)
            await asyncio.sleep(jitter)

        except Exception as e:
            logger.error(f"Ошибка в цикле мониторинга: {e}", exc_info=True)
            await asyncio.sleep(60)
