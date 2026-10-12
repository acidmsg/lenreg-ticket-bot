"""Хендлеры бота: точка входа (``/start``) и админский отчёт (``/status``).

После среза интерфейса бот отвечает только за уведомления и вход в приложение:
работа с пациентами, мониторингом, фильтрами, записью и экспортом живёт
в Mini App.
"""

import asyncio
import contextlib

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from loguru import logger

from src.api.zdrav_client import ZdravClient
from src.config import settings
from src.database.manager import DatabaseManager
from src.database.types import MonitoringEntry, PatientInfo, UserData
from src.filters.admin import IsAdmin
from src.i18n import _
from src.keyboards.inline import get_app_entry_keyboard
from src.services.doctor_discovery import _get_clinic_type_from_db, fetch_specialties
from src.services.healthcheck import format_status_report
from src.utils.helpers import extract_msg_id, shorten_fio, shorten_specialty

router = Router()

# ── On-demand discovery врачей (когда БД пуста для этой клиники) ──


async def _discover_doctors_on_demand(
    api: ZdravClient,
    db: DatabaseManager,
    clinic_id: str,
    p_id: str,
) -> dict:
    """
    Загружает врачей из API, сохраняет и возвращает словарь.
    Сначала пробует patient_id пользователя (он прикреплён к этой клинике),
    если не сработало — fallback на хардкодных discovery-пациентов.
    """
    try:
        clinic_type = await _get_clinic_type_from_db(db._db, clinic_id)
        patient_id_adult = settings.DISCOVERY_PATIENT_ID_ADULT
        patient_id_child = settings.DISCOVERY_PATIENT_ID_CHILD

        # Приоритет: patient_id пользователя > типовой discovery
        patient_candidates = [p_id]
        if clinic_type == "child":
            patient_candidates.append(patient_id_child)
        elif clinic_type == "all":
            patient_candidates.extend([patient_id_adult, patient_id_child])
        else:
            patient_candidates.append(patient_id_adult)

        all_doctors = []
        tried_patients = set()

        for current_patient_id in patient_candidates:
            if current_patient_id in tried_patients:
                continue
            tried_patients.add(current_patient_id)

            specialties_data = await fetch_specialties(
                api, current_patient_id, clinic_id
            )
            if not specialties_data:
                continue  # пробуем следующего пациента

            for spec_info in specialties_data:
                spec_id = spec_info.specialty_id
                spec_name = spec_info.specialty_name
                doctors = await api.fetch_all_doctors(
                    specialty_id=spec_id,
                    patient_id=current_patient_id,
                    clinic_id=clinic_id,
                )
                if doctors:
                    for doc in doctors:
                        doc["SpesialityName"] = spec_name
                    all_doctors.extend(doctors)
                await asyncio.sleep(0.3)

            # Если нашли хотя бы одного врача — хватит
            if all_doctors:
                break

        if all_doctors:
            await db.merge_doctors(clinic_id, all_doctors)
            logger.info(
                f"On-demand discovery для {clinic_id}: {len(all_doctors)} врачей "
                f"(patient={patient_candidates[0]})"
            )

        return await db.get_doctors_for_clinic(clinic_id)
    except Exception as e:
        logger.error(f"Ошибка on-demand discovery для {clinic_id}: {e}")
        return {}


# ── Единый механизм удаления сообщений из last_messages ─────


async def _delete_cleanup_msg_entry(
    bot: Bot,
    uid: str,
    key: str,
    last_messages: dict,
) -> bool:
    """
    Удаляет одно сообщение из чата и из словаря last_messages.
    Возвращает True, если сообщение было удалено.
    """
    value = last_messages.get(key)
    if value is None:
        return False

    msg_id = extract_msg_id(value)
    if msg_id:
        with contextlib.suppress(Exception):
            await bot.delete_message(uid, msg_id)
    del last_messages[key]
    return True


async def _delete_cleanup_msg_entries(
    bot: Bot,
    uid: str,
    prefix_key: str,
    last_messages: dict,
) -> bool:
    """
    Удаляет все сообщения из чата, чьи ключи начинаются с prefix_key.
    Возвращает True, если хотя бы одно сообщение было удалено.
    """
    changed = False
    for key in list(last_messages.keys()):
        if key.startswith(prefix_key):
            changed |= await _delete_cleanup_msg_entry(bot, uid, key, last_messages)
    return changed


# ── Сводка активного мониторинга ──────────────────────────────


def build_monitoring_summary(
    patients: dict[str, PatientInfo],
    monitoring: dict[str, dict[str, MonitoringEntry]],
) -> str:
    """Формирует текстовую сводку активного мониторинга."""
    if not monitoring:
        return ""

    lines = [_("monitoring-summary-header")]

    for p_id, doctors in monitoring.items():
        raw = patients.get(p_id)
        if raw is None:
            continue
        p_info: PatientInfo = raw
        p_name = p_info.get("alias") or p_info.get("fio", _("patient-fallback-name"))
        lines.append(f"\n👤 {p_name}")

        if not doctors:
            continue

        sorted_docs = sorted(
            doctors.items(),
            key=lambda x: x[1].get("name", "") if isinstance(x[1], dict) else str(x[1]),
        )
        for i, (_d_id, d_info) in enumerate(sorted_docs):
            is_last = i == len(sorted_docs) - 1
            prefix = "  ┗" if is_last else "  ┣"
            if isinstance(d_info, dict):
                d_name = shorten_fio(d_info.get("name", _("doctor-fallback-name")))
                doctor_specialty = shorten_specialty(d_info.get("specialty", ""))
            else:
                d_name = str(d_info)
                doctor_specialty = ""
            spec_part = f" ({doctor_specialty})" if doctor_specialty else ""
            lines.append(f"{prefix} 🧑‍⚕️ {d_name}{spec_part}")

    return "\n".join(lines)


def _build_start_text(user_data: UserData) -> str:
    """Собирает текст ``/start``: приветствие и сводка активного мониторинга."""
    summary = build_monitoring_summary(user_data["patients"], user_data["monitoring"])
    if summary:
        return f"{_('start-greeting')}\n\n{summary}"
    return _("start-greeting")


# ── Хендлеры ──────────────────────────────────────────────────


@router.message(Command("status"), IsAdmin())
async def cmd_status(message: Message, db: DatabaseManager) -> None:
    """Команда /status — отчёт о состоянии бота (только для администраторов)."""
    if not message.from_user:
        return

    report = await format_status_report(db)
    await message.answer(report, parse_mode="Markdown")


@router.message(Command("start"))
async def cmd_start(
    message: Message,
    db: DatabaseManager,
    bot: Bot,
    state: FSMContext | None = None,
) -> None:
    """Команда /start — приветствие, сводка мониторинга и вход в приложение.

    Прерывает незавершённый FSM-сценарий и очищает прежние сообщения бота,
    чтобы чат оставался опрятным. Единственная кнопка — «Открыть в приложении».
    """
    if state is not None:
        await state.clear()

    uid = str(message.from_user.id) if message.from_user else "unknown"
    user_data = await db.get_user_data(uid)

    # Удаляем все предыдущие сообщения бота из чата
    await _delete_cleanup_msg_entries(bot, uid, "", user_data["last_messages"])
    await db.update_user(uid, {"last_messages": {}})

    await message.answer(
        _build_start_text(user_data),
        reply_markup=get_app_entry_keyboard(),
        parse_mode="Markdown",
    )
