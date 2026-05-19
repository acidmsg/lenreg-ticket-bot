"""Кастомные исключения API-клиента zdrav.lenreg.ru.

Иерархия:
    ZdravApiError          — базовое исключение
    ├── ZdravNetworkError  — ошибка сети (ConnectionError, NetworkError)
    ├── ZdravTimeoutError  — таймаут запроса
    └── ZdravParseError    — ошибка парсинга (JSONDecodeError, ValidationError)
"""


class ZdravApiError(Exception):
    """Базовое исключение API-клиента zdrav.lenreg.ru."""

    pass


class ZdravNetworkError(ZdravApiError):
    """Ошибка сети: ConnectionError, NetworkError и т.п."""

    pass


class ZdravTimeoutError(ZdravApiError):
    """Таймаут запроса."""

    pass


class ZdravParseError(ZdravApiError):
    """Ошибка парсинга ответа API (JSONDecodeError, ValidationError)."""

    pass
