"""
Модуль мониторинга здоровья бота.

Предоставляет:
1. Команду /status — отдаёт текущее состояние бота
2. Фоновый healthcheck-цикл — периодически проверяет API zdrav.lenreg.ru
3. Healthcheck-метрики для логирования
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from aiogram import Bot

from api.zdrav_client import ZdravClient
from config import settings
from database.database import Database
from database.manager import DatabaseManager

logger = logging.getLogger(__name__)


@dataclass
class HealthMetrics:
    """Сборщик метрик здоровья бота."""

    # Когда запущен
    start_time: float = field(default_factory=time.time)

    # Статистика API
    api_checks_total: int = 0
    api_errors_total: int = 0
    api_success_total: int = 0
    last_api_check_time: Optional[float] = None
    last_api_error_time: Optional[float] = None
    last_api_error_message: str = ""

    # Статистика мониторинга
    monitoring_slots_checked: int = 0
    monitoring_notifications_sent: int = 0
    last_monitoring_cycle_time: Optional[float] = None

    # Состояние фоновых задач
    discovery_tasks_alive: int = 0
    monitor_loop_alive: bool = False
    healthcheck_loop_alive: bool = False

    # Ошибки
    last_error_time: Optional[float] = None
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
        if self.api_checks_total == 0:
            return "❓ Нет данных"
        success_rate = (self.api_success_total / self.api_checks_total) * 100
        if success_rate == 100:
            return f"✅ {success_rate:.0f}% успешных (всего {self.api_checks_total})"
        elif success_rate >= 80:
            return f"⚠️ {success_rate:.0f}% успешных ({self.api_errors_total} ошибок из {self.api_checks_total})"
        else:
            return f"❌ {success_rate:.0f}% успешных ({self.api_errors_total} ошибок из {self.api_checks_total})"

    def last_error_str(self) -> str:
        if not self.last_error_message:
            return "—"
        delta = int(time.time() - (self.last_error_time or 0))
        return f"{self.last_error_message} ({delta}с назад)"


# Глобальный экземпляр метрик
metrics = HealthMetrics()
_metrics_lock = asyncio.Lock()


async def _safe_increment(attr: str, delta: int = 1):
    """Атомарный инкремент поля metrics (под локом)."""
    async with _metrics_lock:
        current = getattr(metrics, attr, 0)
        setattr(metrics, attr, current + delta)


async def _safe_set(attr: str, value):
    """Атомарная установка поля metrics (под локом)."""
    async with _metrics_lock:
        setattr(metrics, attr, value)


async def healthcheck_loop(bot: Bot, api: ZdravClient, db: DatabaseManager):
    """
    Фоновый цикл проверки здоровья.

    Каждые CHECK_INTERVAL секунд:
    1. Проверяет доступность API zdrav.lenreg.ru через все активные клиники
    2. Собирает статистику
    3. Логирует состояние
    """
    await _safe_set("healthcheck_loop_alive", True)
    logger.info("Healthcheck-цикл запущен")

    # Кэш clinic_id → patient_id для healthcheck (заполняется на первом цикле)
    _patient_for_clinic: dict[str, str] = {}

    while True:
        try:
            await asyncio.sleep(settings.CHECK_INTERVAL)  # каждые 5 минут

            # Получаем список активных клиник из БД
            database = db._db
            clinic_ids = await database.get_active_clinic_ids()
            if not clinic_ids:
                # Фоллбэк на DEFAULT_CLINIC_ID, если таблица пуста
                clinic_ids = [settings.DEFAULT_CLINIC_ID]

            # Проверяем API для каждой активной клиники (R4)
            for clinic_id in clinic_ids:
                try:
                    # Определяем patient_id для этой клиники
                    if clinic_id not in _patient_for_clinic:
                        ctype = await database.get_clinic_type(str(clinic_id))
                        if ctype == "child":
                            _patient_for_clinic[clinic_id] = (
                                settings.DISCOVERY_PATIENT_ID_CHILD
                            )
                        else:
                            _patient_for_clinic[clinic_id] = (
                                settings.DISCOVERY_PATIENT_ID_ADULT
                            )

                    patient_id = _patient_for_clinic[clinic_id]

                    await _safe_increment("api_checks_total")
                    specialties = await api.fetch_speciality_list(
                        patient_id,
                        str(clinic_id),
                        limiter=api.limiter_healthcheck,
                    )
                    if specialties is not None:
                        await _safe_increment("api_success_total")
                    else:
                        await _safe_increment("api_errors_total")
                        await _safe_set("last_api_error_time", time.time())
                        await _safe_set("last_api_error_message", "API вернул None")
                    await _safe_set("last_api_check_time", time.time())
                except Exception as e:
                    await _safe_increment("api_errors_total")
                    await _safe_set("last_api_error_time", time.time())
                    await _safe_set("last_api_error_message", str(e)[:200])
                    logger.error(
                        f"Healthcheck: ошибка API для клиники {clinic_id}: {e}"
                    )

            # Собираем статистику по БД (под локом для чтения metrics)
            async with _metrics_lock:
                uptime = metrics.uptime_str()
                api_health = metrics.api_health_str()

            total_users = len(db.data)
            total_monitored_doctors = sum(
                len(u_info.get("monitoring", {})) for u_info in db.data.values()
            )
            total_patients = sum(
                len(u_info.get("patients", {})) for u_info in db.data.values()
            )

            # Логируем состояние
            logger.info(
                f"Healthcheck | "
                f"Uptime: {uptime} | "
                f"Clinics checked: {len(clinic_ids)} | "
                f"Users: {total_users} | "
                f"Patients: {total_patients} | "
                f"Monitored: {total_monitored_doctors} | "
                f"API: {api_health}"
            )

        except asyncio.CancelledError:
            await _safe_set("healthcheck_loop_alive", False)
            logger.info("Healthcheck-цикл остановлен (cancelled)")
            break
        except Exception as e:
            await _safe_set("last_error_time", time.time())
            await _safe_set("last_error_message", f"Healthcheck error: {e}")
            logger.error(f"Ошибка в healthcheck-цикле: {e}", exc_info=True)
            await asyncio.sleep(60)


def format_status_report(db: DatabaseManager) -> str:
    """Форматирует отчёт о состоянии бота для команды /status."""
    total_users = len(db.data)
    total_patients = sum(len(u_info.get("patients", {})) for u_info in db.data.values())
    total_monitored_doctors = sum(
        len(u_info.get("monitoring", {})) for u_info in db.data.values()
    )

    # Считаем количество активных мониторингов (врачей с возможными номерками)
    active_monitorings = sum(
        1
        for u_info in db.data.values()
        for p_id, doctors in u_info.get("monitoring", {}).items()
        if doctors
    )

    lines = [
        f"🤖 **lenreg_ticket_bot**",
        f"———",
        f"⏱ **Аптайм:** {metrics.uptime_str()}",
        f"",
        f"📊 **Пользователи:** {total_users}",
        f"├ Пациентов: {total_patients}",
        f"├ В мониторинге: {active_monitorings}",
        f"└ Врачей под мониторингом: {total_monitored_doctors}",
        f"",
        f"🌐 **API zdrav.lenreg.ru:**",
        f"{metrics.api_health_str()}",
        f"",
        f"🔄 **Фоновые задачи:**",
        f"├ Healthcheck: {'✅' if metrics.healthcheck_loop_alive else '❌'}",
        f"├ Monitor: {'✅' if metrics.monitor_loop_alive else '❌'}",
        f"└ Discovery: {metrics.discovery_tasks_alive} задач",
        f"",
        f"⚙️ **Настройки:**",
        f"├ Интервал проверки: {settings.CHECK_INTERVAL}с",
        f"├ Discovery: {settings.DISCOVERY_INTERVAL}с",
        f"├ Порог слотов: {settings.SLOT_THRESHOLD_ABSOLUTE} шт / {settings.SLOT_THRESHOLD_PERCENTAGE*100:.0f}%",
        f"└ Клиника по умолчанию: {settings.DEFAULT_CLINIC_ID}",
        f"",
        f"⚠️ **Последняя ошибка:** {metrics.last_error_str()}",
    ]

    return "\n".join(lines)
