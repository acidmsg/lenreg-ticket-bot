"""
Избранные клиники Mini App API (``/api/user/favorites``).

Модуль описывает пути без префикса: префикс ``/api/user`` добавляет
агрегатор :mod:`src.web.routers.user_api`.
"""

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.web.routers.user_common import _get_db, _get_telegram_id

router = APIRouter()


class FavoriteAddRequest(BaseModel):
    """Тело запроса на добавление клиники в избранное (POST /favorites)."""

    clinic_id: str = Field(..., description="ID клиники в справочнике")


@router.get("/favorites", response_model=None)
async def list_favorites(request: Request) -> dict[str, Any]:
    """Список избранных клиник аккаунта (P4-FAV).

    Привязка — к аккаунту (uid из initData), не к пациенту. Клиники, которых
    больше нет в справочнике, в ответ не попадают.
    """
    db = _get_db(request)
    uid = _get_telegram_id(request)

    clinic_ids = await db.favorites.list_clinic_ids(uid)
    names = await db.clinics.get_all_clinic_names()

    favorites: list[dict[str, Any]] = []
    for clinic_id in clinic_ids:
        name = names.get(clinic_id)
        if name is None:
            continue
        favorites.append({"clinic_id": clinic_id, "name": name, "short_name": name})

    return {"favorites": favorites}


@router.post("/favorites", response_model=None)
async def add_favorite(
    request: Request, body: FavoriteAddRequest
) -> dict[str, Any] | JSONResponse:
    """Добавляет клинику в избранное аккаунта; повторный вызов безвреден."""
    db = _get_db(request)
    uid = _get_telegram_id(request)

    name = await db.clinics.get_clinic_name(body.clinic_id)
    if name is None:
        return JSONResponse(
            status_code=404,
            content={"detail": "Клиника не найдена в справочнике"},
        )

    await db.favorites.add(uid, body.clinic_id)
    return {"status": "ok", "clinic_id": body.clinic_id}


@router.delete("/favorites/{clinic_id}", response_model=None)
async def remove_favorite(request: Request, clinic_id: str) -> dict[str, Any]:
    """Убирает клинику из избранного аккаунта; повторный вызов безвреден."""
    db = _get_db(request)
    uid = _get_telegram_id(request)

    await db.favorites.remove(uid, clinic_id)
    return {"status": "ok", "clinic_id": clinic_id}
