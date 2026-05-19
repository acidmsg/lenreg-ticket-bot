"""
Общие зависимости FastAPI для веб-дашборда.

Предоставляют доступ к singleton-объектам через app.state.
"""

from fastapi import Request

from src.database.manager import DatabaseManager
from src.services.healthcheck import HealthMetrics
from src.services.metrics import PrometheusMetrics


def get_db(request: Request) -> DatabaseManager:
    """Возвращает DatabaseManager из app.state."""
    return request.app.state.db


def get_health_metrics(request: Request) -> HealthMetrics:
    """Возвращает HealthMetrics из app.state."""
    return request.app.state.health_metrics


def get_prometheus_metrics(request: Request) -> PrometheusMetrics:
    """Возвращает PrometheusMetrics из app.state."""
    return request.app.state.prometheus_metrics
