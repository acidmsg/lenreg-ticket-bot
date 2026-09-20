"""Глобальный поиск по дашборду (DASH-9).

Ищет одним запросом по четырём сущностям: пользователи (uid), пациенты
(ФИО/псевдоним/p_id), врачи (ФИО) и клиники (название/город). Пустой запрос
не ищет ничего — страница показывает подсказку вместо случайной выдачи.
"""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

# Минимальная длина запроса: одна буква даёт шумную выдачу.
MIN_QUERY_LENGTH = 2
SEARCH_LIMIT = 20


async def search_all(db: Any, query: str, limit: int = SEARCH_LIMIT) -> dict[str, Any]:
    """Ищет по всем разделам и возвращает сгруппированный результат.

    Args:
        db: Фасад БД.
        query: Подстрока поиска (регистр не важен для латиницы; для русских
            имён сравнение идёт как есть).
        limit: Максимум строк на раздел.

    Returns:
        Словарь с ``query``, ``too_short``, ``total`` и разделами
        ``users``, ``patients``, ``doctors``, ``clinics``.
    """
    result: dict[str, Any] = {
        "query": query,
        "too_short": len(query.strip()) < MIN_QUERY_LENGTH,
        "users": [],
        "patients": [],
        "doctors": [],
        "clinics": [],
        "total": 0,
    }
    if result["too_short"]:
        return result

    text = query.strip()
    # Разделы независимы: сбой одного не должен скрывать остальные.
    sections = await asyncio.gather(
        db.search_users(text, limit),
        db.search_patients(text, limit),
        db.search_doctors_by_name(text, limit),
        db.search_clinics(text, limit),
        return_exceptions=True,
    )
    names = ("users", "patients", "doctors", "clinics")
    for name, section in zip(names, sections, strict=True):
        if isinstance(section, BaseException):
            logger.warning(f"Поиск: раздел {name} не отработал", exc_info=section)
            result[name] = []
        else:
            result[name] = section

    result["total"] = (
        len(result["users"])
        + len(result["patients"])
        + len(result["doctors"])
        + len(result["clinics"])
    )
    return result
