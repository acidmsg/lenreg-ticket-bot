"""Публичное скачивание файлов экспорта записи по подписанной ссылке.

Путь ``/api/export/*`` намеренно лежит вне ``/api/user/*``: middleware проверки
initData его не касается. Авторизация здесь — подпись и срок годности ссылки,
которую выдаёт ``GET /api/user/bookings/{id}/export-link``.

Зачем так: скачивание через ``fetch`` + blob в WebView Telegram не срабатывает,
а к обычной ссылке нельзя приложить заголовок ``X-Telegram-InitData``. Ссылка
с подписью позволяет отдать файл обычным переходом
(``Telegram.WebApp.downloadFile`` / ``openLink``).
"""

from typing import cast

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response
from loguru import logger

from src.config import settings
from src.database.manager import DatabaseManager
from src.services.export import ExportUnavailableError, render_export
from src.web.export_token import verify_export

router = APIRouter(prefix="/api/export", tags=["Mini App (экспорт по ссылке)"])


@router.get("/bookings/{booking_id}")
async def download_booking_export(
    request: Request,
    booking_id: str,
    format: str = Query(..., description="Формат файла: png, pdf, ics"),
    uid: str = Query(..., description="Telegram ID владельца записи"),
    exp: int = Query(..., description="Срок действия ссылки (unix-время)"),
    sig: str = Query(..., description="Подпись ссылки"),
) -> Response:
    """Отдаёт файл экспорта записи по подписанной ссылке.

    Args:
        booking_id: Составной ID записи.
        format: ``png``, ``pdf`` или ``ics``.
        uid: Telegram ID владельца из подписанной ссылки.
        exp: Момент истечения ссылки.
        sig: Подпись ссылки.

    Returns:
        Response с файлом либо JSONResponse с ошибкой.
    """

    fmt = format.lower().strip()
    if not verify_export(
        booking_id, fmt, str(uid), exp, sig, bot_token=settings.BOT_TOKEN
    ):
        logger.warning(
            "Экспорт по ссылке: подпись недействительна или истекла | booking={}",
            booking_id,
        )
        return JSONResponse(
            status_code=403,
            content={"detail": "Ссылка недействительна или истекла."},
        )

    db = cast(DatabaseManager, request.app.state.db)
    booking = await db.get_booking_by_id(booking_id)
    if booking is None:
        return JSONResponse(
            status_code=404,
            content={"detail": "Запись не найдена."},
        )

    if str(booking["uid"]) != str(uid):
        return JSONResponse(
            status_code=403,
            content={"detail": "Доступ запрещён."},
        )

    try:
        content, media_type, ext = render_export(booking, fmt)
    except ExportUnavailableError as exc:
        return JSONResponse(status_code=501, content={"detail": str(exc)})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="booking_{booking_id}.{ext}"'
            ),
        },
    )
