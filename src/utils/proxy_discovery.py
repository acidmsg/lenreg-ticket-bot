"""
Модуль автоопределения SOCKS5-прокси.

Сканирует Docker/WSL gateway-адреса в диапазоне 172.17.0.0 – 172.31.255.0
(RFC 1918) для обнаружения активного прокси-сервера.
"""

from __future__ import annotations

import asyncio
import re

from loguru import logger

# Параметры автоопределения прокси
PROXY_DISCOVERY_PORT: int = 10808
PROXY_DISCOVERY_CONCURRENT: int = 50
PROXY_DISCOVERY_HOST_TIMEOUT: float = 0.5  # секунд на один хост


def _parse_proxy_host_port(proxy_url: str) -> tuple[str, int]:
    """Извлекает host:port из socks5://host:port строки."""
    stripped = re.sub(r"^[a-z0-9]+://", "", proxy_url)
    host, _, port_str = stripped.partition(":")
    return host, int(port_str) if port_str else 1080


async def _probe_host(host: str, port: int, sem: asyncio.Semaphore) -> str | None:
    """
    Проверяет TCP-соединение с хостом; возвращает host или None.

    Используется для параллельного сканирования — каждый вызов ограничен
    семафором (конкурентность) и таймаутом на соединение.
    """
    async with sem:
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=PROXY_DISCOVERY_HOST_TIMEOUT,
            )
            writer.close()
            await writer.wait_closed()
            return host
        except (TimeoutError, OSError):
            return None


def _generate_docker_gateways() -> list[str]:
    """
    Генерирует список возможных Docker/WSL gateway-адресов.

    Фаза 1: стандартные /16 gateway (.0.1) — 15 адресов (быстро).
    Фаза 2: расширенный пул /20 gateway (.Y.1, шаг 16) — все комбинации
             в диапазоне 172.17.0.0 – 172.31.255.0 (RFC 1918).
    """
    gateways: list[str] = []
    # Фаза 1: стандартные /16
    for second in range(17, 32):
        gateways.append(f"172.{second}.0.1")
    # Фаза 2: все /20 подсети
    for second in range(17, 32):
        for third in range(0, 256, 16):
            gw = f"172.{second}.{third}.1"
            if gw not in gateways:
                gateways.append(gw)
    return gateways


async def discover_proxy(port: int = PROXY_DISCOVERY_PORT) -> str | None:
    """
    Параллельное сканирование Docker gateway'ев на наличие SOCKS5 прокси.

    Сканирует IP из диапазона 172.17.0.0 – 172.31.255.0 (RFC 1918)
    на заданном порту. Возвращает socks5://host:port или None,
    если прокси не найден.
    """
    gateways = _generate_docker_gateways()
    logger.info(
        f"Сканирование прокси: {len(gateways)} адресов "
        f"(конкурентность {PROXY_DISCOVERY_CONCURRENT}, "
        f"таймаут {PROXY_DISCOVERY_HOST_TIMEOUT}с)..."
    )
    sem = asyncio.Semaphore(PROXY_DISCOVERY_CONCURRENT)
    tasks = [asyncio.ensure_future(_probe_host(gw, port, sem)) for gw in gateways]
    for coro in asyncio.as_completed(tasks):
        host = await coro
        if host is not None:
            proxy_url = f"socks5://{host}:{port}"
            logger.info(f"Прокси найден: {proxy_url}")
            # Отменяем оставшиеся проверки
            for t in tasks:
                t.cancel()
            return proxy_url

    logger.warning("Прокси не найден ни на одном из проверенных адресов")
    return None


async def check_proxy_connectivity(
    proxy_url: str, connect_timeout: float = 5.0
) -> None:
    """
    Предварительная проверка TCP-соединения с прокси-сервером.

    Быстрый healthcheck, чтобы дать понятную ошибку до того, как начнём
    создавать сессию и запускать фоновые задачи.
    """
    host, port = _parse_proxy_host_port(proxy_url)
    logger.info(f"Проверка соединения с прокси {host}:{port}...")
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=connect_timeout,
        )
        writer.close()
        await writer.wait_closed()
        logger.info(f"Прокси {host}:{port} доступен")
    except TimeoutError:
        msg = f"Таймаут соединения с прокси {host}:{port} ({connect_timeout}с)"
        logger.error(msg)
        raise ConnectionError(msg)
    except OSError as e:
        msg = f"Прокси {host}:{port} недоступен: {e}"
        logger.error(msg)
        raise ConnectionError(msg)
