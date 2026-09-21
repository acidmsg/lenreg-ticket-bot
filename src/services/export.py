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
    """Собирает общие данные для экспорта: patients, monitoring, clinic_names.

    Returns:
        (uid, patients, monitoring, clinic_names)
    Raises:
        ValueError: Если у пользователя нет данных для экспорта.
    """
    uid = str(user_id)
    user_data = await db_manager.get_user_data(uid)
    patients = user_data.get("patients", {})
    monitoring = user_data.get("monitoring", {})

    if not patients and not monitoring:
        raise ValueError(_("export-no-data-error"))

    clinic_names = await db_manager.get_all_clinic_names()
    return uid, patients, monitoring, clinic_names


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
    uid, patients, monitoring, clinic_names = await _collect_export_data(
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

    # Текущая конфигурация мониторинга (пациенты и врачи)
    now_str = _format_timestamp(time.time())
    rows_written = 0

    for p_id, doctors in monitoring.items():
        raw_p = patients.get(p_id)
        if raw_p is None:
            continue
        p_info: PatientInfo = raw_p
        p_name = p_info.get("alias") or p_info.get("fio", _("patient-fallback-name"))

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
    uid, patients, monitoring, clinic_names = await _collect_export_data(
        db_manager, user_id
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


def _cyrillic_font_paths() -> list[str]:
    """Возвращает кандидатов на шрифт с поддержкой кириллицы.

    В рантайм-образе может не быть системных шрифтов, тогда выручает
    ``DejaVuSansMono.ttf`` из пакета ``python-barcode`` (он стоит всегда).
    """
    import importlib.util
    import os

    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    ]
    spec = importlib.util.find_spec("barcode")
    if spec is not None and spec.origin:
        paths.append(
            os.path.join(os.path.dirname(spec.origin), "fonts", "DejaVuSansMono.ttf")
        )
    return paths


def _load_card_font(size: int) -> Any:
    """Загружает шрифт с кириллицей для PNG-карточки записи.

    Без него Pillow уходит на ``load_default()`` — растровый шрифт без
    кириллицы, из-за чего вместо букв получались прямоугольники.

    Args:
        size: Размер шрифта в пунктах.

    Returns:
        Объект шрифта Pillow.
    """
    from PIL import ImageFont

    for path in _cyrillic_font_paths():
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    logger.warning("Экспорт PNG: шрифт с кириллицей не найден, текст будет нечитаем")
    return ImageFont.load_default()


def _pdf_font_name() -> str:
    """Регистрирует в reportlab шрифт с кириллицей и отдаёт его имя.

    Стандартная ``Helvetica`` кириллицу не содержит — вместо букв выходили
    прямоугольники. Если TTF найти не удалось, остаётся ``Helvetica``.
    """
    import os

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for path in _cyrillic_font_paths():
        if not os.path.exists(path):
            continue
        try:
            pdfmetrics.registerFont(TTFont("BookingFont", path))
            return "BookingFont"
        except Exception:
            continue
    return "Helvetica"


def _wrap_card_line(draw: Any, line: str, font: Any, max_width: float) -> list[str]:
    """Переносит строку карточки по словам под ширину изображения.

    Args:
        draw: Объект ``ImageDraw`` для измерения текста.
        line: Исходная строка карточки.
        font: Шрифт, которым будет нарисован текст.
        max_width: Доступная ширина текста в пикселях.

    Returns:
        Список строк, каждая из которых влезает в ``max_width``.
    """
    if draw.textlength(line, font=font) <= max_width:
        return [line]

    result: list[str] = []
    current = ""
    for word in line.split(" "):
        candidate = f"{current} {word}" if current else word
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
            continue
        # Слово не влезает вместе с текущей строкой — начинаем новую.
        if current:
            result.append(current)
        # Слово шире строки целиком (например, разделитель из «=») — подрезаем.
        while word and draw.textlength(word, font=font) > max_width:
            word = word[:-1]
        current = word
    if current:
        result.append(current)
    return result


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
    from PIL import Image, ImageDraw

    card_text = _format_booking_card_text(booking)

    # Параметры изображения
    font_size = 16
    line_height = 22
    padding_x = 24
    padding_y = 20
    width = 480
    max_text_width = width - padding_x * 2

    # Шрифт нужен до переноса строк: им же измеряется ширина текста.
    font = _load_card_font(font_size)
    measurer = ImageDraw.Draw(Image.new("RGB", (width, line_height)))

    # Переносим длинные строки: фиксированная ширина карточки обрезала
    # «Клиника: …» с полным названием.
    lines: list[str] = []
    for raw_line in card_text.split("\n"):
        lines.extend(_wrap_card_line(measurer, raw_line, font, max_text_width))

    height = padding_y * 2 + line_height * len(lines) + 20

    # Создаём изображение (белый фон)
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

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


def _build_ticket_payload(booking: BookingEntry) -> str:
    """Номер талона для штрих-кода: appointment_id, иначе booking_id."""
    appointment_id = booking.get("appointment_id", "")
    if appointment_id:
        return appointment_id
    return booking.get("booking_id", "")


def export_booking_barcode_png(booking: BookingEntry) -> bytes:
    """Генерирует PNG со штрих-кодом талона (Code 128).

    Args:
        booking: Данные записи (BookingEntry TypedDict).

    Returns:
        PNG-изображение со штрих-кодом в виде байтов.

    Raises:
        ImportError: Если python-barcode не установлен.
    """
    import barcode
    from barcode.writer import ImageWriter

    payload = _build_ticket_payload(booking)
    ticket = barcode.get("code128", payload, writer=ImageWriter())

    buffer = io.BytesIO()
    ticket.write(
        buffer,
        options={
            "module_width": 0.3,
            "module_height": 15.0,
            "quiet_zone": 2.0,
            "write_text": False,
            "dpi": 300,
            "background": "white",
            "foreground": "black",
        },
    )
    return buffer.getvalue()


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

    c.setFont(_pdf_font_name(), font_size)
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


#: Соответствие формата экспорта его media type и расширению файла.
EXPORT_MEDIA_TYPES: dict[str, tuple[str, str]] = {
    "png": ("image/png", "png"),
    "pdf": ("application/pdf", "pdf"),
    "ics": ("text/calendar", "ics"),
}


class ExportUnavailableError(Exception):
    """Формат корректен, но серверная зависимость недоступна (нет Pillow).

    Отделено от ``ValueError`` (неверный формат): вызывающие эндпоинты обязаны
    отвечать 501, а не 400 — такова прежняя контрактная семантика.
    """


def render_export(booking: BookingEntry, fmt: str) -> tuple[bytes, str, str]:
    """Готовит файл экспорта записи в запрошенном формате.

    Единая точка входа для отдачи файла: публичный маршрут
    ``/api/export/bookings/{id}``, который открывается по короткоживущей
    подписанной ссылке (её выдаёт ``/api/user/bookings/{id}/export-link``).

    Args:
        booking: Запись из БД.
        fmt: Формат файла — ``png``, ``pdf`` или ``ics``.

    Returns:
        Кортеж ``(содержимое, media_type, расширение)``.

    Raises:
        ValueError: Неизвестный формат.
        ExportUnavailableError: Формат поддержан, но нет Pillow (нужен ответ 501).
    """
    if fmt not in EXPORT_MEDIA_TYPES:
        raise ValueError("Неверный формат. Допустимые: png, pdf, ics.")
    if fmt == "png":
        try:
            content = export_booking_png(booking)
        except ImportError as exc:
            raise ExportUnavailableError(
                "Экспорт в PNG недоступен: Pillow не установлен."
            ) from exc
    elif fmt == "pdf":
        content = export_booking_pdf(booking)
    else:
        content = export_booking_ics(booking)
    media_type, ext = EXPORT_MEDIA_TYPES[fmt]
    return content, media_type, ext
