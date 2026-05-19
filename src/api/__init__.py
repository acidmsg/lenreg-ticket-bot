"""Пакет API-клиента zdrav.lenreg.ru."""

from src.api.exceptions import (
    ZdravApiError,
    ZdravNetworkError,
    ZdravParseError,
    ZdravTimeoutError,
)
from src.api.zdrav_client import ZdravClient

__all__ = [
    "ZdravApiError",
    "ZdravClient",
    "ZdravNetworkError",
    "ZdravParseError",
    "ZdravTimeoutError",
]
