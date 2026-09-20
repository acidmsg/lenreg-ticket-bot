"""Репозиторий почасовых агрегатов метрик (DASH-6).

Хранит счётчики по часам, чтобы сводка могла показать динамику за 24 часа
и 7 дней. Записи копятся дельтами: каждая итерация фоновой задачи
прибавляет то, что накопилось с прошлого снимка.
"""

from __future__ import annotations

from loguru import logger

from src.database.base_repo import BaseRepository
from src.database.types import MetricsHourlyEntry


class MetricsRepository(BaseRepository):
    """Почасовые агрегаты для трендов на сводке.

    Наследует ``BaseRepository``: соединение берётся свойством ``_c`` в момент
    вызова, а не в конструкторе — при создании фасада соединение ещё не открыто.
    """

    async def upsert_bucket(self, bucket_ts: int, deltas: dict[str, float]) -> None:
        """Прибавляет дельты к часу ``bucket_ts`` (создаёт запись при надобности).

        Args:
            bucket_ts: Начало часа (Unix-время, кратно 3600).
            deltas: Неотрицательные приращения метрик.
        """
        c = self._c
        if c is None:
            return

        try:
            await c.execute(
                "INSERT INTO metrics_hourly ("
                "bucket_ts, api_checks, api_errors, latency_sum, latency_max, "
                "latency_count, slots_found, notifications) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(bucket_ts) DO UPDATE SET "
                "api_checks = api_checks + excluded.api_checks, "
                "api_errors = api_errors + excluded.api_errors, "
                "latency_sum = latency_sum + excluded.latency_sum, "
                "latency_max = MAX(latency_max, excluded.latency_max), "
                "latency_count = latency_count + excluded.latency_count, "
                "slots_found = slots_found + excluded.slots_found, "
                "notifications = notifications + excluded.notifications",
                (
                    bucket_ts,
                    max(0, int(deltas.get("api_checks", 0))),
                    max(0, int(deltas.get("api_errors", 0))),
                    max(0.0, float(deltas.get("latency_sum", 0.0))),
                    max(0.0, float(deltas.get("latency_max", 0.0))),
                    max(0, int(deltas.get("latency_count", 0))),
                    max(0, int(deltas.get("slots_found", 0))),
                    max(0, int(deltas.get("notifications", 0))),
                ),
            )
            await c.commit()
        except Exception:
            # Агрегаты — вспомогательные данные: их сбой не должен ронять бота.
            logger.warning("Не удалось записать часовой агрегат метрик", exc_info=True)

    async def get_series(self, since_ts: int) -> list[MetricsHourlyEntry]:
        """Часовые агрегаты начиная с ``since_ts`` (по возрастанию времени)."""
        c = self._c
        if c is None:
            return []

        try:
            cursor = await c.execute(
                "SELECT bucket_ts, api_checks, api_errors, latency_sum, latency_max, "
                "latency_count, slots_found, notifications "
                "FROM metrics_hourly WHERE bucket_ts >= ? ORDER BY bucket_ts",
                (since_ts,),
            )
            rows = await cursor.fetchall()
        except Exception:
            logger.warning("Не удалось прочитать часовые агрегаты", exc_info=True)
            return []

        return [
            {
                "bucket_ts": int(row["bucket_ts"]),
                "api_checks": int(row["api_checks"]),
                "api_errors": int(row["api_errors"]),
                "latency_sum": float(row["latency_sum"]),
                "latency_max": float(row["latency_max"]),
                "latency_count": int(row["latency_count"]),
                "slots_found": int(row["slots_found"]),
                "notifications": int(row["notifications"]),
            }
            for row in rows
        ]
