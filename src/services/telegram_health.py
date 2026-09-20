"""Телеметрия здоровья Telegram-шлюза для дашборда (UX-7).

Дополняет два существующих сборщика данных, у которых своя зона:

- :class:`~src.services.healthcheck.HealthMetrics` — внешний API zdrav.lenreg.ru;
- :class:`~src.services.metrics.PrometheusMetrics` — агрегаты для Prometheus.

Здесь живёт то, чего у них нет: режим получения обновлений, доступность Bot API
(периодическая проверка), очередь отправки уведомлений и срабатывания лимита
Telegram (429).

Единый источник истины — глобальный экземпляр :data:`telegram_health`.
Блокировка не нужна: обновление полей идёт из корутин одного event loop'а, а шаг
байткода «прочитать → изменить → записать» не содержит ``await``, поэтому
переключение корутин внутри него невозможно. Примитивы loop'а на уровне модуля
не создаются — правило 2
[`event-loop-ownership.md`](../../specs/design/event-loop-ownership.md:530).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from aiogram import Bot
from loguru import logger

# Лимит отправки Telegram Bot API: суммарно ≤ 25 сообщений/с на бота.
# Единый источник истины и для лимитера отправителя
# ([`monitor.py`](src/services/monitor.py:100)), и для дашборда.
TELEGRAM_SEND_RATE_LIMIT = 25.0
TELEGRAM_SEND_RATE_PERIOD = 1.0

# Режим получения обновлений, когда он ещё не подтверждён проверкой Bot API.
MODE_UNKNOWN = "unknown"
MODE_POLLING = "polling"
MODE_WEBHOOK = "webhook"

_MODE_LABELS = {
    MODE_UNKNOWN: "неизвестно",
    MODE_POLLING: "long polling",
    MODE_WEBHOOK: "webhook",
}


@dataclass
class TelegramHealth:
    """Снапшот здоровья Telegram-шлюза.

    Attributes:
        mode: Режим получения обновлений (``polling`` / ``webhook``).
        api_ok: Успешен ли последний пинг Bot API.
        last_api_check_time: Unix-время последней проверки (0.0 — ещё не было).
        last_api_latency_ms: Длительность последней успешной проверки, мс.
        api_checks_total: Всего проверок Bot API.
        api_errors_total: Всего неудачных проверок Bot API.
        last_api_error: Текст последней ошибки проверки.
        queue_depth: Сколько уведомлений сейчас ждёт лимитер отправки.
        queue_peak: Максимум одновременных ожиданий с момента старта.
        sends_total: Успешных отправок уведомлений.
        send_errors_total: Неудачных отправок уведомлений.
        retry_after_total: Срабатываний 429 (пауз по лимиту).
        last_retry_after: Длительность последней паузы по 429, секунды.
    """

    mode: str = MODE_UNKNOWN
    api_ok: bool = False
    last_api_check_time: float = 0.0
    last_api_latency_ms: float = 0.0
    api_checks_total: int = 0
    api_errors_total: int = 0
    last_api_error: str = ""

    queue_depth: int = 0
    queue_peak: int = 0
    sends_total: int = 0
    send_errors_total: int = 0
    retry_after_total: int = 0
    last_retry_after: float = 0.0

    # ── Запись: очередь отправки ─────────────────────────────────

    def queue_enter(self) -> None:
        """Отмечает уведомление, вставшее в очередь лимитера отправки."""
        self.queue_depth += 1
        if self.queue_depth > self.queue_peak:
            self.queue_peak = self.queue_depth

    def queue_exit(self) -> None:
        """Отмечает уведомление, покинувшее очередь лимитера."""
        if self.queue_depth > 0:
            self.queue_depth -= 1

    # ── Запись: результат отправки ───────────────────────────────

    def record_send_ok(self) -> None:
        """Успешная отправка уведомления."""
        self.sends_total += 1

    def record_send_error(self) -> None:
        """Неудачная отправка уведомления."""
        self.send_errors_total += 1

    def record_retry_after(self, seconds: float) -> None:
        """Пауза по лимиту Telegram (429): счётчик и длительность."""
        self.retry_after_total += 1
        self.last_retry_after = float(seconds)

    # ── Запись: проверка Bot API ─────────────────────────────────

    def record_api_ok(self, latency_ms: float, mode: str) -> None:
        """Успешная проверка Bot API."""
        self.api_checks_total += 1
        self.api_ok = True
        self.mode = mode
        self.last_api_check_time = time.time()
        self.last_api_latency_ms = latency_ms
        self.last_api_error = ""

    def record_api_error(self, message: str) -> None:
        """Неудачная проверка Bot API."""
        self.api_checks_total += 1
        self.api_errors_total += 1
        self.api_ok = False
        self.last_api_check_time = time.time()
        self.last_api_error = message

    # ── Представление для дашборда ───────────────────────────────

    def api_health_str(self) -> str:
        """Состояние Bot API: «Доступен (N с назад)» / «Недоступен (...)"."""
        if self.last_api_check_time == 0.0:
            return "проверка ещё не запускалась"
        ago = _ago_str(self.last_api_check_time)
        return f"Доступен ({ago})" if self.api_ok else f"Недоступен ({ago})"

    def mode_label(self) -> str:
        """Человекочитаемый режим получения обновлений."""
        return _MODE_LABELS.get(self.mode, self.mode)

    def last_check_str(self) -> str:
        """Возраст последней проверки Bot API."""
        if self.last_api_check_time == 0.0:
            return "—"
        return _ago_str(self.last_api_check_time)

    def latency_str(self) -> str:
        """Задержка последнего ответа Bot API."""
        if self.last_api_check_time == 0.0 or not self.api_ok:
            return "—"
        return f"{self.last_api_latency_ms:.0f} мс"

    def queue_str(self) -> str:
        """Очередь отправки: текущая глубина и пик за сессию."""
        return f"{self.queue_depth} (пик {self.queue_peak})"

    def sends_str(self) -> str:
        """Отправки: успешные / неудачные."""
        return f"{self.sends_total} / {self.send_errors_total}"

    def retry_after_str(self) -> str:
        """Срабатывания лимита 429 и длительность последней паузы."""
        if self.retry_after_total == 0:
            return "0"
        return f"{self.retry_after_total} (последняя {self.last_retry_after:.0f} с)"

    def rate_str(self) -> str:
        """Ограничение отправки, заданное лимитером."""
        limit = f"{TELEGRAM_SEND_RATE_LIMIT:.0f}"
        period = f"{TELEGRAM_SEND_RATE_PERIOD:.0f}"
        return f"{limit} сообщ./{period} с"

    def snapshot(self) -> dict[str, Any]:
        """Снапшот для шаблонов и живого обновления дашборда.

        Returns:
            Словарь с готовыми строками (``*_str``), флагом ``api_ok`` и
            сырыми значениями для JSON-сводки.
        """
        return {
            "mode": self.mode,
            "mode_label": self.mode_label(),
            "api_ok": self.api_ok,
            "api_health": self.api_health_str(),
            "last_check": self.last_check_str(),
            "last_check_seconds_ago": (
                int(time.time() - self.last_api_check_time)
                if self.last_api_check_time
                else None
            ),
            "latency": self.latency_str(),
            "latency_ms": round(self.last_api_latency_ms, 1),
            "queue": self.queue_str(),
            "queue_depth": self.queue_depth,
            "queue_peak": self.queue_peak,
            "rate": self.rate_str(),
            "rate_limit": TELEGRAM_SEND_RATE_LIMIT,
            "sends": self.sends_str(),
            "sends_total": self.sends_total,
            "send_errors_total": self.send_errors_total,
            "retry_after": self.retry_after_str(),
            "retry_after_total": self.retry_after_total,
            "last_retry_after": self.last_retry_after,
            "api_checks_total": self.api_checks_total,
            "api_errors_total": self.api_errors_total,
            "last_api_error": self.last_api_error,
        }


def _ago_str(timestamp: float) -> str:
    """Возраст метки времени: «N с назад» до двух минут, дальше — минуты."""
    delta = int(time.time() - timestamp)
    return f"{delta}с назад" if delta < 120 else f"{delta // 60}м назад"


# Глобальный экземпляр телеметрии Telegram-шлюза.
telegram_health = TelegramHealth()


async def check_bot_api(bot: Bot) -> bool:
    """Проверяет доступность Bot API и определяет режим получения обновлений.

    Запрос ``getWebhookInfo`` — самый дешёвый вызов API, который не расходует
    апдейты и работает в обоих режимах: непустой ``url`` означает webhook,
    пустой — long polling.

    Returns:
        ``True`` если Bot API ответил, иначе ``False``.
    """
    started = time.perf_counter()
    try:
        info = await bot.get_webhook_info()
    except Exception as exc:
        # Широкий перехват намеренный: для задачи о доступности любая ошибка
        # клиента/сети означает «API недоступен», и падение фонового пинга на
        # первом же сбое лишило бы дашборд данных. Исключение не замалчивается:
        # тип и текст уходят в телеметрию и в WARNING-лог.
        message = f"{type(exc).__name__}: {exc}"
        logger.warning("Проверка Bot API не прошла: {}", message)
        telegram_health.record_api_error(message)
        return False

    latency_ms = (time.perf_counter() - started) * 1000
    mode = MODE_WEBHOOK if info.url else MODE_POLLING
    telegram_health.record_api_ok(latency_ms, mode)
    return True
