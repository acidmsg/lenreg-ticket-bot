"""
Агрегатор Mini App API (``/api/user``).

Публичный символ ``router`` собирает доменные под-роутеры: порядок включения
фиксирует порядок маршрутов Mini App API. Эндпоинты живут в модулях ``user_*``,
бизнес-логика — в ``src.services.*``.

Все под-роутеры описывают пути без префикса: аутентификация выполняется
middleware ``TelegramInitDataMiddleware`` (``request.state.telegram_id``).
"""

from fastapi import APIRouter

from src.web.routers import (
    user_bookings,
    user_doctors,
    user_favorites,
    user_monitoring,
    user_patients,
    user_profile,
    user_slots,
)
from src.web.routers.user_bookings import BOOK_ERROR_CODES
from src.web.routers.user_patients import PatientUpdateRequest

# Публичная поверхность агрегатора: ``router`` для ``app.py`` и реэкспорт
# моделей/констант, которые импортируют тесты контракта OpenAPI.
__all__ = ["BOOK_ERROR_CODES", "PatientUpdateRequest", "router"]

router = APIRouter(prefix="/api/user", tags=["Mini App (JSON API)"])

# Порядок включения фиксирует порядок маршрутов Mini App API (§3.2 дизайна TD-028).
router.include_router(user_profile.router)
router.include_router(user_favorites.router)
router.include_router(user_doctors.router)
router.include_router(user_slots.router)
router.include_router(user_monitoring.router)
router.include_router(user_patients.router)
router.include_router(user_bookings.router)
