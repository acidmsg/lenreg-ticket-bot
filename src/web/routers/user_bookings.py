"""
Записи Mini App API (``/api/user/book``, ``/api/user/bookings``).

Модуль описывает пути без префикса: префикс ``/api/user`` добавляет
агрегатор :mod:`src.web.routers.user_api`. Оркестрация бронирования вынесена
в :mod:`src.services.booking`; здесь остаются идемпотентность (``Idempotency-Key``),
маппинг доменного исхода в HTTP-ответ и уведомление Telegram.
"""

import datetime
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field, field_validator

from src.config import settings
from src.database.types import BookingEntry
from src.services.booking import BookingCommand, book
from src.utils.helpers import shorten_specialty
from src.web.routers.user_common import _get_api, _get_db, _get_telegram_id

router = APIRouter()

#: Коды ошибок ответа POST /api/user/book — синхронно со схемой
#: BookErrorResponse в specs/openapi.yaml.
BOOK_ERROR_CODES: frozenset[str] = frozenset(
    {
        "slot_taken",
        "busy",
        "patient_not_found",
        "idempotency_conflict",
        "api_unavailable",
        "api_timeout",
        "forbidden",
        "unknown",
    }
)

#: Исходы бронирования, ответ на которые сохраняется под ``Idempotency-Key``.
_IDEMPOTENT_STATUSES: frozenset[str] = frozenset(
    {"confirmed", "slot_taken", "forbidden"}
)


class BookRequest(BaseModel):
    """Тело запроса на бронирование талона (POST /api/user/book)."""

    clinic_id: str = Field(..., description="ID клиники")
    patient_id: str = Field(..., description="ID пациента")
    doctor_id: str = Field(
        ..., description="ID врача, выбранного пользователем (d_id из monitoring_id)"
    )
    appointment_id: str = Field(
        ..., description="ID слота (appointment_id из check_slots)"
    )
    slot_date: str = Field(
        ..., description="Дата выкупаемого слота в формате ГГГГ-ММ-ДД"
    )
    slot_time: str = Field(
        ...,
        pattern=r"^\d{2}:\d{2}$",
        description="Время выкупаемого слота в формате ЧЧ:ММ",
    )
    history_id: str = Field(default="", description="ID истории (опционально)")
    referral_id: str = Field(default="", description="ID направления (опционально)")

    @field_validator("slot_date")
    @classmethod
    def validate_slot_date(cls, value: str) -> str:
        """Проверяет соответствие даты слота формату ``ГГГГ-ММ-ДД``."""
        try:
            datetime.date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("Дата слота должна быть в формате ГГГГ-ММ-ДД.") from exc
        return value


@router.post("/book", response_model=None)
async def book_appointment(
    request: Request,
    body: BookRequest,
) -> dict[str, Any] | JSONResponse:
    """Забронировать талон (запись к врачу).

    Выполняет бронирование через API zdrav.lenreg.ru и сохраняет
    запись в таблицу ``bookings``.

    Тело запроса: ``BookRequest`` с полями clinic_id, patient_id, doctor_id,
    appointment_id, slot_date, slot_time, history_id (опционально),
    referral_id (опционально). Запись мониторинга для пары «пациент + врач» не
    требуется: реквизиты берутся из мониторинга (если запись есть), иначе — из
    справочника клиники по паре ``clinic_id`` + ``doctor_id``. Явные проверки:
    ``patient_id`` принадлежит текущему пользователю (иначе 403, IDOR) и пара
    ``clinic_id`` + ``doctor_id`` известна справочнику (иначе 400).
    """
    from src.web import idempotency

    db = _get_db(request)
    api = _get_api(request)
    telegram_id = _get_telegram_id(request)

    # Идемпотентность: повтор с тем же Idempotency-Key отдаёт сохранённый
    # терминальный ответ; тот же ключ с другими параметрами — 422.
    idempotency_key = request.headers.get("Idempotency-Key")
    idempotency_hash: str | None = None
    if idempotency_key:
        idempotency_hash = idempotency.params_hash(body.model_dump())
        stored = idempotency.get(telegram_id, idempotency_key)
        if stored is not None:
            stored_hash, stored_status, stored_body = stored
            if stored_hash != idempotency_hash:
                return _idempotency_conflict()
            return JSONResponse(status_code=stored_status, content=stored_body)

    outcome = await book(
        BookingCommand(
            telegram_id=telegram_id,
            clinic_id=body.clinic_id,
            patient_id=body.patient_id,
            doctor_id=body.doctor_id,
            appointment_id=body.appointment_id,
            slot_date=body.slot_date,
            slot_time=body.slot_time,
            history_id=body.history_id,
            referral_id=body.referral_id,
        ),
        api,
        db,
    )

    if outcome.status in _IDEMPOTENT_STATUSES and idempotency_key and idempotency_hash:
        idempotency.put(
            telegram_id,
            idempotency_key,
            idempotency_hash,
            outcome.http_status,
            outcome.body,
        )

    if outcome.status == "confirmed":
        await _notify_confirmed(telegram_id, outcome.body)
        return outcome.body
    if outcome.status == "already_booked":
        return outcome.body

    headers = {"Retry-After": outcome.retry_after} if outcome.retry_after else None
    return JSONResponse(
        status_code=outcome.http_status, content=outcome.body, headers=headers
    )


def _idempotency_conflict() -> JSONResponse:
    """Ответ 422 на повтор ключа с другими параметрами."""
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": "idempotency_conflict",
            "detail": "Idempotency-Key уже использован с другими параметрами.",
        },
    )


async def _notify_confirmed(telegram_id: str, body: dict[str, Any]) -> None:
    """Независимый от WebView канал: бот подтверждает запись сообщением."""
    from src.web import notify

    await notify.send_booking_confirmed(
        telegram_id,
        {
            "doctor_name": body["doctor_name"],
            "specialty": body["specialty"],
            "clinic_name": body["clinic_name"],
            "date": body["date"],
            "time": body["time"],
            "patient_name": body["patient_name"],
        },
    )


def _serialize_booking(booking: BookingEntry) -> dict[str, Any]:
    """Преобразует BookingEntry в JSON-сериализуемый словарь."""
    created_at_iso = ""
    ts = booking.get("created_at", 0.0)
    if ts:
        from datetime import UTC, datetime

        dt = datetime.fromtimestamp(float(ts), tz=UTC)
        created_at_iso = dt.isoformat()
    return {
        "booking_id": booking["booking_id"],
        "doctor_name": booking["doctor_name"],
        "specialty": booking["specialty"],
        # Короткое название специальности для заголовка события в календаре
        # («Офтальмология» → «Офтальмолог»). Источник — словарь проекта.
        "specialty_short": shorten_specialty(booking["specialty"]),
        "clinic_name": booking["clinic_name"],
        "date": booking["slot_date"],
        "time": booking["slot_time"],
        "patient_name": booking["patient_name"],
        "created_at": created_at_iso,
        "is_archived": bool(booking.get("is_archived", 0)),
        "status": booking.get("status", "confirmed"),
    }


@router.get("/bookings")
async def get_bookings(request: Request) -> dict[str, Any]:
    """Возвращает активные записи пользователя (T-11).

    Перед выдачей выполняет автоархивацию прошедших записей.
    """
    db = _get_db(request)
    telegram_id = _get_telegram_id(request)

    # Автоархивация прошедших записей
    try:
        await db.archive_past_bookings(telegram_id)
    except Exception:
        logger.exception("Ошибка автоархивации для uid={}", telegram_id)

    # Получаем активные записи
    bookings = await db.get_user_bookings(telegram_id)
    serialized = [_serialize_booking(b) for b in bookings]
    return {"bookings": serialized}


@router.get("/bookings/archive")
async def get_bookings_archive(request: Request) -> dict[str, Any]:
    """Возвращает архивные записи пользователя (T-12)."""
    db = _get_db(request)
    telegram_id = _get_telegram_id(request)

    bookings = await db.get_user_bookings_archive(telegram_id)
    serialized = [_serialize_booking(b) for b in bookings]
    return {"bookings": serialized}


@router.get("/bookings/{booking_id}/export-link")
async def export_booking_link(
    request: Request,
    booking_id: str,
    format: str = Query("png", description="Формат экспорта: png, pdf, ics"),
) -> Any:
    """Возвращает подписанную ссылку на скачивание файла экспорта.

    Скачивание через ``fetch`` + blob в WebView Telegram не срабатывает, а
    обычная ссылка не может приложить заголовок initData: путь ``/api/user/*``
    закрыт middleware. Поэтому клиент берёт короткоживущую подписанную ссылку
    и открывает её (``Telegram.WebApp.downloadFile`` / ``openLink``), а файл
    отдаёт публичный ``/api/export/bookings/{id}`` по подписи.

    Args:
        booking_id: Составной ID записи.
        format: ``png``, ``pdf`` или ``ics``.

    Returns:
        ``{"url": …, "file_name": …}`` либо JSONResponse с ошибкой.
    """

    from src.web.export_token import EXPORT_FORMATS, sign_export

    db = _get_db(request)
    telegram_id = _get_telegram_id(request)

    booking = await db.get_booking_by_id(booking_id)
    if booking is None:
        return JSONResponse(
            status_code=404,
            content={"detail": "Запись не найдена."},
        )

    if booking["uid"] != telegram_id:
        return JSONResponse(
            status_code=403,
            content={"detail": "Доступ запрещён."},
        )

    fmt = format.lower().strip()
    if fmt not in EXPORT_FORMATS:
        return JSONResponse(
            status_code=400,
            content={"detail": "Неверный формат. Допустимые: png, pdf, ics."},
        )

    query = sign_export(booking_id, fmt, telegram_id, bot_token=settings.BOT_TOKEN)
    base = str(request.base_url).rstrip("/")
    return {
        "url": f"{base}/api/export/bookings/{booking_id}?{query}",
        "file_name": f"booking_{booking_id}.{fmt}",
    }
