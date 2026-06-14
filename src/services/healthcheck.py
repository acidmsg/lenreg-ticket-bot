"""
Модуль мониторинга здоровья бота.

Предоставляет:
1. Команду /status — отдаёт текущее состояние бота
2. Фоновый healthcheck-цикл — периодически проверяет API zdrav.lenreg.ru
3. Healthcheck-метрики для логирования
"""

import asyncio
import time
from dataclasses import dataclass, field

from aiogram import Bot
from loguru import logger

from src.api.zdrav_client import ZdravClient
from src.config import settings
from src.database.manager import DatabaseManager
from src.i18n import _


@dataclass
class HealthMetrics:
    """Сборщик метрик здоровья бота."""

    # Когда запущен
    start_time: float = field(default_factory=time.time)

    # Накопительная статистика API (для Prometheus / логирования)
    api_checks_total: int = 0
    api_errors_total: int = 0
    api_success_total: int = 0

    # Снапшот последнего цикла healthcheck (бинарный: доступен/недоступен)
    last_api_check_time: float = 0.0  # 0.0 = ещё ни разу
    last_api_ok: bool = False
    last_api_error_time: float | None = None
    last_api_error_message: str = ""

    # Длительность последней проверки (для Prometheus)
    last_check_duration: float = 0.0

    # Статистика мониторинга
    monitoring_slots_checked: int = 0
    monitoring_notifications_sent: int = 0
    last_monitoring_cycle_time: float | None = None

    # Состояние фоновых задач
    discovery_tasks_alive: int = 0
    monitor_loop_alive: bool = False
    healthcheck_loop_alive: bool = False

    # Ошибки
    last_error_time: float | None = None
    last_error_message: str = ""

    def uptime_seconds(self) -> float:
        return time.time() - self.start_time

    def uptime_str(self) -> str:
        total = int(self.uptime_seconds())
        days = total // 86400
        hours = (total % 86400) // 3600
        minutes = (total % 3600) // 60
        seconds = total % 60
        parts = []
        if days:
            parts.append(f"{days}д")
        if hours:
            parts.append(f"{hours}ч")
        if minutes:
            parts.append(f"{minutes}м")
        parts.append(f"{seconds}с")
        return " ".join(parts)

    def api_health_str(self) -> str:
        """Состояние API — бинарное: ✅ Доступен / ❌ Недоступен."""
        if self.last_api_check_time == 0.0:
            if self.healthcheck_loop_alive:
                return "⏳ Выполняется первый цикл проверки..."
            return "⏳ Healthcheck ещё не запущен"
        delta = int(time.time() - self.last_api_check_time)
        ago = f"{delta}с назад" if delta < 120 else f"{delta // 60}м назад"
        if self.last_api_ok:
            return f"✅ Доступен ({ago})"
        return f"❌ Недоступен ({ago})"

    def last_error_str(self) -> str:
        if not self.last_error_message:
            return "—"
        delta = int(time.time() - (self.last_error_time or 0))
        return f"{self.last_error_message} ({delta}с назад)"


# Глобальный экземпляр метрик
metrics = HealthMetrics()
metrics_lock = asyncio.Lock()


async def safe_increment(attr: str, delta: int = 1) -> None:
    """Атомарный инкремент поля metrics (под metrics_lock)."""
    async with metrics_lock:
        current = getattr(metrics, attr, 0)
        setattr(metrics, attr, current + delta)


async def safe_set(attr: str, value) -> None:
    """Атомарная установка поля metrics (под metrics_lock)."""
    async with metrics_lock:
        setattr(metrics, attr, value)


async def healthcheck_loop(bot: Bot, api: ZdravClient, db: DatabaseManager) -> None:
    """
    Фоновый цикл проверки здоровья.

    Каждые CHECK_INTERVAL секунд:
    1. Делает 1 запрос к API zdrav.lenreg.ru — проверка доступности
    2. Фиксирует бинарный результат: доступен / недоступен
    3. Логирует состояние
    """
    await safe_set("healthcheck_loop_alive", True)
    logger.info("Healthcheck-цикл запущен")

    while True:
        try:
            # Один запрос — любая клиника/пациент, API общий
            ok = False
            check_start = time.time()
            try:
                specialties = await api.fetch_speciality_list(
                    settings.DISCOVERY_PATIENT_ID_ADULT,
                    settings.DEFAULT_CLINIC_ID,
                    limiter=api.limiter_healthcheck,
                )
                if specialties is not None:
                    ok = True
                    await safe_increment("api_success_total")
                    await safe_increment("api_checks_total")
                else:
                    await safe_increment("api_checks_total")
                    await safe_increment("api_errors_total")
                    await safe_set("last_api_error_time", time.time())
                    await safe_set("last_api_error_message", "API вернул None")
            except Exception as e:
                await safe_increment("api_checks_total")
                await safe_increment("api_errors_total")
                await safe_set("last_api_error_time", time.time())
                await safe_set("last_api_error_message", str(e)[:200])
                logger.error(f"Healthcheck: ошибка API: {e}")

            # Атомарно фиксируем снапшот
            now = time.time()
            async with metrics_lock:
                metrics.last_api_check_time = now
                metrics.last_api_ok = ok
                metrics.last_check_duration = now - check_start
                uptime = metrics.uptime_str()
                api_health = metrics.api_health_str()

            stats = db.get_user_statistics()

            # Логируем состояние
            logger.info(
                f"Healthcheck | "
                f"Uptime: {uptime} | "
                f"API: {api_health} | "
                f"Users: {stats['total_users']} | "
                f"Patients: {stats['total_patients']} | "
                f"Monitored: {stats['total_monitored_doctors']}"
            )

            # Пауза до следующего цикла
            await asyncio.sleep(settings.CHECK_INTERVAL)

        except asyncio.CancelledError:
            await safe_set("healthcheck_loop_alive", False)
            logger.info("Healthcheck-цикл остановлен (cancelled)")
            break
        except Exception as e:
            await safe_set("last_error_time", time.time())
            await safe_set("last_error_message", f"Healthcheck error: {e}")
            logger.error(f"Ошибка в healthcheck-цикле: {e}", exc_info=True)
            await asyncio.sleep(60)


async def format_status_report(db: DatabaseManager) -> str:
    """Форматирует отчёт о состоянии бота для команды /status."""
    stats = db.get_user_statistics()

    # Читаем метрики под локом — атомарный снапшот
    async with metrics_lock:
        uptime = metrics.uptime_str()
        api_health = metrics.api_health_str()
        last_error = metrics.last_error_str()
        healthcheck_alive = metrics.healthcheck_loop_alive
        monitor_alive = metrics.monitor_loop_alive
        discovery_tasks = metrics.discovery_tasks_alive

    healthcheck_status = "✅" if healthcheck_alive else "❌"
    monitor_status = "✅" if monitor_alive else "❌"

    lines = [
        _("status-report-title"),
        "———",
        _("status-uptime").format(uptime=uptime),
        "",
        _("status-users").format(n=stats["total_users"]),
        _("status-patients").format(n=stats["total_patients"]),
        _("status-monitored").format(n=stats["active_monitorings"]),
        _("status-doctors-monitored").format(n=stats["total_monitored_doctors"]),
        "",
        _("status-api-header"),
        f"{api_health}",
        "",
        _("status-tasks-header"),
        _("status-task-healthcheck").format(status=healthcheck_status),
        _("status-task-monitor").format(status=monitor_status),
        _("status-task-discovery").format(n=discovery_tasks),
        "",
        _("status-config-header"),
        _("status-config-check-interval").format(n=settings.CHECK_INTERVAL),
        _("status-config-discovery").format(n=settings.DISCOVERY_INTERVAL),
        _("status-config-threshold").format(
            abs=settings.SLOT_THRESHOLD_ABSOLUTE,
            pct=settings.SLOT_THRESHOLD_PERCENTAGE * 100,
        ),
        _("status-config-default-clinic").format(id=settings.DEFAULT_CLINIC_ID),
        "",
        _("status-last-error").format(err=last_error),
    ]

    return "\n".join(lines)
