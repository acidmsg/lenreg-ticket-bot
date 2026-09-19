"""Fallback на закэшированный IP при отказе DNS зоны `lenreg.ru` (TD-025).

Авторитетные NS зоны `lenreg.ru` периодически недоступны, поэтому имя
`zdrav.lenreg.ru` не резолвится с VPS — при живом маршруте до сервера API.
Транспорт запоминает последний успешно разрешённый IP и при отказе DNS
подставляет его в соединение.

Как это устроено:

- каждый запрос к хосту API сначала пробует системный DNS
  (`loop.getaddrinfo`, без блокировки event loop);
- успешный резолв обновляет кэш (в памяти + JSON-файл, чтобы адрес пережил
  перезапуск процесса);
- при отказе DNS используется последний успешный IP: URL переписывается на
  IP, заголовок `Host` сохраняет имя хоста, а расширение `sni_hostname`
  заставляет TLS проверять сертификат строго по имени (MITM-риск исключён);
- если кэша нет, запрос уходит как есть — fail-fast по DNS-ошибке сохраняется.

Транспорт не влияет на rate limiting: лимитеры `aiolimiter` живут в
[`ZdravClient`](zdrav_client.py) и работают до вызова транспорта.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import socket
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import aiofiles
import dns.asyncresolver
import dns.exception
import httpx
from loguru import logger

Resolver = Callable[[], Awaitable[str | None]]
AddressResolver = Callable[[], Awaitable[set[str] | None]]

CACHE_SCHEMA_VERSION: Final[int] = 1
DNS_RESOLVE_TIMEOUT_SECONDS: Final[float] = 5.0


class DnsFallbackTransport(httpx.AsyncBaseTransport):
    """Транспорт httpx с fallback на последний успешный IP хоста API."""

    def __init__(
        self,
        *,
        host: str,
        port: int = 443,
        cache_path: str | Path | None = None,
        delegate: httpx.AsyncBaseTransport | None = None,
        resolver: Resolver | None = None,
        address_resolver: AddressResolver | None = None,
    ) -> None:
        """Настраивает транспорт.

        Args:
            host: имя API-хоста, для которого включён fallback.
            port: порт для проверки DNS-резолва.
            cache_path: путь к JSON-файлу кэша IP (``None`` — только память).
            delegate: нижележащий транспорт (по умолчанию стандартный httpx).
            resolver: функция резолва (для тестов; по умолчанию системный DNS).
            address_resolver: резолв в обход ``/etc/hosts`` (для тестов; по
                умолчанию реальный DNS-запрос).
        """
        self._host = host
        self._port = port
        self._cache_path = Path(cache_path) if cache_path else None
        self._delegate = delegate or httpx.AsyncHTTPTransport()
        self._resolver: Resolver = resolver or self._resolve_via_system_dns
        self._address_resolver: AddressResolver = (
            address_resolver or self._resolve_via_authoritative_dns
        )
        self._cached_ip: str | None = None
        self._cache_loaded = False
        # Адреса, соединение по которым уже не удалось: пиннинг из /etc/hosts
        # остаётся прежним и иначе перетирал бы вылеченный адрес на каждом запросе.
        self._unreachable: set[str] = set()
        self._lock = asyncio.Lock()

    @property
    def cached_ip(self) -> str | None:
        """Последний успешно разрешённый IP (``None`` — кэша нет)."""
        return self._cached_ip

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Обрабатывает запрос: при отказе DNS подставляет кэшированный IP.

        Если соединение по текущему адресу не устанавливается (клиника сменила
        IP, а пиннинг из ``/etc/hosts`` устарел), транспорт ищет актуальный
        адрес реальным DNS-запросом и переключается на него.
        """
        if request.url.host != self._host:
            return await self._delegate.handle_async_request(request)

        resolved = await self._resolver()
        cached = await self._get_cached_ip()
        # Пиннинг из /etc/hosts может быть уже мёртвым: такой адрес не берём и
        # кэш им не затираем, иначе каждый запрос ждёт таймаут соединения.
        attempt_ip = (
            resolved if resolved and resolved not in self._unreachable else cached
        )
        if attempt_ip is None:
            # Fail-fast: ни резолва, ни кэша — исходная ошибка уйдёт наверх.
            return await self._delegate.handle_async_request(request)
        if resolved and resolved == attempt_ip:
            await self._remember_ip(resolved)
            target = request
        else:
            logger.warning(
                "DNS: использую известный рабочий адрес {} для {} (источник: кэш)",
                attempt_ip,
                self._host,
            )
            target = self._rewrite_to_ip(request, attempt_ip)

        try:
            return await self._delegate.handle_async_request(target)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            self._mark_unreachable(attempt_ip)
            switched = await self._switch_to_dns_address(tried_ip=attempt_ip, error=exc)
            if switched is None:
                raise
            return await self._delegate.handle_async_request(
                self._rewrite_to_ip(request, switched)
            )

    def _mark_unreachable(self, ip: str) -> None:
        """Запоминает адрес, соединение по которому не установилось."""
        if ip not in self._unreachable:
            self._unreachable.add(ip)
            logger.warning("DNS: адрес {} для {} помечен недоступным", ip, self._host)

    async def aclose(self) -> None:
        """Закрывает нижележащий транспорт."""
        await self._delegate.aclose()

    async def _resolve_via_system_dns(self) -> str | None:
        """Разрешает имя через системный DNS; ``None`` при ошибке."""
        loop = asyncio.get_running_loop()
        try:
            infos = await asyncio.wait_for(
                loop.getaddrinfo(self._host, self._port, type=socket.SOCK_STREAM),
                timeout=DNS_RESOLVE_TIMEOUT_SECONDS,
            )
        except (socket.gaierror, OSError, TimeoutError) as e:
            logger.warning("DNS: не удалось разрешить {}: {}", self._host, e)
            return None
        if not infos:
            return None
        return str(infos[0][4][0])

    async def _remember_ip(self, ip: str) -> None:
        """Обновляет кэш IP, если адрес изменился."""
        async with self._lock:
            if self._cache_loaded and ip == self._cached_ip:
                return
            changed = self._cached_ip is not None and ip != self._cached_ip
            self._cached_ip = ip
            self._cache_loaded = True
            await self._write_cache(ip)
        if changed:
            logger.info("DNS: адрес {} изменился на {}", self._host, ip)
        else:
            logger.debug("DNS: {} разрешился в {}", self._host, ip)

    async def _get_cached_ip(self) -> str | None:
        """Возвращает кэшированный IP, при первом обращении читая файл."""
        async with self._lock:
            if self._cache_loaded:
                return self._cached_ip
            self._cache_loaded = True
            if self._cached_ip is None and self._cache_path is not None:
                self._cached_ip = await self._read_cache()
            return self._cached_ip

    async def _read_cache(self) -> str | None:
        """Читает IP из файла кэша; повреждённый файл игнорируется."""
        if self._cache_path is None or not self._cache_path.is_file():
            return None
        try:
            async with aiofiles.open(self._cache_path, encoding="utf-8") as stream:
                payload = json.loads(await stream.read())
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("DNS: не удалось прочитать кэш {}: {}", self._cache_path, e)
            return None
        if payload.get("version") != CACHE_SCHEMA_VERSION:
            logger.warning(
                "DNS: кэш {} имеет неизвестную версию схемы — игнорирую",
                self._cache_path,
            )
            return None
        if payload.get("host") != self._host:
            return None
        ip = payload.get("ip")
        return str(ip) if ip else None

    async def _write_cache(self, ip: str) -> None:
        """Сохраняет IP в файл кэша; ошибка записи не критична."""
        if self._cache_path is None:
            return
        payload: dict[str, Any] = {
            "version": CACHE_SCHEMA_VERSION,
            "host": self._host,
            "ip": ip,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(self._cache_path, "w", encoding="utf-8") as stream:
                await stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.warning("DNS: не удалось сохранить кэш {}: {}", self._cache_path, e)

    def _inc_switch_metric(self) -> None:
        """Инкрементирует счётчик переключений на новый IP (ленивый импорт).

        Импорт внутри функции: ``src.services.metrics`` косвенно тянет
        ``src.api.zdrav_client``, поэтому импорт на уровне модуля дал бы цикл.
        """
        try:
            from src.services.metrics import prometheus_metrics
        except ImportError:  # pragma: no cover - транспорт работает и без метрик
            return
        prometheus_metrics.inc_dns_fallback_switch()

    async def _resolve_via_authoritative_dns(self) -> set[str] | None:
        """Разрешает A-записи хоста реальным DNS-запросом в обход ``/etc/hosts``.

        В контейнере имя API закреплено через ``extra_hosts``, поэтому системный
        резолв всегда возвращает пиннинг и смену адреса клиникой не покажет.

        Returns:
            Множество адресов либо ``None``, если запрос не удался.
        """
        resolver = dns.asyncresolver.Resolver(configure=True)
        resolver.lifetime = DNS_RESOLVE_TIMEOUT_SECONDS
        try:
            answer = await resolver.resolve(self._host, "A")
        except (dns.exception.DNSException, OSError) as exc:
            logger.warning("DNS: обходной резолв {} не удался: {}", self._host, exc)
            return None
        addresses = {rdata.address for rdata in answer}
        return addresses or None

    async def _switch_to_dns_address(
        self, *, tried_ip: str | None, error: Exception
    ) -> str | None:
        """Ищет актуальный адрес и переключается на него.

        Вызывается, когда соединение по адресу ``tried_ip`` (пиннинг или кэш) не
        установлено: клиника могла сменить IP, а запись в ``/etc/hosts`` остаться
        прежней. Найденный адрес попадает в кэш, поэтому следующие запросы идут
        уже по нему — ручная правка ``API_PINNED_IP`` не требуется.

        Параллельные запросы не мешают друг другу: если другой запрос уже нашёл
        рабочий адрес (он лежит в кэше и отличается от ``tried_ip``), берётся он -
        без повторного DNS-запроса и без исключения наверх.

        Args:
            tried_ip: Адрес, по которому соединение не установилось.
            error: Исключение соединения, из-за которого запущено лечение.

        Returns:
            Рабочий IP либо ``None``, если переключаться не на что.
        """
        cached = await self._get_cached_ip()
        if cached and cached != tried_ip and cached not in self._unreachable:
            logger.warning(
                "DNS: переключаюсь на уже найденный адрес {} | host={}",
                cached,
                self._host,
            )
            return cached

        addresses = await self._address_resolver()
        if not addresses:
            return None
        new_ip = next(
            (
                ip
                for ip in sorted(addresses)
                if ip != tried_ip and ip not in self._unreachable
            ),
            None,
        )
        if new_ip is None:
            return None
        await self._remember_ip(new_ip)
        self._inc_switch_metric()
        logger.warning(
            "DNS: соединение по {} не установлено ({}), переключаюсь на {} "
            "из DNS-ответа | host={} | действие: пиннинг API_PINNED_IP можно "
            "обновить позже, бот работает по фактическому адресу",
            tried_ip or "пиннингу",
            type(error).__name__,
            new_ip,
            self._host,
        )
        return new_ip

    def _rewrite_to_ip(self, request: httpx.Request, ip: str) -> httpx.Request:
        """Копирует запрос на IP с сохранением Host и SNI-имени."""
        extensions = dict(request.extensions)
        extensions["sni_hostname"] = self._host
        headers = httpx.Headers(request.headers)
        headers["Host"] = request.url.netloc.decode("ascii")
        kwargs: dict[str, Any] = {}
        with contextlib.suppress(httpx.RequestNotRead):
            kwargs["content"] = request.content
        if "content" not in kwargs:
            kwargs["stream"] = request.stream
        return httpx.Request(
            method=request.method,
            url=request.url.copy_with(host=ip),
            headers=headers,
            extensions=extensions,
            **kwargs,
        )
