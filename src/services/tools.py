"""Инструменты обслуживания в UI (DASH-7).

Экспонирует существующие скрипты ``scripts/`` как страницу ``/tools``:

* read-only инструменты запускаются «как есть» и возвращают отчёт;
* мутирующие по умолчанию работают в режиме dry-run, а применение требует
  явного подтверждения (``apply=True`` + ``confirm=True``);
* каждый запуск пишется в ``audit_log`` действием ``tool_run``.

Dry-run для скриптов без собственного ``--apply`` выполняется на **копии**
БД: скрипт открывает базу по ``SQLITE_DB_PATH``, поэтому копия подменяет
путь через окружение и реальные данные не меняются.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

# Ограничения запуска: таймаут и объём вывода, который уходит в UI.
TOOL_TIMEOUT_SECONDS = 180
OUTPUT_TAIL_CHARS = 4000

# Корень проекта: src/services/tools.py → три уровня вверх. Скрипты лежат
# в scripts/ и импортируют src.*, поэтому запускаются из корня.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ToolParam:
    """Параметр инструмента, который вводит администратор."""

    name: str
    label: str
    required: bool = False
    default: str = ""


@dataclass(frozen=True)
class ToolSpec:
    """Описание инструмента обслуживания."""

    name: str
    title: str
    description: str
    kind: str  # read_only | mutating
    script: str
    params: tuple[ToolParam, ...] = field(default_factory=tuple)
    apply_flag: bool = False
    """Скрипт понимает ``--apply``; без него применение = работа по реальной БД."""

    @property
    def mutating(self) -> bool:
        """Меняет ли инструмент данные."""
        return self.kind == "mutating"


TOOLS: dict[str, ToolSpec] = {
    "audit_booking_doctor_mismatch": ToolSpec(
        name="audit_booking_doctor_mismatch",
        title="Аудит расхождений врач/запись",
        description=(
            "Ищет записи, где врач в брони не совпадает со справочником. "
            "Только чтение — отчёт в выводе."
        ),
        kind="read_only",
        script="audit_booking_doctor_mismatch.py",
    ),
    "apply_city_heuristic": ToolSpec(
        name="apply_city_heuristic",
        title="Эвристика города клиник",
        description=(
            "Проставляет город клиникам, у которых он пуст. "
            "Dry-run выполняется на копии БД."
        ),
        kind="mutating",
        script="apply_city_heuristic.py",
    ),
    "apply_heuristic_types": ToolSpec(
        name="apply_heuristic_types",
        title="Эвристика типа клиник",
        description=(
            "Определяет тип клиник эвристикой. Dry-run выполняется на копии БД."
        ),
        kind="mutating",
        script="apply_heuristic_types.py",
    ),
    "repair_booking_doctor": ToolSpec(
        name="repair_booking_doctor",
        title="Ремонт брони (врач/дата)",
        description=(
            "Исправляет booking_id после смены врача. По умолчанию dry-run; "
            "применение — только с подтверждением."
        ),
        kind="mutating",
        script="repair_booking_doctor.py",
        apply_flag=True,
        params=(
            ToolParam("booking_id", "booking_id", required=True),
            ToolParam("doctor_id", "doctor_id"),
            ToolParam("doctor_name", "ФИО врача"),
            ToolParam("slot_date", "Дата (ДД.ММ.ГГГГ)"),
            ToolParam("slot_time", "Время (ЧЧ:ММ)"),
        ),
    ),
}


def build_command(
    spec: ToolSpec, params: dict[str, str], apply: bool, db_path: str | Path
) -> list[str]:
    """Собирает argv скрипта для запуска.

    Args:
        spec: Описание инструмента.
        params: Значения параметров из формы.
        apply: Применять изменения (для мутирующих).
        db_path: Путь к БД (для dry-run — к копии).

    Returns:
        Аргументы процесса.

    Raises:
        ValueError: Обязательный параметр не заполнен или он неизвестен.
    """
    # Интерпретатор берём у процесса: в dev это venv-питон, в контейнере —
    # системный. Литерал "python" ломался там, где есть только "python3".
    argv = [
        sys.executable or "python",
        str(PROJECT_ROOT / "scripts" / spec.script),
        f"--db={db_path}",
    ]

    known = {param.name for param in spec.params}
    unknown = set(params) - known
    if unknown:
        raise ValueError(f"Неизвестные параметры: {', '.join(sorted(unknown))}")

    for param in spec.params:
        value = str(params.get(param.name, "") or param.default).strip()
        if not value:
            if param.required:
                raise ValueError(f"Параметр «{param.label}» обязателен.")
            continue
        # Форма --param=value: значение, начинающееся с дефиса, не будет
        # принято парсером за флаг.
        argv.append(f"--{param.name.replace('_', '-')}={value}")

    if spec.mutating and apply and spec.apply_flag:
        argv.append("--apply")
    return argv


def tool_view(spec: ToolSpec) -> dict[str, Any]:
    """Представление инструмента для страницы и API."""
    return {
        "name": spec.name,
        "title": spec.title,
        "description": spec.description,
        "kind": spec.kind,
        "mutating": spec.mutating,
        "params": [
            {
                "name": param.name,
                "label": param.label,
                "required": param.required,
                "default": param.default,
            }
            for param in spec.params
        ],
    }


def _snapshot_db(db_path: Path, dest: Path) -> None:
    """Консистентный снимок БД средствами SQLite (учитывает WAL).

    Копирование файла игнорировало бы незачекпойнченный WAL, поэтому снимок
    делается через ``Connection.backup``.
    """
    source = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        target = sqlite3.connect(dest)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def _prepare_dry_run_db(db_path: Path) -> tuple[Path, Path]:
    """Копия БД для dry-run мутирующего скрипта.

    Returns:
        Путь к копии и путь к каталогу, который нужно убрать после запуска.
    """
    work_dir = Path(tempfile.mkdtemp(prefix="dashboard-tool-"))
    copy_path = work_dir / "dry-run.db"
    _snapshot_db(db_path, copy_path)
    return copy_path, work_dir


def _run_sync(
    argv: list[str], env: dict[str, str], work_dir: Path | None
) -> tuple[int, str, bool]:
    """Запускает инструмент и убирает каталог копии в том же потоке.

    Returns:
        Код возврата, объединённый вывод и признак таймаута.
    """
    process = subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(PROJECT_ROOT),
        env=env,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=TOOL_TIMEOUT_SECONDS)
        return process.returncode, (stdout or "") + (stderr or ""), False
    except subprocess.TimeoutExpired:
        # Убиваем всю группу процессов: дочерние процессы скрипта не должны
        # остаться работать, пока мы убираем его данные.
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except OSError:
            process.kill()
        process.communicate()
        return -1, f"Таймаут {TOOL_TIMEOUT_SECONDS} с: инструмент не завершился.", True
    except OSError as exc:
        return -1, f"Не удалось запустить инструмент: {exc}", False
    finally:
        if work_dir is not None:
            shutil.rmtree(work_dir, ignore_errors=True)


async def run_tool(
    db: Any,
    name: str,
    params: dict[str, str],
    apply: bool,
    confirm: bool,
    actor: str,
    db_path: str | Path,
) -> dict[str, Any]:
    """Запускает инструмент и фиксирует факт запуска в журнале.

    Args:
        db: Фасад БД (журнал действий).
        name: Имя инструмента из реестра.
        params: Значения параметров.
        apply: Применять изменения.
        confirm: Явное подтверждение применения мутирующего инструмента.
        actor: Кто запустил.
        db_path: Путь к БД проекта.

    Returns:
        Словарь со статусом, кодом возврата и выводом.

    Raises:
        KeyError: Инструмента нет в реестре.
        ValueError: Параметры не прошли проверку.
    """
    from src.services.audit import log_action

    spec = TOOLS.get(name)
    if spec is None:
        raise KeyError(name)

    if spec.mutating and apply and not confirm:
        # Двухшаговое подтверждение: без него применение не запускаем,
        # но попытку фиксируем в журнале.
        await log_action(
            db,
            actor,
            "tool_confirm_required",
            target=name,
            apply=True,
        )
        return {
            "status": "confirm_required",
            "tool": name,
            "message": "Применение требует подтверждения.",
        }

    real_db = Path(db_path)
    work_dir: Path | None = None
    run_db = real_db
    if spec.mutating and not apply:
        try:
            run_db, work_dir = await asyncio.get_running_loop().run_in_executor(
                None, _prepare_dry_run_db, real_db
            )
        except OSError as exc:
            logger.warning(f"Инструменты: не удалось подготовить dry-run: {exc}")
            return {
                "status": "error",
                "tool": name,
                "message": f"Не удалось подготовить dry-run: {exc}",
            }

    argv = build_command(spec, params, apply, run_db)
    env = os.environ.copy()
    env["SQLITE_DB_PATH"] = str(run_db)

    started = time.monotonic()
    exit_code, output, timed_out = await asyncio.get_running_loop().run_in_executor(
        None, _run_sync, argv, env, work_dir
    )

    duration = round(time.monotonic() - started, 2)
    applied = bool(spec.mutating and apply and exit_code == 0)
    status = "ok" if exit_code == 0 else ("timeout" if timed_out else "error")

    tail = output[-OUTPUT_TAIL_CHARS:] if len(output) > OUTPUT_TAIL_CHARS else output
    result = {
        "status": status,
        "tool": name,
        "exit_code": exit_code,
        "applied": applied,
        "dry_run": spec.mutating and not apply,
        "duration_seconds": duration,
        "output": tail,
        "output_truncated": len(output) > OUTPUT_TAIL_CHARS,
    }

    await log_action(
        db,
        actor,
        "tool_run",
        target=name,
        params={key: value for key, value in params.items() if value},
        apply=apply,
        exit_code=exit_code,
        dry_run=result["dry_run"],
    )
    return result
