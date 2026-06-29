"""
Хелперы для унифицированного парсинга callback_data.

Предоставляет функцию `_parse_callback_arg()` для безопасного извлечения
именованных параметров из callback_data со значениями по умолчанию,
а также фабрику фильтров для типизированных CallbackData.

Пример использования:
    parts = call.data.split("_")
    city_idx = _parse_callback_arg(parts, 4, "all")
"""

from typing import Any

from aiogram.filters.callback_data import CallbackData


def _parse_callback_arg(parts: list[str], index: int, default: str = "all") -> str:
    """Безопасно извлекает аргумент из разобранной callback_data.

    Args:
        parts: Результат split("_") от call.data.
        index: Индекс извлекаемого элемента.
        default: Значение по умолчанию, если индекс выходит за границы.

    Returns:
        Значение по индексу, если он существует, иначе default.

    Пример:
        >>> _parse_callback_arg(["a", "b", "c"], 2)
        'c'
        >>> _parse_callback_arg(["a", "b"], 2, "all")
        'all'
    """
    if index < len(parts):
        return parts[index]
    return default


def create_callback_filter(cb_class: type[CallbackData] | str) -> Any:
    """Создаёт фильтр для магического фильтра aiogram.

    Поддерживает как типизированные CallbackData (с полями), так и строковые константы
    префиксов (для callback'ов без полезной нагрузки).

    Использование:
        # Типизированный CallbackData с полями:
        @router.callback_query(create_callback_filter(PatientSelect))
        async def handler(call: CallbackQuery, callback_data: PatientSelect):
            p_id = callback_data.p_id

        # Строковая константа (без полей):
        @router.callback_query(create_callback_filter(CB_BACK_TO_MAIN))
        async def handler(call: CallbackQuery):
            ...
    """
    if isinstance(cb_class, str):
        from aiogram import F

        return F.data == cb_class
    return cb_class.filter()
