"""Тренды для сводки: почасовые ряды и спарклайны (DASH-6).

Ряды строятся из двух источников:
* события слотов — из ``monitoring_log`` (историю уже пишет мониторинг);
* проверки API, ошибки и латентность — из ``metrics_hourly``, куда фоновая
  задача складывает приращения счётчиков процесса.

Спарклайны рисуются на сервере: шаблон получает готовую строку точек
для ``<polyline>``, внешние библиотеки не нужны.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

from loguru import logger

HOUR_SECONDS = 3600
TREND_HOURS_DAY = 24
TREND_HOURS_WEEK = 24 * 7


def hour_bucket(ts: float) -> int:
    """Начало часа, в который попадает ``ts`` (Unix-время)."""
    return int(ts // HOUR_SECONDS) * HOUR_SECONDS


async def snapshot_hourly(
    db: Any,
    health_metrics: Any,
    prometheus_metrics: Any,
    state: dict[str, Any],
) -> None:
    """Записывает приращение счётчиков процесса в текущий час.

    ``state`` живёт в памяти процесса и хранит предыдущие значения
    счётчиков: в БД уходят только дельты. Счётчики монотонные, поэтому
    отрицательная дельта (перезапуск процесса) трактуется как 0.

    Args:
        db: Фасад БД.
        health_metrics: Счётчики healthcheck.
        prometheus_metrics: Прометеевские счётчики (слоты).
        state: Предыдущие значения счётчиков (изменяется на месте).
    """
    try:
        current = {
            "api_checks": float(health_metrics.api_checks_total),
            "api_errors": float(health_metrics.api_errors_total),
            "latency_sum": float(
                getattr(health_metrics, "api_latency_sum", 0.0) or 0.0
            ),
            "slots_found": float(prometheus_metrics._slots_found_total._value.get()),
            "notifications": float(health_metrics.monitoring_notifications_sent),
        }
        # Последняя проверка могла ещё не выполняться: None превратился бы
        # в TypeError уже после сдвига базы отсчёта.
        last_duration = float(
            getattr(health_metrics, "last_check_duration", 0.0) or 0.0
        )
    except Exception:
        # Чтение счётчиков не должно ронять фоновую задачу: без метрик
        # дашборд живёт, без задачи — теряется вся история трендов.
        logger.warning("Тренды: не удалось прочитать счётчики", exc_info=True)
        return

    deltas: dict[str, float] = {}
    for key, value in current.items():
        previous = state.get(key)
        if previous is None:
            # Первый снимок — база отсчёта: приращение приписать нечему,
            # поэтому в текущий час уходит ноль, а не всё накопленное.
            deltas[key] = 0.0
        elif value < previous:
            # Счётчик начался заново: прирост считаем от нуля, иначе
            # приращение после сброса потерялось бы.
            deltas[key] = value
        else:
            deltas[key] = value - previous

    bucket = hour_bucket(time.time())

    # Максимум латентности копим за текущий час и сбрасываем при смене часа:
    # мгновенное значение последней проверки — не часовой максимум.
    if state.get("_latency_bucket") != bucket:
        state["_latency_bucket"] = bucket
        state["_latency_max"] = 0.0
    state["_latency_max"] = max(float(state.get("_latency_max", 0.0)), last_duration)

    if not any(deltas.values()):
        # Записывать нечего, но базу отсчёта двигаем: счётчики не изменились.
        state.update(current)
        return

    try:
        await db.record_metrics_bucket(
            bucket,
            {
                "api_checks": deltas["api_checks"],
                "api_errors": deltas["api_errors"],
                "latency_sum": deltas["latency_sum"],
                "latency_max": float(state["_latency_max"]),
                "latency_count": deltas["api_checks"],
                "slots_found": deltas["slots_found"],
                "notifications": deltas["notifications"],
            },
        )
    except Exception:
        # Базу отсчёта НЕ двигаем: приращение уйдёт в следующий удачный
        # вызов, а не потеряется.
        logger.warning("Тренды: не удалось сохранить часовой агрегат", exc_info=True)
        return

    state.update(current)


async def collect_trends(db: Any, hours: int) -> dict[str, Any]:
    """Ряд за ``hours`` часов: слоты из журнала, API — из агрегатов.

    Returns:
        Словарь с готовыми рядами: ``slots_found``, ``slots_gone``,
        ``api_checks``, ``api_errors``, ``latency_avg``, ``notifications``.
    """
    now = time.time()
    start = hour_bucket(now) - (hours - 1) * HOUR_SECONDS
    buckets = [start + index * HOUR_SECONDS for index in range(hours)]

    slot_events = await db.get_slot_events_per_hour(float(start))
    metrics_rows = await db.get_metrics_series(start)
    metrics_by_bucket = {int(row["bucket_ts"]): row for row in metrics_rows}

    series: dict[str, list[float]] = {
        "slots_found": [],
        "slots_gone": [],
        "api_checks": [],
        "api_errors": [],
        "latency_avg": [],
        "notifications": [],
    }

    for bucket in buckets:
        events = slot_events.get(bucket, {})
        row = metrics_by_bucket.get(bucket)

        series["slots_found"].append(float(events.get("появился", 0)))
        series["slots_gone"].append(
            float(events.get("исчез", 0) + events.get("уменьшился", 0))
        )
        if row is None:
            series["api_checks"].append(0.0)
            series["api_errors"].append(0.0)
            series["latency_avg"].append(0.0)
            series["notifications"].append(0.0)
            continue

        series["api_checks"].append(float(row["api_checks"]))
        series["api_errors"].append(float(row["api_errors"]))
        count = int(row["latency_count"])
        series["latency_avg"].append(
            round(float(row["latency_sum"]) / count, 3) if count else 0.0
        )
        series["notifications"].append(float(row["notifications"]))

    # «Нет данных» — это отсутствие строк в окне; нулевой ряд (например,
    # ноль ошибок API) — полноценные данные, и рисовать его нужно.
    series["has_data"] = bool(slot_events) or bool(metrics_by_bucket)
    return series


def sparkline_points(
    values: Sequence[float], width: int = 160, height: int = 32, padding: int = 2
) -> str | None:
    """Точки для ``<polyline>``: строка ``"x,y x,y …"`` или ``None``.

    ``None`` — только когда значений нет вовсе. Ряд из нулей — это данные:
    он рисуется ровной линией по низу (ноль ошибок API информативен).
    """
    numbers = [float(value) for value in values]
    if not numbers:
        return None

    # Одна точка — плоская линия во всю ширину: одиночная координата
    # невидима в SVG.
    if len(numbers) == 1:
        numbers = [numbers[0], numbers[0]]

    top = max(numbers)
    inner_width = max(1, width - 2 * padding)
    inner_height = max(1, height - 2 * padding)
    inner_width = max(1, width - 2 * padding)
    step = inner_width / (len(numbers) - 1)

    points: list[str] = []
    for index, value in enumerate(numbers):
        x = padding + step * index
        # Ряд из нулей — ровная линия по низу, а не «нет данных».
        y = height - padding if top <= 0 else padding + inner_height * (1 - value / top)
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def peak_label(values: Sequence[float]) -> str:
    """Подпись максимума ряда для карточки тренда."""
    numbers = [float(value) for value in values]
    if not numbers:
        return "нет данных"
    peak = max(numbers)
    # Дробную часть показываем только там, где она есть: латентность
    # измеряется секундами (0.4 с), а счётчики — целыми.
    if peak != int(peak):
        return f"макс {peak:g}"
    return f"макс {int(peak)}"


TREND_SERIES: tuple[tuple[str, str], ...] = (
    ("slots_found", "Найдено слотов"),
    ("api_checks", "Проверок API"),
    ("api_errors", "Ошибок API"),
    ("latency_avg", "Латентность, с"),
    ("notifications", "Уведомлений"),
)


def build_cards(series: dict[str, Any]) -> list[dict[str, Any]]:
    """Готовые карточки спарклайнов: точки, подпись пика и итог ряда."""
    has_data = bool(series.get("has_data"))
    cards: list[dict[str, Any]] = []
    for key, title in TREND_SERIES:
        values = [float(value) for value in series.get(key, [])]
        if not has_data:
            # В окне нет ни одной записи: честное «нет данных», а не линия
            # нулей, за которой может скрываться сбой сбора метрик.
            cards.append(
                {
                    "key": key,
                    "title": title,
                    "points": None,
                    "label": "нет данных",
                    "total": 0,
                }
            )
            continue
        # Сумма почасовых средних латентностей смысла не имеет — берём пик.
        total = (
            max(values) if key == "latency_avg" and values else round(sum(values), 2)
        )
        cards.append(
            {
                "key": key,
                "title": title,
                "points": sparkline_points(values),
                "label": peak_label(values),
                "total": total,
            }
        )
    return cards
