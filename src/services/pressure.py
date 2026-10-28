"""Чтение cgroup v2 Pressure Stall Information (PSI).

Файлы ``cpu.pressure``, ``memory.pressure`` и ``io.pressure`` лежат в
``/sys/fs/cgroup`` контейнера и показывают давление именно его cgroup.
``/proc/pressure/*`` — хостовый срез, его используем только как fallback.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

PRESSURE_KEYS = ("cpu", "memory", "io")


def _parse_pressure_text(text: str) -> dict[str, dict[str, float]]:
    """Разбирает строки ``some``/``full`` из PSI-файла."""
    result: dict[str, dict[str, float]] = {}
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        kind = parts[0]
        values: dict[str, float] = {}
        for item in parts[1:]:
            if "=" not in item:
                continue
            name, raw = item.split("=", 1)
            try:
                values[name] = float(raw)
            except ValueError:
                continue
        if values:
            result[kind] = values
    return result


def read_pressure(path: str | Path) -> dict[str, Any]:
    """Читает один PSI-файл; отсутствие файла — честный ``unavailable``."""
    file_path = Path(path)
    if not file_path.is_file():
        return {"status": "unavailable"}
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError:
        return {"status": "unavailable"}
    parsed = _parse_pressure_text(text)
    if not parsed:
        return {"status": "unavailable"}
    return {"status": "ok", **parsed}


def collect_pressure_snapshot(
    base_path: str | Path = "/sys/fs/cgroup",
) -> dict[str, Any]:
    """Собирает PSI по cpu/memory/io для текущего контейнера."""
    base = Path(base_path)
    snapshot: dict[str, Any] = {}
    available = False
    for key in PRESSURE_KEYS:
        item = read_pressure(base / f"{key}.pressure")
        snapshot[key] = item
        if item.get("status") == "ok":
            available = True
    snapshot["status"] = "ok" if available else "unavailable"
    return snapshot
