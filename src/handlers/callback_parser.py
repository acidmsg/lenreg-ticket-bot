"""
Хелперы для унифицированного парсинга callback_data.

Предоставляет функцию `_parse_callback_arg()` для безопасного извлечения
именованных параметров из callback_data с значениями по умолчанию.

Пример использования:
    parts = call.data.split("_")
    city_idx = _parse_callback_arg(parts, 4, "all")
"""


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
