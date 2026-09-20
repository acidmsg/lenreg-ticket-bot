"""Системный снимок для страницы ``/system`` (DASH-4).

Собирает только то, что можно проверить из процесса: место на диске, размеры
БД и её WAL, объём бэкапов, состояние Redis, версии, uptime и интервалы.
Если источник недоступен, отдаётся честный статус ``unavailable`` без
выдуманных чисел.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from loguru import logger

# ── Пороги для уровней ok / warn / crit ───────────────────────
# Доля свободного места на диске, ниже которой статус становится жёлтым/красным.
DISK_FREE_WARN_PERCENT = 20.0
DISK_FREE_CRIT_PERCENT = 10.0
# Объёмы в байтах: предупреждение и критический уровень.
DB_WARN_BYTES = 500 * 1024 * 1024
DB_CRIT_BYTES = 1024 * 1024 * 1024
WAL_WARN_BYTES = 100 * 1024 * 1024
BACKUPS_WARN_BYTES = 2 * 1024 * 1024 * 1024
# Возраст самого свежего бэкапа, часы: после этого уровня — предупреждение.
BACKUP_STALE_HOURS = 48.0

BACKUP_CATEGORIES = ("daily", "weekly", "monthly", "manual")
# Ревизия git меняется редко: кэшируем, чтобы не звать subprocess на каждый запрос.
REVISION_CACHE_TTL_SECONDS = 300.0


# Кэш ревизий: (время чтения по monotonic, значение).
_revision_cache: dict[str, tuple[float, str]] = {}


def _mb(value: float) -> float:
    """Байты в мегабайты с двумя знаками после запятой.

    Два знака, а не один: небольшие файлы (первые килобайты) иначе
    округлялись бы до нуля и выглядели как отсутствие данных.
    """
    return round(value / (1024 * 1024), 2)


def disk_snapshot(path: str | Path) -> dict[str, Any]:
    """Свободное место на диске, на котором лежит указанный путь."""
    try:
        usage = shutil.disk_usage(str(path))
    except OSError as exc:
        logger.warning(f"system: диск {path} недоступен: {exc}")
        return {"path": str(path), "status": "unavailable", "level": "unknown"}

    free_percent = round(usage.free / usage.total * 100, 1) if usage.total else 0.0
    if free_percent < DISK_FREE_CRIT_PERCENT:
        level = "crit"
    elif free_percent < DISK_FREE_WARN_PERCENT:
        level = "warn"
    else:
        level = "ok"

    return {
        "path": str(path),
        "status": "ok",
        "total_bytes": usage.total,
        "free_bytes": usage.free,
        "total_mb": _mb(usage.total),
        "used_mb": _mb(usage.used),
        "free_mb": _mb(usage.free),
        "free_percent": free_percent,
        "level": level,
    }


def db_snapshot(db_path: str | Path) -> dict[str, Any]:
    """Размеры файла БД, WAL и SHM."""
    path = Path(db_path)
    if not path.is_file():
        return {"path": str(path), "status": "unavailable", "level": "unknown"}

    try:
        main_size = path.stat().st_size
    except OSError as exc:
        logger.warning(f"system: не удалось прочитать БД {path}: {exc}")
        return {"path": str(path), "status": "unavailable", "level": "unknown"}

    # Файлы WAL/SHM может удалить checkpoint между проверкой и stat() —
    # это не ошибка страницы, а нормальный ход событий.
    wal_size = _safe_size(path.with_name(path.name + "-wal"))
    shm_size = _safe_size(path.with_name(path.name + "-shm"))
    total = main_size + wal_size + shm_size

    if total >= DB_CRIT_BYTES:
        level = "crit"
    elif total >= DB_WARN_BYTES or wal_size >= WAL_WARN_BYTES:
        level = "warn"
    else:
        level = "ok"

    return {
        "path": str(path),
        "status": "ok",
        "main_bytes": main_size,
        "wal_bytes": wal_size,
        "shm_bytes": shm_size,
        "total_bytes": total,
        "main_mb": _mb(main_size),
        "wal_mb": _mb(wal_size),
        "shm_mb": _mb(shm_size),
        "total_mb": _mb(total),
        "wal_present": wal_size > 0,
        "level": level,
    }


def _safe_size(file_path: Path) -> int:
    """Размер файла или 0, если файла нет/он недоступен."""
    try:
        return file_path.stat().st_size if file_path.is_file() else 0
    except OSError:
        return 0


def _display_path(path: str | Path, root: str | Path) -> str:
    """Путь относительно корня проекта: на странице нет абсолютных путей хоста."""
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except (ValueError, OSError):
        return Path(path).name


def backups_snapshot(backup_dir: str | Path) -> dict[str, Any]:
    """Количество и суммарный объём бэкапов по категориям."""
    root = Path(backup_dir)
    if not root.is_dir():
        return {"path": str(root), "status": "unavailable", "level": "unknown"}

    categories: dict[str, dict[str, Any]] = {}
    total_bytes = 0
    total_files = 0
    latest_mtime = 0.0

    for category in BACKUP_CATEGORIES:
        category_dir = root / category
        size = 0
        count = 0
        if category_dir.is_dir():
            for backup in category_dir.glob("*.db"):
                # Симлинки (например, latest.db) не считаем: иначе объём
                # и количество задваиваются.
                if backup.is_symlink():
                    continue
                try:
                    stat = backup.stat()
                except OSError:
                    continue
                size += stat.st_size
                count += 1
                latest_mtime = max(latest_mtime, stat.st_mtime)
        categories[category] = {"count": count, "size_mb": _mb(size)}
        total_bytes += size
        total_files += count

    newest_age_hours: float | None = None
    if latest_mtime:
        newest_age_hours = round((time.time() - latest_mtime) / 3600, 1)

    if total_files == 0:
        # Отсутствие бэкапов — не «норма»: у данных нет страховки.
        level = "crit"
    elif total_bytes >= BACKUPS_WARN_BYTES or (
        newest_age_hours is not None and newest_age_hours > BACKUP_STALE_HOURS
    ):
        level = "warn"
    else:
        level = "ok"

    return {
        "path": str(root),
        "status": "ok",
        "count": total_files,
        "total_bytes": total_bytes,
        "total_mb": _mb(total_bytes),
        "categories": categories,
        "newest_age_hours": newest_age_hours,
        "level": level,
    }


async def redis_snapshot() -> dict[str, Any]:
    """Состояние Redis: подключение и память.

    При недоступности Redis возвращается ``connected: False`` — без цифр,
    чтобы на странице не было выдуманных значений.
    """
    try:
        from src.utils.redis import RedisClient

        client = await RedisClient.get_instance()
        if not client.is_available():
            return {"status": "ok", "connected": False, "level": "warn"}

        raw = client.client
        info = await raw.info()
    except Exception as exc:
        logger.warning(f"system: Redis недоступен: {exc}")
        return {"status": "ok", "connected": False, "level": "warn"}

    used_memory = int(info.get("used_memory", 0) or 0)
    maxmemory = int(info.get("maxmemory", 0) or 0)
    used_percent = round(used_memory / maxmemory * 100, 1) if maxmemory > 0 else None

    return {
        "status": "ok",
        "connected": True,
        "version": str(info.get("redis_version", "")),
        "used_memory_mb": _mb(used_memory),
        "used_memory_human": str(info.get("used_memory_human", "")),
        "maxmemory_mb": _mb(maxmemory) if maxmemory else 0.0,
        "used_percent": used_percent,
        "connected_clients": int(info.get("connected_clients", 0) or 0),
        "uptime_seconds": int(info.get("uptime_in_seconds", 0) or 0),
        "level": "warn" if (used_percent or 0) >= 90 else "ok",
    }


def versions_snapshot(root: str | Path) -> dict[str, Any]:
    """Версии приложения и рантайма, образ и ревизия исходников."""
    from src.config import settings

    return {
        "app": settings.API_VERSION,
        "python": sys.version.split()[0],
        "sqlite": sqlite3.sqlite_version,
        "image": os.environ.get("BOT_IMAGE") or os.environ.get("IMAGE_TAG") or "",
        "revision": _git_revision(root),
    }


def _git_revision(root: str | Path) -> str:
    """Ревизия git с кэшем на ``REVISION_CACHE_TTL_SECONDS``."""
    key = str(root)
    cached = _revision_cache.get(key)
    now = time.monotonic()
    if cached is not None and now - cached[0] < REVISION_CACHE_TTL_SECONDS:
        return cached[1]
    value = _read_git_revision(root)
    _revision_cache[key] = (now, value)
    return value


def _read_git_revision(root: str | Path) -> str:
    """Короткая ревизия git (``ветка@хеш``) или пустая строка.

    Пустая строка честно означает «нет данных»: в контейнере без ``.git``
    показывать нечего.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""

    revision = result.stdout.strip()
    branch = ""
    try:
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if branch_result.returncode == 0:
            branch = branch_result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        branch = ""

    return f"{branch}@{revision}" if branch else revision


async def schedule_snapshot(db: Any) -> dict[str, Any]:
    """Интервалы сканирования и дефолты расписания бэкапов.

    Расписание бэкапов задаётся вне процесса (внешний cron/скрипт), поэтому
    страница показывает сроки хранения и возраст свежего бэкапа, а не
    выдуманное «время до следующего запуска».
    """
    from src.config import (
        CONFIG_KEY_CHECK_INTERVAL,
        CONFIG_KEY_DISCOVERY_INTERVAL,
        settings,
    )

    scan_enabled = await db.config.get_config("doctor_scan_enabled", "1")
    scan_interval = await db.config.get_config(
        CONFIG_KEY_DISCOVERY_INTERVAL, str(settings.DISCOVERY_INTERVAL)
    )
    check_interval = await db.config.get_config(
        CONFIG_KEY_CHECK_INTERVAL, str(settings.CHECK_INTERVAL)
    )

    return {
        "scan_enabled": scan_enabled == "1",
        "scan_interval_seconds": _as_int(scan_interval),
        "check_interval_seconds": _as_int(check_interval),
        "retention": {
            "daily": settings.backup_daily_retention,
            "weekly": settings.backup_weekly_retention,
            "monthly": settings.backup_monthly_retention,
            "manual": settings.backup_manual_retention,
        },
    }


def _as_int(raw: str, default: int = 0) -> int:
    """Строку в int; нечисловое значение — ``default``."""
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _collect_sync_part(
    db_path: str | Path, backup_dir: str | Path, project_root: str | Path
) -> dict[str, Any]:
    """Файловые операции и git: вызывается в executor, не в loop'е.

    Обход каталогов, ``shutil.disk_usage`` и ``subprocess.run`` для ревизии —
    блокирующие вызовы; в event loop'е они заморозили бы бота.
    """
    disk = disk_snapshot(project_root)
    database = db_snapshot(db_path)
    backups = backups_snapshot(backup_dir)
    versions = versions_snapshot(project_root)

    # Абсолютные пути хоста на страницу не отдаём — только относительные.
    disk["display"] = _display_path(disk["path"], project_root)
    database["display"] = _display_path(database["path"], project_root)
    backups["display"] = _display_path(backups["path"], project_root)

    return {"disk": disk, "db": database, "backups": backups, "versions": versions}


async def collect_system_snapshot(
    db: Any,
    db_path: str | Path,
    backup_dir: str | Path,
    project_root: str | Path,
    uptime_seconds: float,
) -> dict[str, Any]:
    """Собирает полный системный снимок для страницы ``/system``."""
    loop = asyncio.get_running_loop()
    sync_part = await loop.run_in_executor(
        None, _collect_sync_part, db_path, backup_dir, project_root
    )
    return {
        **sync_part,
        "redis": await redis_snapshot(),
        "schedule": await schedule_snapshot(db),
        "uptime_seconds": round(float(uptime_seconds), 1),
    }
