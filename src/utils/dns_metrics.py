"""Метрика переключений транспорта API на адрес из DNS-ответа.

Модуль нижнего слоя: счётчик вынесен из `src.services.metrics`, чтобы
`src.api.dns_fallback` инкрементировал его без зависимости от слоя services.
Счётчик регистрируется в дефолтном registry Prometheus, поэтому экспозиция
`/metrics` не меняется.
"""

from prometheus_client import Counter

_dns_fallback_switch_total = Counter(
    "lenreg_ticket_dns_fallback_switch_total",
    "Счётчик переключений транспорта API на адрес из DNS-ответа",
)


def inc_dns_fallback_switch() -> None:
    """Инкрементирует счётчик переключений транспорта на актуальный IP."""
    _dns_fallback_switch_total.inc()
