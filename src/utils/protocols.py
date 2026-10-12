"""Структурные протоколы нижнего слоя.

Разрывают связи `src.utils` с верхними слоями: вместо импорта конкретных типов
(`src.api.models.DateInfo`, `src.database.manager.DatabaseManager`) функции
нижнего слоя описывают минимально необходимый структурный контракт.
Совместимость конкретных реализаций проверяется статически (`mypy`).
"""

from __future__ import annotations

from typing import Protocol


class SlotDateParts(Protocol):
    """Минимум полей даты слота, нужный форматтеру (структурная типизация)."""

    day: str
    month: str
    year: str


class LastMessageStore(Protocol):
    """Хранилище id последнего сообщения (структурная типизация DatabaseManager)."""

    async def get_last_message_id(self, uid: str, p_id: str, d_id: str) -> int | None:
        """Возвращает id последнего сообщения пары пациент-врач или ``None``."""
        ...

    async def set_last_message_id(
        self, uid: str, p_id: str, d_id: str, message_id: int
    ) -> None:
        """Сохраняет id последнего сообщения пары пациент-врач."""
        ...
