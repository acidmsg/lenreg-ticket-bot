"""Числовые границы фильтра отслеживания — единый источник для Mini App.

Серверная валидация Mini App (:mod:`src.web.routers.user_api`) применяет
эти ограничения. Константы вынесены в нейтральный модуль без зависимостей
от aiogram.
"""

from __future__ import annotations

#: Максимальный горизонт даты фильтра — 365 дней от сегодня.
FILTER_MAX_HORIZON_DAYS = 365

#: Максимальное число конкретных дат в allow-списке.
FILTER_MAX_SPECIFIC_DATES = 10
