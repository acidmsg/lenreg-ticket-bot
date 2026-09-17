"""
Фоновый детектор расхождения пиннинга API-хоста и реального DNS.

Назначение
----------

Мини-приложение и мониторинг отказывают, когда имя API-хоста
(``zdrav.lenreg.ru``) не разрешается штатным DNS-путём. Штатный способ
разрешения имени внутри контейнера бота — пиннинг через ``/etc/hosts``
(``extra_hosts`` в ``docker-compose.yml``): имя разрешается в зафиксированный
IP, минуя деградировавшую DNS-зону, при этом SNI и заголовок ``Host``
сохраняются, а TLS-сертификат проверяется по имени.

Обратная сторона пиннинга — «тихое» устаревание: если провайдер перенесёт API
на другой адрес, бот продолжит обращаться к старому IP и об этом никто не
узнает. Задача модуля — заметить расхождение между пиннингом
(:attr:`settings.api_pinned_ip`) и реальной A-записью зоны и уведомить
администраторов. **Автоматическое изменение инфраструктуры запрещено**:
детектор ничего не правит в ``.env``, ``docker-compose.yml`` и ``/etc/hosts`` —
только фиксирует факт и уведомляет.

Механизм запроса (обход ``/etc/hosts``)
---------------------------------------

Используется ``dns.asyncresolver.Resolver`` из ``dnspython`` с настройками по
умолчанию (``configure=True``): резолвер читает только ``/etc/resolv.conf`` и
отправляет UDP/TCP-запрос серверам, перечисленным в нём (в контейнере это
Docker embedded DNS ``127.0.0.11``, который форвардит запрос аплинкам хоста).
``/etc/hosts`` контейнера не читается и не парсится, поэтому ``getaddrinfo``
(и, следовательно, пиннинг через ``extra_hosts``) в этом пути не участвует.
Ручная сборка DNS-пакета не используется; провайдерные DoH-резолверы, включая
Яндекс-DNS, запрещены.

Известное ограничение: ответ может формироваться встроенным резолвером Docker,
поведение которого относительно записей ``extra_hosts`` проверяется на сервере
отдельной devops-задачей. Детектор сравнивает с пиннингом ровно то, что
возвращает контейнеру штатный DNS-путь.

Режимы работы
-------------

- Совпадение адресов — тишина: ни WARNING-логов, ни метрик, ни уведомлений.
- Расхождение — WARNING-лог с обоими адресами (пин и DNS), инкремент
  ``lenreg_ticket_dns_watchdog_drift_total`` и уведомление администраторам с
  точным действием: обновить ``API_PINNED_IP`` в ``.env`` на сервере и
  пересоздать контейнер (``docker compose up -d bot``).
- Неудача резолва (реальность инцидента: ``SERVFAIL`` / ``EDE 22``) — инкремент
  ``lenreg_ticket_dns_watchdog_zone_unreachable_total`` и WARNING-лог с
  ограничением частоты: первый сбой логируется сразу, далее — не чаще одного
  раза в ``_ZONE_UNREACHABLE_LOG_EVERY_N_CYCLES`` циклов. Неудача резолва —
  не ошибка API: счётчики healthcheck (``api_errors_total``) не изменяются.

Регистрация
-----------

Задача регистрируется в ``BackgroundTaskManager`` (см. ``src/main.py``):
менеджер владеет циклом, расписанием (``dns_watchdog_interval_sec``), retry и
watchdog'ом, а :func:`dns_watchdog_loop` — тело одной итерации.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

import dns.asyncresolver
import dns.exception
from loguru import logger

from src.config import settings
from src.services.error_notifier import error_notifier
from src.services.metrics import prometheus_metrics

# Таймаут одного DNS-запроса в секундах (общий бюджет резолвера, включая retry).
_DNS_QUERY_LIFETIME_SEC = 5.0

# Ограничение частоты логирования недоступности DNS-зоны: первый сбой логируется
# сразу, далее — не чаще одного раза в N циклов.
_ZONE_UNREACHABLE_LOG_EVERY_N_CYCLES = 10

# Точное действие для администратора при расхождении пиннинга и DNS.
_DRIFT_ACTION = (
    "обновить API_PINNED_IP в .env на сервере и пересоздать контейнер "
    "(docker compose up -d bot)"
)


class DnsPinDriftError(RuntimeError):
    """Расхождение зафиксированного IP API и результата реального DNS-запроса."""


@dataclass
class DnsWatchdogState:
    """Мутируемое состояние детектора, живущее между итерациями.

    Создаётся вызывающей стороной (``src/main.py``) и передаётся в
    :func:`dns_watchdog_loop` при каждом вызове: так счётчики частоты
    логирования переживают итерации менеджера фоновых задач.

    Attributes:
        cycles: Общее количество выполненных проверок.
        zone_failures_consecutive: Количество подряд идущих неудач резолва.
    """

    cycles: int = 0
    zone_failures_consecutive: int = 0


def get_api_host() -> str:
    """Возвращает host API из базового URL (единый источник истины).

    Returns:
        Имя хоста без схемы и порта (например, ``zdrav.lenreg.ru``).

    Raises:
        ValueError: ``API_BASE_URL`` не содержит host.
    """
    host = urlparse(settings.API_BASE_URL).hostname
    if not host:
        raise ValueError(f"API_BASE_URL не содержит host: {settings.API_BASE_URL!r}")
    return host


async def resolve_api_host_addresses(host: str) -> set[str]:
    """Разрешает A-записи хоста реальным DNS-запросом (минуя ``/etc/hosts``).

    Args:
        host: Имя хоста (например, ``zdrav.lenreg.ru``).

    Returns:
        Множество IPv4-адресов из ответа DNS.

    Raises:
        dns.exception.DNSException: Запрос не выполнен: ``SERVFAIL``, отсутствие
            достижимых авторитетных серверов, таймаут, ``NXDOMAIN`` и т.п.
    """
    resolver = dns.asyncresolver.Resolver(configure=True)
    resolver.lifetime = _DNS_QUERY_LIFETIME_SEC
    answer = await resolver.resolve(host, "A")
    return {rdata.address for rdata in answer}


async def dns_watchdog_loop(*, state: DnsWatchdogState) -> None:
    """Одна итерация детектора: реальный DNS-запрос против пиннинга.

    Цикл, расписание, retry и watchdog принадлежат ``BackgroundTaskManager``;
    функция выполняет ровно одну проверку и возвращает управление. Неудача
    резолва не является ошибкой итерации и не пробрасывается наружу.

    Args:
        state: Мутируемое состояние между итерациями.
    """
    state.cycles += 1
    host = get_api_host()
    pinned_ip = settings.api_pinned_ip.strip()
    if not pinned_ip:
        logger.warning(
            "DNS-детектор: API_PINNED_IP не задан | Причина: пустое значение "
            "настройки | Действие: проверка расхождения пропущена"
        )
        return

    try:
        resolved = await resolve_api_host_addresses(host)
    except dns.exception.DNSException as exc:
        await _handle_zone_unreachable(state, host, exc)
        return

    state.zone_failures_consecutive = 0

    if pinned_ip in resolved:
        logger.debug(
            "DNS-детектор: пиннинг совпадает с DNS | host={} | ip={}",
            host,
            pinned_ip,
        )
        return

    await _handle_drift(host, pinned_ip, resolved)


async def _handle_zone_unreachable(
    state: DnsWatchdogState,
    host: str,
    error: dns.exception.DNSException,
) -> None:
    """Фиксирует недоступность DNS-зоны: метрика и лог с ограничением частоты.

    Args:
        state: Мутируемое состояние между итерациями.
        host: Имя хоста API.
        error: Исключение резолвера (``SERVFAIL``, таймаут и т.п.).
    """
    state.zone_failures_consecutive += 1
    prometheus_metrics.inc_dns_watchdog_zone_unreachable()

    should_log = (
        state.zone_failures_consecutive == 1
        or state.zone_failures_consecutive % _ZONE_UNREACHABLE_LOG_EVERY_N_CYCLES == 0
    )
    if not should_log:
        return

    logger.opt(exception=error).warning(
        "DNS-детектор: DNS-зона недоступна | host={} | подряд неудач: {} | "
        "Действие: пиннинг через /etc/hosts продолжает работать, "
        "lenreg_ticket_dns_watchdog_zone_unreachable_total +1",
        host,
        state.zone_failures_consecutive,
    )


async def _handle_drift(host: str, pinned_ip: str, resolved: set[str]) -> None:
    """Фиксирует расхождение пиннинга и DNS: лог, метрика, уведомление.

    Args:
        host: Имя хоста API.
        pinned_ip: Зафиксированный IP из настроек.
        resolved: Множество адресов из реального DNS-ответа.
    """
    addresses = ", ".join(sorted(resolved))
    prometheus_metrics.inc_dns_watchdog_drift()
    logger.warning(
        "DNS-детектор: расхождение пиннинга и DNS | host={} | пин={} | dns={} | "
        "Действие: {} | lenreg_ticket_dns_watchdog_drift_total +1",
        host,
        pinned_ip,
        addresses,
        _DRIFT_ACTION,
    )
    await error_notifier.notify(
        DnsPinDriftError(
            f"Расхождение пиннинга и DNS для {host}: пин={pinned_ip}, dns={addresses}"
        ),
        context="DNS-детектор расхождения пиннинга API",
        extra={
            "host": host,
            "pinned_ip": pinned_ip,
            "dns_addresses": addresses,
            "action": _DRIFT_ACTION,
        },
    )
