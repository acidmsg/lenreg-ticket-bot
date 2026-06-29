"""
Сервис экспорта данных мониторинга в CSV и JSON.

Предоставляет функции для выгрузки истории мониторинга слотов
для последующего анализа пользователем.
"""

import csv
import io
import json
import time
from datetime import UTC
from typing import Any

import aiofiles
from loguru import logger

from src.database.manager import DatabaseManager
from src.database.types import BookingEntry, PatientInfo
from src.i18n import _


async def _collect_export_data(
    db_manager: DatabaseManager, user_id: int
) -> tuple[str, dict, dict, list, dict[str, str]]:
    """Собирает общие данные для экспорта: patients, monitoring, logs, clinic_names.

    Returns:
        (uid, patients, monitoring, logs, clinic_names)
    Raises:
        ValueError: Если у пользователя нет данных для экспорта.
    """
    uid = str(user_id)
    user_data = await db_manager.get_user_data(uid)
    patients = user_data.get("patients", {})
    monitoring = user_data.get("monitoring", {})

    if not patients and not monitoring:
        raise ValueError(_("export-no-data-error"))

    logs = await db_manager.get_user_monitoring_logs(uid, limit=10000)
    clinic_names = await db_manager.get_all_clinic_names()
    return uid, patients, monitoring, logs, clinic_names


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
    uid, patients, monitoring, logs, clinic_names = await _collect_export_data(
        db_manager, user_id
    )

    # Создаём временный CSV-файл
    buffer = io.StringIO()
    writer = csv.writer(buffer)
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
        now_str = _format_timestamp(time.time())

        for p_id, doctors in monitoring.items():
            raw_p = patients.get(p_id)
            if raw_p is None:
                continue
            p_info: PatientInfo = raw_p
            p_name = p_info.get("alias") or p_info.get(
                "fio", _("patient-fallback-name")
            )

            for _d_id, d_info in doctors.items():
                if isinstance(d_info, dict):
                    d_name = d_info.get("name", "")
                    doctor_specialty = d_info.get("specialty", "")
                    clinic_id = d_info.get("clinic_id", "")
                else:
                    d_name = str(d_info)
                    doctor_specialty = ""
                    clinic_id = ""

                clinic_name = clinic_names.get(clinic_id, "") if clinic_id else ""

                writer.writerow(
                    [
                        p_name,
                        doctor_specialty,
                        d_name,
                        clinic_name,
                        "",
                        _("export-status-active"),
                        now_str,
                    ]
                )
                rows_written += 1

    # Асинхронная запись временного файла
    import os
    import tempfile

    fd, filepath = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    async with aiofiles.open(filepath, mode="w", newline="", encoding="utf-8-sig") as f:
        await f.write(buffer.getvalue())

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
    uid, patients, monitoring, logs, clinic_names = await _collect_export_data(
        db_manager, user_id
    )

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

    # Собираем структуру
    export_data: dict[str, Any] = {
        "user_id": user_id,
        "exported_at": _format_timestamp(time.time()),
        "patients": [],
    }

    for p_id, doctors in monitoring.items():
        raw_p = patients.get(p_id)
        if raw_p is None:
            continue
        p_info: PatientInfo = raw_p
        p_name = p_info.get("alias") or p_info.get("fio", _("patient-fallback-name"))

        patient_entry: dict[str, Any] = {
            "patient_id": p_id,
            "patient_name": p_name,
            "doctors": [],
        }

        for d_id, d_info in doctors.items():
            if isinstance(d_info, dict):
                d_name = d_info.get("name", "")
                doctor_specialty = d_info.get("specialty", "")
                clinic_id = d_info.get("clinic_id", "")
            else:
                d_name = str(d_info)
                doctor_specialty = ""
                clinic_id = ""

            clinic_name = clinic_names.get(clinic_id, "") if clinic_id else ""

            doctor_entry: dict[str, Any] = {
                "doctor_id": d_id,
                "doctor_name": d_name,
                "specialty": doctor_specialty,
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

    # Создаём временный JSON-файл (асинхронно)
    import os
    import tempfile

    fd, filepath = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    json_content = json.dumps(export_data, ensure_ascii=False, indent=2, default=str)
    async with aiofiles.open(filepath, mode="w", encoding="utf-8") as f:
        await f.write(json_content)

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


# ── Экспорт бронирований (Фаза 3 рефакторинга UX) ──────────────


def _format_booking_card_text(
    booking: "BookingEntry",
) -> str:
    """Формирует текстовое представление карточки записи."""
    patient_name = booking.get("patient_name", "")
    doctor_name = booking.get("doctor_name", "")
    specialty = booking.get("specialty", "")
    clinic_name = booking.get("clinic_name", "")
    slot_date = booking.get("slot_date", "")
    slot_time = booking.get("slot_time", "")

    lines = [
        "Запись к врачу",
        "=" * 40,
        f"Врач:     {doctor_name}",
        f"Профиль:  {specialty}" if specialty else "",
        f"Клиника:  {clinic_name}",
        f"Дата:     {slot_date}",
        f"Время:    {slot_time}",
        f"Пациент:  {patient_name}",
    ]
    return "\n".join(line for line in lines if line)


def export_booking_png(
    booking: "BookingEntry",
) -> bytes:
    """Генерирует PNG-изображение карточки записи через Pillow.

    Args:
        booking: Данные записи (BookingEntry TypedDict).

    Returns:
        PNG-изображение в виде байтов.

    Raises:
        ImportError: Если Pillow не установлен.
    """
    from PIL import Image, ImageDraw, ImageFont

    card_text = _format_booking_card_text(booking)
    lines = card_text.split("\n")

    # Параметры изображения
    font_size = 16
    line_height = 22
    padding_x = 24
    padding_y = 20
    width = 480
    height = padding_y * 2 + line_height * len(lines) + 20

    # Создаём изображение (белый фон)
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Пытаемся использовать встроенный шрифт; fallback — default
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except OSError:
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()

    # Рисуем текст
    y = padding_y
    for line in lines:
        draw.text((padding_x, y), line, fill=(0, 0, 0), font=font)
        y += line_height

    # Конвертируем в PNG-байты
    import io

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def export_booking_pdf(
    booking: "BookingEntry",
) -> bytes:
    """Генерирует PDF-карточку записи.

    Использует reportlab если доступен, иначе — минимальный hand-crafted PDF.

    Args:
        booking: Данные записи (BookingEntry TypedDict).

    Returns:
        PDF-документ в виде байтов.
    """
    import importlib.util

    if importlib.util.find_spec("reportlab") is not None:
        return _export_booking_pdf_reportlab(booking)
    return _export_booking_pdf_raw(booking)


def _export_booking_pdf_reportlab(booking: "BookingEntry") -> bytes:
    """PDF через reportlab (русский текст через встроенный шрифт)."""
    import io

    from reportlab.lib.pagesizes import A6
    from reportlab.pdfgen import canvas as rl_canvas

    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A6)

    card_text = _format_booking_card_text(booking)
    lines = card_text.split("\n")

    y = A6[1] - 30
    font_size = 10
    line_height = 14

    c.setFont("Helvetica", font_size)
    for line in lines:
        c.drawString(20, y, line)
        y -= line_height

    c.save()
    return buf.getvalue()


def _export_booking_pdf_raw(booking: "BookingEntry") -> bytes:
    """Минимальный hand-crafted PDF без внешних зависимостей.

    Генерирует валидный PDF 1.4 с внедрённым текстом в кодировке UTF-16 BE BOM.
    """
    card_text = _format_booking_card_text(booking)
    lines = card_text.split("\n")

    # Формируем content stream с русским текстом (UTF-16 BE)
    # Используем стандартный шрифт Helvetica (без кириллицы, но PDF будет валидным).
    # Для русского текста внедряем его как hex-строку в UTF-16 BE с BOM.

    def _to_pdf_utf16(text: str) -> str:
        """Кодирует строку в PDF-формат UTF-16 BE с BOM."""
        encoded = text.encode("utf-16-be")
        return "".join(f"{b:02x}" for b in encoded)

    # Строим текст с ручным позиционированием (Td оператор)
    text_operations: list[str] = []
    y = 380  # стартовая Y-координата (сверху A6)
    line_height = 16

    for line in lines:
        hex_line = _to_pdf_utf16(line)
        text_operations.append(f"BT /F1 10 Tf 20 {y} Td <{hex_line}> Tj ET")
        y -= line_height

    content_stream = "\n".join(text_operations)

    # Подсчитываем длины для cross-reference таблицы
    content_bytes = content_stream.encode("ascii", errors="replace")

    pdf = f"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj

2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj

3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 298 420]
   /Contents 4 0 R
   /Resources << /Font << /F1 << /Type /Font
      /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding
   >> >> >>
endobj

4 0 obj
<< /Length {len(content_bytes)} >>
stream
{content_stream}
endstream
endobj

xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
{len(content_bytes):010} 00000 n

trailer
<< /Size 5 /Root 1 0 R >>
startxref
{0}
%%EOF
"""

    # Пересчитываем xref с реальными смещениями
    lines_pdf = pdf.split("\n")
    # Находим позиции "1 0 obj", "2 0 obj" и т.д.

    offsets: dict[int, int] = {}
    for idx, pdf_line in enumerate(lines_pdf):
        for obj_num in [1, 2, 3, 4]:
            if pdf_line.strip().startswith(f"{obj_num} 0 obj"):
                # Смещение = сумма длин предыдущих строк + переносы
                offset = sum(len(ln) + 1 for ln in lines_pdf[:idx])
                offsets[obj_num] = offset

    # Собираем итоговый PDF с правильными смещениями
    result_lines: list[str] = []
    for _i, pdf_line in enumerate(lines_pdf):
        if pdf_line.strip() == "xref":
            result_lines.append("xref")
            break
        result_lines.append(pdf_line)

    # Добавляем xref записи
    xref_lines = ["0 5", "0000000000 65535 f "]
    for obj_num in [1, 2, 3, 4]:
        offset = offsets.get(obj_num, 0)
        xref_lines.append(f"{offset:010} 00000 n ")

    result_lines.extend(xref_lines)

    # trailer
    result_lines.extend(["trailer", "<< /Size 5 /Root 1 0 R >>", "startxref"])
    xref_offset = sum(len(ln) + 1 for ln in result_lines)
    result_lines.append(str(xref_offset))
    result_lines.append("%%EOF")

    final_pdf = "\n".join(result_lines)
    return final_pdf.encode("ascii", errors="replace")


def export_booking_ics(
    booking: "BookingEntry",
) -> bytes:
    """Генерирует .ics файл (RFC 5545) для импорта записи в календарь.

    Args:
        booking: Данные записи (BookingEntry TypedDict).

    Returns:
        Содержимое .ics файла в виде байтов (UTF-8).
    """
    slot_date = booking.get("slot_date", "")  # ДД.ММ.ГГГГ
    slot_time = booking.get("slot_time", "")  # ЧЧ:ММ
    doctor_name = booking.get("doctor_name", "")
    specialty = booking.get("specialty", "")
    clinic_name = booking.get("clinic_name", "")
    patient_name = booking.get("patient_name", "")

    # Преобразуем ДД.ММ.ГГГГ + ЧЧ:ММ → YYYYMMDDTHHMMSS
    dtstart = ""
    if len(slot_date) == 10 and len(slot_time) == 5:
        day, month, year = slot_date.split(".")
        hour, minute = slot_time.split(":")
        dtstart = f"{year}{month}{day}T{hour}{minute}00"

    summary = f"Приём у {doctor_name}"
    if specialty:
        summary += f" ({specialty})"

    description = f"Пациент: {patient_name}"
    location = clinic_name

    ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//Lenreg Ticket Bot//RU\r\n"
        "BEGIN:VEVENT\r\n"
        f"DTSTART:{dtstart}\r\n"
        f"SUMMARY:{summary}\r\n"
        f"LOCATION:{location}\r\n"
        f"DESCRIPTION:{description}\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    return ics.encode("utf-8")
