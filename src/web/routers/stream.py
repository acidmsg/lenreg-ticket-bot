"""SSE-поток состояния дашборда (DASH-1).

Отдаёт события ``text/event-stream`` с компактным снапшотом сводки, чтобы
страница обновлялась без перезагрузки: счётчики, блок фоновых задач, статус
API и последние алерты.

Эндпоинт защищён обычной сессией дашборда (``SessionAuthMiddleware``):
``EventSource`` отправляет cookie того же origin. Поток завершается сам при
отключении клиента; ошибки сбора снапшота не рвут соединение — клиент получает
событие с признаком ошибки и продолжает жить.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from loguru import logger

from src.config import settings
from src.web.routers._shared import build_live_payload

router = APIRouter()

# Заголовки против буферизации прокси: иначе поток «залипает» и события
# приходят пачкой только при закрытии соединения.
_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


@router.get("/dashboard/stream")
async def dashboard_stream(
    request: Request,
    frames: int | None = Query(
        None,
        ge=1,
        le=1000,
        description=(
            "Ограничить число кадров (диагностика и тесты); по умолчанию — бесконечно"
        ),
    ),
) -> StreamingResponse:
    """Отдаёт поток обновлений сводки (Server-Sent Events).

    Returns:
        ``StreamingResponse`` с кадрами ``data: <json>\\n\\n`` и паузами
        ``DASHBOARD_STREAM_INTERVAL`` секунд.
    """
    interval = max(2, int(settings.DASHBOARD_STREAM_INTERVAL))
    db = request.app.state.db
    prometheus_metrics = request.app.state.prometheus_metrics
    templates = request.app.state.templates

    async def event_stream() -> AsyncIterator[bytes]:
        """Генерирует кадры SSE до отключения клиента или предела ``frames``.

        Первый кадр уходит до любой проверки соединения: ``is_disconnected()``
        читает ``receive()`` и в начале потока может ждать дисконнект, поэтому
        проверка стоит только между кадрами.
        """
        sent = 0
        while True:
            try:
                payload = await build_live_payload(db, prometheus_metrics, templates)
            except Exception as exc:
                logger.warning(f"SSE: не удалось собрать снапшот: {exc}")
                payload = {"ts": int(time.time()), "error": "snapshot_failed"}

            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()
            sent += 1
            if frames is not None and sent >= frames:
                break

            await asyncio.sleep(interval)

            if await request.is_disconnected():
                logger.debug("SSE: клиент отключился, поток завершён")
                break

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
