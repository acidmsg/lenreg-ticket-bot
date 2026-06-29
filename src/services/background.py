"""
Менеджер фоновых asyncio-задач.

Централизованное управление фоновыми циклами бота: мониторинг, discovery,
healthcheck, cleanup. Владеет циклом ``while True`` — корутина становится
телом одной итерации. Заменяет ручной ``while True`` + ``try/except CancelledError``
+ ``except Exception: sleep(N)`` в каждом из циклов.

Возможности:
- Декларативное расписание (интервал + jitter)
- Retry с exponential backoff
- Watchdog с ограничением частоты перезапусков
- Prometheus-метрики (опционально)
- Graceful shutdown (cancel + gather с таймаутом)

Использование:
    manager = BackgroundTaskManager()
    manager.add(my_coro, name="my_task", schedule=ScheduleConfig(interval=60))
    await manager.start_all()
    # ... бот работает ...
    await manager.stop_all()
"""

from __future__ import annotations

import asyncio
import enum
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from loguru import logger
from prometheus_client import Counter, Gauge, Histogram

# ══════════════════════════════════════════════════════════════════════════════
# Конфигурационные dataclass'ы
# ══════════════════════════════════════════════════════════════════════════════


@dataclass
class ScheduleConfig:
    """Расписание запуска фоновой задачи.

    Attributes:
        interval: Базовый интервал между итерациями в секундах.
        jitter: Диапазон случайного разброса (min, max) в секундах.
                Если задан — ``interval`` игнорируется, используется
                ``random.uniform(jitter[0], jitter[1])``.
    """

    interval: float
    jitter: tuple[float, float] | None = None


@dataclass
class RetryConfig:
    """Параметры retry с exponential backoff.

    Attributes:
        max_retries: Максимум последовательных ошибок перед остановкой.
        backoff_base: Множитель задержки:
            ``delay = backoff_min * (backoff_base ** attempt)``.
        backoff_min: Минимальная задержка retry в секундах.
        backoff_max: Потолок задержки retry в секундах.
    """

    max_retries: int = 3
    backoff_base: float = 2.0
    backoff_min: float = 1.0
    backoff_max: float = 300.0


@dataclass
class WatchdogConfig:
    """Параметры watchdog (перезапуск при крахе).

    Если за последние ``restart_window`` секунд было больше ``max_restarts``
    перезапусков — задача останавливается с состоянием ``CRASHED``.

    Attributes:
        max_restarts: Максимум перезапусков в окне.
        restart_window: Окно в секундах.
    """

    max_restarts: int = 5
    restart_window: float = 300.0


# ══════════════════════════════════════════════════════════════════════════════
# Перечисление состояний задачи
# ══════════════════════════════════════════════════════════════════════════════


class TaskState(enum.Enum):
    """Состояния жизненного цикла фоновой задачи."""

    IDLE = "idle"  # Зарегистрирована, но не запущена
    RUNNING = "running"  # Выполняется итерация
    SLEEPING = "sleeping"  # Ожидание между итерациями (интервал / jitter)
    RETRYING = "retrying"  # Ожидание перед retry (backoff)
    STOPPING = "stopping"  # Получен CancelledError, завершаемся
    STOPPED = "stopped"  # Успешно остановлена
    CRASHED = "crashed"  # Аварийно остановлена (watchdog превышен / retry исчерпан)


# ══════════════════════════════════════════════════════════════════════════════
# Dataclass статуса задачи (возвращается manager.status())
# ══════════════════════════════════════════════════════════════════════════════


@dataclass
class TaskStatus:
    """Снапшот текущего состояния фоновой задачи."""

    state: TaskState
    iterations: int
    successes: int
    failures: int
    consecutive_errors: int
    restarts: int
    last_run_start: float | None
    last_run_duration: float | None
    created_at: float


# ══════════════════════════════════════════════════════════════════════════════
# Метрики Prometheus (синглтоны на уровне модуля — создаются один раз)
# ══════════════════════════════════════════════════════════════════════════════

_BG_ITERATIONS = Counter(
    "lenreg_ticket_bg_task_iterations_total",
    "Счётчик итераций фоновой задачи",
    labelnames=["task", "status"],
)
_BG_DURATION = Histogram(
    "lenreg_ticket_bg_task_duration_seconds",
    "Длительность итерации фоновой задачи",
    labelnames=["task"],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300],
)
_BG_RESTARTS = Counter(
    "lenreg_ticket_bg_task_restarts_total",
    "Счётчик перезапусков фоновой задачи",
    labelnames=["task"],
)
_BG_ERRORS_CONSECUTIVE = Gauge(
    "lenreg_ticket_bg_task_errors_consecutive",
    "Текущее количество последовательных ошибок",
    labelnames=["task"],
)


# ══════════════════════════════════════════════════════════════════════════════
# Внутренний класс: метрики одной задачи
# ══════════════════════════════════════════════════════════════════════════════


class _TaskMetrics:
    """Обёртка над 4 Prometheus-метриками для одной фоновой задачи.

    Создаётся лениво при первом запуске задачи, если ``metrics=True``.
    Использует модульные синглтоны метрик — не создаёт новых при каждом вызове.
    """

    def __init__(self, task_name: str) -> None:
        self.task_name: str = task_name
        self.iterations: Counter = _BG_ITERATIONS
        self.duration: Histogram = _BG_DURATION
        self.restarts: Counter = _BG_RESTARTS
        self.errors_consecutive: Gauge = _BG_ERRORS_CONSECUTIVE


# ══════════════════════════════════════════════════════════════════════════════
# BackgroundTask — одна фоновая задача
# ══════════════════════════════════════════════════════════════════════════════


class BackgroundTask:
    """Представление одной зарегистрированной фоновой задачи.

    Хранит конфигурацию, состояние, статистику и ссылку на ``asyncio.Task``.
    Экземпляры создаются только через ``BackgroundTaskManager.add()``.
    """

    __slots__ = (
        "_asyncio_task",
        "_consecutive_errors",
        "_coro_fn",
        "_coro_kwargs",
        "_created_at",
        "_failures",
        "_first_error_logged",
        "_iterations",
        "_last_run_duration",
        "_last_run_start",
        "_metrics",
        "_metrics_enabled",
        "_restart_timestamps",
        "_restarts",
        "_state",
        "_stop_event",
        "_successes",
        "name",
        "retry",
        "schedule",
        "watchdog",
    )

    def __init__(
        self,
        name: str,
        coro_fn: Callable[..., Awaitable[None]],
        schedule: ScheduleConfig,
        retry: RetryConfig | None,
        watchdog: WatchdogConfig | None,
        metrics_enabled: bool,
        coro_kwargs: dict[str, Any],
    ) -> None:
        self.name = name
        self._coro_fn = coro_fn
        self._coro_kwargs = coro_kwargs
        self.schedule = schedule
        self.retry = retry
        self.watchdog = watchdog
        self._metrics_enabled = metrics_enabled

        # Управление жизненным циклом
        self._stop_event = asyncio.Event()
        self._asyncio_task: asyncio.Task[None] | None = None

        # Состояние
        self._state = TaskState.IDLE
        self._iterations = 0
        self._successes = 0
        self._failures = 0
        self._consecutive_errors = 0
        self._restarts = 0
        self._last_run_start: float | None = None
        self._last_run_duration: float | None = None
        self._created_at = time.time()

        # Watchdog: скользящее окно временны́х меток перезапусков
        self._restart_timestamps: list[float] = []

        # Метрики (ленивая инициализация при первом запуске)
        self._metrics: _TaskMetrics | None = None

        # Флаг: логировать ли следующую ошибку с exc_info=True
        # (только первая ошибка в цепочке)
        self._first_error_logged = False

    # ── Свойства ────────────────────────────────────────────────────────

    @property
    def state(self) -> TaskState:
        """Текущее состояние задачи."""
        return self._state

    @state.setter
    def state(self, value: TaskState) -> None:
        self._state = value

    @property
    def asyncio_task(self) -> asyncio.Task[None] | None:
        """Ссылка на нижележащий ``asyncio.Task`` (может быть None)."""
        return self._asyncio_task

    # ── Публичный метод ─────────────────────────────────────────────────

    def cancel(self) -> None:
        """Запросить graceful shutdown задачи.

        Устанавливает стоп-событие и отменяет ``asyncio.Task``.
        Не ждёт завершения — для этого используй ``stop_all()`` менеджера.
        """
        self._stop_event.set()
        if self._asyncio_task and not self._asyncio_task.done():
            self._asyncio_task.cancel()

    # ── Формирование статуса ────────────────────────────────────────────

    def get_status(self) -> TaskStatus:
        """Возвращает снапшот текущего состояния задачи."""
        return TaskStatus(
            state=self._state,
            iterations=self._iterations,
            successes=self._successes,
            failures=self._failures,
            consecutive_errors=self._consecutive_errors,
            restarts=self._restarts,
            last_run_start=self._last_run_start,
            last_run_duration=self._last_run_duration,
            created_at=self._created_at,
        )


# ══════════════════════════════════════════════════════════════════════════════
# BackgroundTaskManager — центральный реестр фоновых задач
# ══════════════════════════════════════════════════════════════════════════════


class BackgroundTaskManager:
    """Центральный реестр фоновых задач.

    Создаётся один экземпляр в ``main.py`` при старте бота.

    Использование:
        manager = BackgroundTaskManager()
        manager.add(my_coro, name="monitor", schedule=ScheduleConfig(jitter=(42, 85)))
        await manager.start_all()
        # ...
        await manager.stop_all()
    """

    def __init__(self) -> None:
        self._tasks: dict[str, BackgroundTask] = {}

    # ── Регистрация ─────────────────────────────────────────────────────

    def add(
        self,
        coro_fn: Callable[..., Awaitable[None]],
        *,
        name: str,
        schedule: ScheduleConfig,
        retry: RetryConfig | None = None,
        watchdog: WatchdogConfig | None = None,
        metrics: bool = True,
        **coro_kwargs: Any,
    ) -> None:
        """Зарегистрировать фоновую задачу. **Не запускает** — запуск в ``start_all()``.

        Args:
            coro_fn: Асинхронная функция одной итерации.
            name: Уникальное имя задачи (лейбл в метриках, ключ в ``status()``).
            schedule: Расписание: интервал и jitter.
            retry: Параметры retry с backoff (None — без retry).
            watchdog: Параметры watchdog (None — без перезапуска).
            metrics: Включить Prometheus-метрики для этой задачи.
            **coro_kwargs: Именованные аргументы, передаваемые в ``coro_fn``
                          при каждом вызове.

        Raises:
            ValueError: Если задача с таким ``name`` уже зарегистрирована.
        """
        if name in self._tasks:
            raise ValueError(f"Фоновая задача с именем '{name}' уже зарегистрирована")

        if retry is None:
            retry = RetryConfig()
        if watchdog is None:
            watchdog = WatchdogConfig()

        task = BackgroundTask(
            name=name,
            coro_fn=coro_fn,
            schedule=schedule,
            retry=retry,
            watchdog=watchdog,
            metrics_enabled=metrics,
            coro_kwargs=coro_kwargs,
        )
        self._tasks[name] = task
        logger.debug(f"Background task '{name}' registered")

    # ── Запуск ───────────────────────────────────────────────────────────

    async def start_all(self) -> None:
        """Запустить все зарегистрированные задачи конкурентно.

        Создаёт ``asyncio.Task`` для каждой задачи. Не ждёт завершения —
        возвращает управление сразу.
        """
        for task in self._tasks.values():
            if task.state != TaskState.IDLE:
                logger.warning(
                    f"Background task '{task.name}' is not IDLE (state={task.state}), "
                    f"skipping start"
                )
                continue

            # Ленивая инициализация метрик
            if task._metrics_enabled and task._metrics is None:
                task._metrics = _TaskMetrics(task.name)

            task._asyncio_task = asyncio.create_task(self._run_task(task))
            logger.info(f"Background task '{task.name}' started")

    # ── Остановка ────────────────────────────────────────────────────────

    async def stop_all(self, shutdown_timeout: float = 30.0) -> None:
        """Graceful shutdown всех фоновых задач.

        1. Устанавливает ``_stop_event`` для каждой задачи.
        2. Отменяет все ``asyncio.Task``.
        3. Ждёт завершения через ``asyncio.gather(return_exceptions=True)``
           с суммарным таймаутом ``shutdown_timeout``.

        Args:
            shutdown_timeout: Суммарный таймаут в секундах на остановку всех задач.
        """
        logger.info("Stopping all background tasks...")

        # 1. Установить stop events
        for task in self._tasks.values():
            task._stop_event.set()

        # 2. Отменить asyncio-задачи
        asyncio_tasks: list[asyncio.Task[None]] = []
        for task in self._tasks.values():
            if task._asyncio_task and not task._asyncio_task.done():
                task._asyncio_task.cancel()
                asyncio_tasks.append(task._asyncio_task)

        if not asyncio_tasks:
            logger.info("No active background tasks to stop")
            return

        # 3. Ожидание с таймаутом
        try:
            await asyncio.wait_for(
                asyncio.gather(*asyncio_tasks, return_exceptions=True),
                timeout=shutdown_timeout,
            )
        except TimeoutError:
            logger.warning(
                f"Shutdown timeout ({shutdown_timeout}s), "
                f"some tasks may not have stopped cleanly"
            )

        # Убедиться, что все задачи в финальном состоянии
        for task in self._tasks.values():
            if task.state not in (TaskState.STOPPED, TaskState.CRASHED, TaskState.IDLE):
                task.state = TaskState.STOPPED

        logger.info("All background tasks stopped")

    # ── Статус ───────────────────────────────────────────────────────────

    def status(self) -> dict[str, TaskStatus]:
        """Возвращает словарь ``{name: TaskStatus}`` с текущим состоянием всех задач.

        Используется для веб-дашборда и отладки.
        """
        return {name: task.get_status() for name, task in self._tasks.items()}

    # ── Внутренний цикл задачи ───────────────────────────────────────────

    async def _run_task(self, task: BackgroundTask) -> None:
        """Основной цикл одной фоновой задачи.

        Бесконечный цикл: выполнить итерацию → sleep/jitter → повторить.
        При ошибке: retry с backoff → если исчерпан → watchdog → CRASHED.
        """
        while not task._stop_event.is_set():
            # ── RUNNING: выполнение итерации ─────────────────────────
            task.state = TaskState.RUNNING
            task._last_run_start = time.monotonic()

            try:
                await task._coro_fn(**task._coro_kwargs)
            except asyncio.CancelledError:
                task.state = TaskState.STOPPING
                break
            except Exception as exc:
                # ── Ошибка в итерации ───────────────────────────────
                task._iterations += 1
                task._failures += 1
                task._consecutive_errors += 1

                if task._metrics:
                    task._metrics.iterations.labels(
                        task=task.name, status="error"
                    ).inc()
                    task._metrics.errors_consecutive.labels(task=task.name).set(
                        task._consecutive_errors
                    )

                # Логируем с exc_info только первую ошибку в цепочке
                max_retries_display = task.retry.max_retries if task.retry else "?"
                if not task._first_error_logged:
                    logger.opt(exception=True).warning(
                        f"Task '{task.name}': iteration failed "
                        f"(attempt {task._consecutive_errors}/"
                        f"{max_retries_display}): {exc}"
                    )
                    task._first_error_logged = True
                else:
                    logger.warning(
                        f"Task '{task.name}': iteration failed "
                        f"(attempt {task._consecutive_errors}/"
                        f"{max_retries_display}): {exc}"
                    )

                # ── RETRY с backoff ─────────────────────────────────
                if (
                    task.retry is not None
                    and task._consecutive_errors <= task.retry.max_retries
                ):
                    task.state = TaskState.RETRYING
                    attempt_index = task._consecutive_errors - 1  # 0-based
                    delay = min(
                        task.retry.backoff_min
                        * (task.retry.backoff_base**attempt_index),
                        task.retry.backoff_max,
                    )
                    logger.warning(
                        f"Task '{task.name}': retrying in {delay:.1f}s "
                        f"(attempt {task._consecutive_errors}/{task.retry.max_retries})"
                    )
                    try:
                        await asyncio.wait_for(task._stop_event.wait(), timeout=delay)
                        # Стоп-событие установлено во время backoff
                        if task._stop_event.is_set():
                            task.state = TaskState.STOPPING
                            break
                    except TimeoutError:
                        # Backoff истёк — продолжаем цикл (retry)
                        continue
                    except asyncio.CancelledError:
                        task.state = TaskState.STOPPING
                        break
                else:
                    # ── Retry исчерпан (или нет retry) → CRASHED ─────
                    task.state = TaskState.CRASHED
                    task._restarts += 1

                    if task._metrics:
                        task._metrics.restarts.labels(task=task.name).inc()

                    # Watchdog: скользящее окно
                    if task.watchdog is not None:
                        now = time.monotonic()
                        task._restart_timestamps.append(now)
                        cutoff = now - task.watchdog.restart_window
                        task._restart_timestamps = [
                            t for t in task._restart_timestamps if t > cutoff
                        ]
                        restart_count = len(task._restart_timestamps)

                        if restart_count <= task.watchdog.max_restarts:
                            logger.warning(
                                f"Task '{task.name}': crashed, restarting "
                                f"(restart {restart_count}/"
                                f"{task.watchdog.max_restarts} "
                                f"in {task.watchdog.restart_window:.0f}s"
                                f" window)"
                            )
                            task.state = TaskState.RUNNING
                            task._first_error_logged = False
                            continue  # Немедленный перезапуск

                    # Watchdog превышен или отсутствует
                    if task.retry is not None:
                        logger.critical(
                            f"Task '{task.name}': max retries "
                            f"({task.retry.max_retries}) exceeded, CRASHED"
                        )
                    if task.watchdog is not None:
                        logger.critical(
                            f"Task '{task.name}': max restarts "
                            f"({task.watchdog.max_restarts}) in "
                            f"{task.watchdog.restart_window:.0f}s exceeded, CRASHED"
                        )
                    break
            else:
                # ── Успешная итерация ────────────────────────────────
                task._last_run_duration = time.monotonic() - task._last_run_start
                task._iterations += 1
                task._successes += 1

                if task._metrics:
                    task._metrics.iterations.labels(
                        task=task.name, status="success"
                    ).inc()
                    task._metrics.duration.labels(task=task.name).observe(
                        task._last_run_duration
                    )

                # Сброс счётчика последовательных ошибок после успеха
                task._consecutive_errors = 0
                task._first_error_logged = False
                if task._metrics:
                    task._metrics.errors_consecutive.labels(task=task.name).set(0)

                logger.debug(
                    f"Task '{task.name}': iteration #{task._iterations} OK "
                    f"({task._last_run_duration:.1f}s)"
                )

                # ── SLEEPING: ожидание между итерациями ──────────────
                task.state = TaskState.SLEEPING

                if task.schedule.jitter is not None:
                    sleep_time = random.uniform(*task.schedule.jitter)
                else:
                    sleep_time = task.schedule.interval

                try:
                    await asyncio.wait_for(task._stop_event.wait(), timeout=sleep_time)
                    # Стоп-событие установлено во время сна
                    if task._stop_event.is_set():
                        task.state = TaskState.STOPPING
                        break
                except TimeoutError:
                    # Сон истёк — следующая итерация
                    continue
                except asyncio.CancelledError:
                    task.state = TaskState.STOPPING
                    break

        # ── Пост-цикл: финализация состояния ─────────────────────────────
        if task.state == TaskState.STOPPING or (
            task._stop_event.is_set() and task.state != TaskState.CRASHED
        ):
            task.state = TaskState.STOPPED
            logger.info(
                f"Task '{task.name}': stopped. "
                f"Stats: {task._iterations} iters, "
                f"{task._failures} errors, {task._restarts} restarts"
            )


# ══════════════════════════════════════════════════════════════════════════════
# Публичный API
# ══════════════════════════════════════════════════════════════════════════════

__all__ = [
    "BackgroundTask",
    "BackgroundTaskManager",
    "RetryConfig",
    "ScheduleConfig",
    "TaskState",
    "TaskStatus",
    "WatchdogConfig",
]
