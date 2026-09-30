"""
Репозиторий метрик discovery: почасовые агрегаты обходов справочника врачей.

Динамика нужна, чтобы по ``/metrics`` и странице «Система» было видно, как
часто проходит обход каталога и сколько врачей добавляется, а сам справочник
меняется редко. Записи копятся по часам и переживают перезапуск процесса.
"""

from __future__ import annotations

import time

from src.database.base_repo import BaseRepository

HOUR_SECONDS = 3600
"""Длина часа в секундах: ширина корзины агрегации."""

DEFAULT_HISTORY_HOURS = 168
"""Окно истории по умолчанию — неделя."""


class MetricsRepository(BaseRepository):
    """Почасовые агрегаты discovery (таблица metrics_hourly)."""

    async def record_discovery(
        self,
        *,
        doctors_total: int,
        doctors_added: int,
        ts: float | None = None,
    ) -> None:
        """Записывает итоги одного цикла discovery в текущую часовую корзину.

        Внутри часа значения накапливаются: ``doctors_added`` и
        ``discovery_cycles`` суммируются, а ``doctors_total`` перезаписывается
        последним снимком справочника.

        Args:
            doctors_total: Текущее число врачей в справочнике.
            doctors_added: Сколько новых врачей обнаружено за цикл.
            ts: Момент завершения цикла; по умолчанию — текущее время.
        """
        moment = ts if ts is not None else time.time()
        bucket = int(moment // HOUR_SECONDS * HOUR_SECONDS)
        await self._c.execute(
            "INSERT INTO metrics_hourly "
            "(bucket_ts, doctors_total, doctors_added, discovery_cycles) "
            "VALUES (?, ?, ?, 1) "
            "ON CONFLICT(bucket_ts) DO UPDATE SET "
            "doctors_total = excluded.doctors_total, "
            "doctors_added = metrics_hourly.doctors_added + excluded.doctors_added, "
            "discovery_cycles = metrics_hourly.discovery_cycles + 1",
            (bucket, doctors_total, doctors_added),
        )
        await self._c.commit()

    async def get_discovery_history(
        self, hours: int = DEFAULT_HISTORY_HOURS
    ) -> list[dict]:
        """История обходов discovery за последние ``hours`` часов.

        Args:
            hours: Ширина окна в часах (по умолчанию — неделя).

        Returns:
            Точки по возрастанию времени: ``bucket_ts``, ``doctors_total``,
            ``doctors_added``, ``discovery_cycles``.
        """
        since = int(time.time() - hours * HOUR_SECONDS)
        cursor = await self._c.execute(
            "SELECT bucket_ts, doctors_total, doctors_added, discovery_cycles "
            "FROM metrics_hourly WHERE bucket_ts >= ? ORDER BY bucket_ts",
            (since,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "bucket_ts": row["bucket_ts"],
                "doctors_total": row["doctors_total"],
                "doctors_added": row["doctors_added"],
                "discovery_cycles": row["discovery_cycles"],
            }
            for row in rows
        ]
