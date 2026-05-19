"""
Сервис экспорта данных мониторинга в CSV и JSON.

Предоставляет функции для выгрузки истории мониторинга слотов
для последующего анализа пользователем.
"""

import csv
import json
import tempfile
import time
from datetime import UTC
from typing import Any

from loguru import logger

from src.database.manager import DatabaseManager
from src.i18n import _


async def export_monitoring_csv(db_manager: DatabaseManager, user_id: int) -> str:
    """
    Экспорт данных мониторинга пользователя в CSV.

    Собирает историю мониторинга из таблицы monitoring_log, а также
    текущую конфигурацию мониторинга (пациенты + врачи).

    Args:
        db_manager: Менеджер базы данных.
        user_id: Telegram ID пользователя.

    Returns:
        Путь к временному CSV-файлу.

    Raises:
        ValueError: Если у пользователя нет данных для экспорта.
    """
    uid = str(user_id)

    # Получаем данные пользователя
    user_data = await db_manager.get_user_data(uid)
    patients = user_data.get("patients", {})
    monitoring = user_data.get("monitoring", {})

    if not patients and not monitoring:
        raise ValueError(_("export-no-data-error"))

    # Получаем логи мониторинга
    logs = await db_manager.get_user_monitoring_logs(uid, limit=10000)
    log_by_key: dict[str, list[dict]] = {}
    for entry in logs:
        key = f"{entry['p_id']}_{entry['d_id']}"
        log_by_key.setdefault(key, []).append(entry)

    # Создаём временный CSV-файл
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=".csv", mode="w", newline="", encoding="utf-8-sig"
    ) as tmp:
        filepath: str = tmp.name
        writer = csv.writer(tmp)
        writer.writerow(
            [
                _("export-csv-header-patient"),
                _("export-csv-header-specialty"),
                _("export-csv-header-doctor"),
                _("export-csv-header-clinic"),
                _("export-csv-header-slot"),
                _("export-csv-header-status"),
                _("export-csv-header-timestamp"),
            ]
        )

        # Сначала пишем логи мониторинга (если есть)
        rows_written = 0
        if logs:
            for entry in logs:
                ts_str = _format_timestamp(entry["ts"])
                writer.writerow(
                    [
                        entry.get("patient_name", ""),
                        entry.get("specialty", ""),
                        entry.get("doctor_name", ""),
                        entry.get("clinic_name", ""),
                        entry.get("slot_date", ""),
                        entry.get("status", ""),
                        ts_str,
                    ]
                )
                rows_written += 1

        # Если логов нет, пишем текущую конфигурацию мониторинга
        if not rows_written:
            clinic_names = await db_manager.get_all_clinic_names()
            now_str = _format_timestamp(time.time())

            for p_id, doctors in monitoring.items():
                p_info = patients.get(p_id, {})
                p_name = p_info.get("alias") or p_info.get(
                    "fio", _("patient-fallback-name")
                )

                for _d_id, d_info in doctors.items():
                    if isinstance(d_info, dict):
                        d_name = d_info.get("name", "")
                        d_spec = d_info.get("specialty", "")
                        clinic_id = d_info.get("clinic_id", "")
                    else:
                        d_name = str(d_info)
                        d_spec = ""
                        clinic_id = ""

                    clinic_name = clinic_names.get(clinic_id, "") if clinic_id else ""

                    writer.writerow(
                        [
                            p_name,
                            d_spec,
                            d_name,
                            clinic_name,
                            "",
                            _("export-status-active"),
                            now_str,
                        ]
                    )
                    rows_written += 1

        logger.info(
            "CSV-экспорт для uid={}: {} строк",
            uid,
            rows_written,
        )

    return filepath


async def export_monitoring_json(db_manager: DatabaseManager, user_id: int) -> str:
    """
    Экспорт данных мониторинга пользователя в JSON.

    Args:
        db_manager: Менеджер базы данных.
        user_id: Telegram ID пользователя.

    Returns:
        Путь к временному JSON-файлу.

    Raises:
        ValueError: Если у пользователя нет данных для экспорта.
    """
    uid = str(user_id)

    # Получаем данные пользователя
    user_data = await db_manager.get_user_data(uid)
    patients = user_data.get("patients", {})
    monitoring = user_data.get("monitoring", {})

    if not patients and not monitoring:
        raise ValueError(_("export-no-data-error"))

    # Получаем логи мониторинга
    logs = await db_manager.get_user_monitoring_logs(uid, limit=10000)

    # Группируем логи по пациенту → врачу
    log_by_patient: dict[str, dict[str, list[dict]]] = {}
    for entry in logs:
        pid = entry["p_id"]
        did = entry["d_id"]
        log_by_patient.setdefault(pid, {}).setdefault(did, []).append(
            {
                "doctor_name": entry.get("doctor_name", ""),
                "specialty": entry.get("specialty", ""),
                "clinic_name": entry.get("clinic_name", ""),
                "slot_date": entry.get("slot_date", ""),
                "status": entry.get("status", ""),
                "timestamp": _format_timestamp(entry["ts"]),
            }
        )

    clinic_names = await db_manager.get_all_clinic_names()

    # Собираем структуру
    export_data: dict[str, Any] = {
        "user_id": user_id,
        "exported_at": _format_timestamp(time.time()),
        "patients": [],
    }

    for p_id, doctors in monitoring.items():
        p_info = patients.get(p_id, {})
        p_name = p_info.get("alias") or p_info.get("fio", _("patient-fallback-name"))

        patient_entry: dict[str, Any] = {
            "patient_id": p_id,
            "patient_name": p_name,
            "doctors": [],
        }

        for d_id, d_info in doctors.items():
            if isinstance(d_info, dict):
                d_name = d_info.get("name", "")
                d_spec = d_info.get("specialty", "")
                clinic_id = d_info.get("clinic_id", "")
            else:
                d_name = str(d_info)
                d_spec = ""
                clinic_id = ""

            clinic_name = clinic_names.get(clinic_id, "") if clinic_id else ""

            doctor_entry: dict[str, Any] = {
                "doctor_id": d_id,
                "doctor_name": d_name,
                "specialty": d_spec,
                "clinic_name": clinic_name,
                "status": _("export-status-active"),
                "history": log_by_patient.get(p_id, {}).get(d_id, []),
            }
            patient_entry["doctors"].append(doctor_entry)

        # Добавляем пациентов, которые есть в логах, но уже не в мониторинге
        if not patient_entry["doctors"] and p_id in log_by_patient:
            for d_id, entries in log_by_patient[p_id].items():
                if entries:
                    first = entries[0]
                    doctor_entry = {
                        "doctor_id": d_id,
                        "doctor_name": first.get("doctor_name", ""),
                        "specialty": first.get("specialty", ""),
                        "clinic_name": first.get("clinic_name", ""),
                        "status": _("export-status-inactive"),
                        "history": entries,
                    }
                    patient_entry["doctors"].append(doctor_entry)

        export_data["patients"].append(patient_entry)

    # Создаём временный JSON-файл
    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".json",
        mode="w",
        encoding="utf-8",
    ) as tmp:
        filepath: str = tmp.name
        json.dump(export_data, tmp, ensure_ascii=False, indent=2, default=str)
        logger.info(
            "JSON-экспорт для uid={}: {} пациентов",
            uid,
            len(export_data["patients"]),
        )

    return filepath


def _format_timestamp(ts: float) -> str:
    """Форматирует timestamp в читаемую дату/время."""
    from datetime import datetime

    dt = datetime.fromtimestamp(ts, tz=UTC)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
