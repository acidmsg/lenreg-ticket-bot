"""
Модуль Prometheus-метрик для бота.

Предоставляет HTTP-endpoint `/metrics` с метриками в формате Prometheus.
Агрегирует данные из HealthMetrics, DatabaseManager и RedisClient.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest

from src.database.manager import DatabaseManager
from src.services.healthcheck import _metrics_lock
from src.services.healthcheck import metrics as health_metrics
from src.utils.redis import RedisClient


class PrometheusMetrics:
    """
    Агрегатор метрик для Prometheus.

    Синхронизирует данные из глобального экземпляра HealthMetrics,
    DatabaseManager и RedisClient в Prometheus-формат. Использует
    дельта-инкременты для Counter'ов, чтобы не нарушать семантику
    монотонно возрастающих значений.

    Использование:
        pm = PrometheusMetrics()
        body, content_type = await pm.generate_response(db)
    """

    def __init__(self) -> None:
        # -- Gauge'и (мгновенные значения) --
        self._monitor_status: Any = Gauge(
            "zdrav_monitor_status",
            "Статус мониторинга (1 = работает, 0 = остановлен)",
        )
        self._healthcheck_last_success: Any = Gauge(
            "zdrav_healthcheck_last_success_timestamp",
            "Таймстемп последнего успешного healthcheck",
        )
        self._healthcheck_duration: Any = Gauge(
            "zdrav_healthcheck_duration_seconds",
            "Длительность последнего healthcheck",
        )
        self._active_users: Any = Gauge(
            "zdrav_active_users",
            "Количество активных пользователей",
        )
        self._monitored_doctors: Any = Gauge(
            "zdrav_monitored_doctors",
            "Количество отслеживаемых врачей",
        )
        self._redis_connected: Any = Gauge(
            "zdrav_redis_connected",
            "Статус соединения с Redis (1 = подключен, 0 = отключен)",
        )

        # -- Schema Change Detection (F8) Gauge --
        self._schema_drift: Any = Gauge(
            "zdrav_api_schema_drift",
            "Расхождение схемы API (1 = расхождение, 0 = совпадение)",
            labelnames=["endpoint"],
        )

        # -- Хранение текущего состояния схем для веб-дашборда --
        self._schema_status: dict[str, bool] = {}

        # -- Counter'ы (монотонно возрастающие) --
        self._healthcheck_errors_total: Any = Counter(
            "zdrav_healthcheck_errors_total",
            "Счётчик ошибок healthcheck",
        )
        self._slots_found_total: Any = Counter(
            "zdrav_slots_found_total",
            "Счётчик найденных слотов",
        )
        self._api_requests_total: Any = Counter(
            "zdrav_api_requests_total",
            "Счётчик запросов к API",
        )
        self._api_errors_total: Any = Counter(
            "zdrav_api_errors_total",
            "Счётчик ошибок API",
        )

        # -- Schema Change Detection (F8) Counter --
        self._schema_changes_total: Any = Counter(
            "zdrav_api_schema_changes_total",
            "Общее количество обнаруженных изменений схемы API",
            labelnames=["endpoint"],
        )

        # -- Хранение предыдущих значений для дельта-инкрементов --
        self._prev_healthcheck_errors: int = 0
        self._prev_slots_found: int = 0
        self._prev_api_requests: int = 0
        self._prev_api_errors: int = 0

    async def _sync_counters(self) -> None:
        """Синхронизирует Counter'ы дельта-инкрементами под блокировкой."""
        async with _metrics_lock:
            # healthcheck_errors_total = api_errors_total
            delta_hc = health_metrics.api_errors_total - self._prev_healthcheck_errors
            if delta_hc > 0:
                self._healthcheck_errors_total.inc(delta_hc)
                self._prev_healthcheck_errors = health_metrics.api_errors_total
            elif delta_hc < 0:
                # Сброс (например, перезапуск бота) — переустановка через _value
                logger.debug("Сброс zdrav_healthcheck_errors_total")
                self._healthcheck_errors_total._value.set(
                    float(health_metrics.api_errors_total)
                )
                self._prev_healthcheck_errors = health_metrics.api_errors_total

            delta_slots = (
                health_metrics.monitoring_notifications_sent - self._prev_slots_found
            )
            if delta_slots > 0:
                self._slots_found_total.inc(delta_slots)
                self._prev_slots_found = health_metrics.monitoring_notifications_sent
            elif delta_slots < 0:
                logger.debug("Сброс zdrav_slots_found_total")
                self._slots_found_total._value.set(
                    float(health_metrics.monitoring_notifications_sent)
                )
                self._prev_slots_found = health_metrics.monitoring_notifications_sent

            delta_api = health_metrics.api_checks_total - self._prev_api_requests
            if delta_api > 0:
                self._api_requests_total.inc(delta_api)
                self._prev_api_requests = health_metrics.api_checks_total
            elif delta_api < 0:
                logger.debug("Сброс zdrav_api_requests_total")
                self._api_requests_total._value.set(
                    float(health_metrics.api_checks_total)
                )
                self._prev_api_requests = health_metrics.api_checks_total

            delta_err = health_metrics.api_errors_total - self._prev_api_errors
            if delta_err > 0:
                self._api_errors_total.inc(delta_err)
                self._prev_api_errors = health_metrics.api_errors_total
            elif delta_err < 0:
                logger.debug("Сброс zdrav_api_errors_total")
                self._api_errors_total._value.set(
                    float(health_metrics.api_errors_total)
                )
                self._prev_api_errors = health_metrics.api_errors_total

    async def _sync_gauges(self, db: DatabaseManager) -> None:
        """Синхронизирует Gauge'и с текущим состоянием."""
        async with _metrics_lock:
            # Статус мониторинга
            self._monitor_status.set(1.0 if health_metrics.monitor_loop_alive else 0.0)

            # Таймстемп последнего успешного healthcheck
            if health_metrics.last_api_ok and health_metrics.last_api_check_time > 0:
                self._healthcheck_last_success.set(health_metrics.last_api_check_time)

            # Длительность healthcheck
            self._healthcheck_duration.set(health_metrics.last_check_duration)

        # Активные пользователи и отслеживаемые врачи (из БД)
        stats = db.get_user_statistics()
        self._active_users.set(float(stats["total_users"]))
        self._monitored_doctors.set(float(stats["total_monitored_doctors"]))

        # Статус Redis
        redis = await RedisClient.get_instance()
        self._redis_connected.set(1.0 if redis.is_available else 0.0)

    async def update(self, db: DatabaseManager) -> None:
        """Полная синхронизация всех метрик (Gauge + Counter)."""
        await self._sync_counters()
        await self._sync_gauges(db)

    async def generate_response(self, db: DatabaseManager) -> tuple[bytes, str]:
        """Генерирует тело ответа в формате Prometheus."""
        await self.update(db)
        return generate_latest(), CONTENT_TYPE_LATEST

    # ── Schema Change Detection (F8) ──────────────────────────────

    def set_schema_drift(self, endpoint: str, has_drift: bool) -> None:
        """Устанавливает Gauge расхождения схемы для эндпоинта."""
        self._schema_drift.labels(endpoint=endpoint).set(1.0 if has_drift else 0.0)
        # Сохраняем в dict для веб-дашборда
        self._schema_status[endpoint] = has_drift

    def inc_schema_changes(self, endpoint: str, count: int = 1) -> None:
        """Инкрементирует счётчик изменений схемы."""
        self._schema_changes_total.labels(endpoint=endpoint).inc(count)

    def get_schema_status(self) -> dict[str, bool]:
        """Возвращает текущее состояние схем API.

        Returns:
            Словарь {endpoint: has_drift}, где True — расхождение,
            False — схемы совпадают.
        """
        return dict(self._schema_status)


# Глобальный экземпляр Prometheus-метрик
prometheus_metrics = PrometheusMetrics()
