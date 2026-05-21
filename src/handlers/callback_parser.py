"""
Хелперы для унифицированного парсинга callback_data.

Предоставляет функцию `_parse_callback_arg()` для безопасного извлечения
именованных параметров из callback_data со значениями по умолчанию,
а также фабрику фильтров для типизированных CallbackData.

Пример использования:
    parts = call.data.split("_")
    city_idx = _parse_callback_arg(parts, 4, "all")
"""

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


def cb_filter(cb_class: type[CallbackData]) -> CallbackData:
    """Создаёт экземпляр CallbackData-фильтра для магического фильтра aiogram.

    Использование:
        @router.callback_query(PatientSelect.filter())
        async def handler(call: CallbackQuery, callback_data: PatientSelect):
            p_id = callback_data.p_id
    """
    return cb_class.filter()  # type: ignore[return-value]
