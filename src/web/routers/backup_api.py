"""
API-эндпоинты управления резервным копированием БД.

Все эндпоинты защищены ``APIKeyMiddleware`` (как и остальной дашборд) —
проверяется заголовок ``X-API-Key``. Путь ``/api/backups/*`` не входит
в публичные префиксы (``/app``, ``/static``, ``/api/user``).

Роутер монтируется с префиксом ``/api/backups``.

Логика бэкапа живёт в shell-скриптах. Веб-API — тонкая прослойка:
принимает HTTP-запрос, валидирует параметры, вызывает скрипт через
``subprocess.run`` (в executor), возвращает результат в JSON.
"""

import asyncio
import json
import logging
import os
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from src.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backups", tags=["Backups (JSON API)"])

# ── Константы ─────────────────────────────────────────────────

# Корень проекта (три уровня вверх от src/web/routers/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Файл для хранения токенов подтверждения восстановления
_TOKENS_FILE = _PROJECT_ROOT / "data" / "backups" / "restore_tokens.json"

# TTL токена подтверждения восстановления (5 минут)
_TOKEN_TTL_MINUTES = 5

# Таймаут для subprocess-вызовов скриптов (секунды)
_SCRIPT_TIMEOUT = 120

# Категории бэкапов (порядок для сортировки: monthly → weekly → daily → manual)
_CATEGORIES = ("monthly", "weekly", "daily", "manual")
_CATEGORY_SORT_ORDER = {"monthly": 0, "weekly": 1, "daily": 2, "manual": 3}


# ── Синхронные вспомогательные функции (безопасны для вызова из executor) ──


def _human_size(size_bytes: int) -> str:
    """Преобразует размер в байтах в человекочитаемую строку (KB, MB, GB)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    value: float = float(size_bytes)
    for unit in ("KB", "MB", "GB", "TB"):
        value /= 1024.0
        if value < 1024.0:
            return f"{value:.1f} {unit}"
    return f"{value:.1f} PB"


def _check_integrity(backup_path: Path) -> str:
    """
    Проверяет статус целостности бэкапа по маркерным файлам.

    Ищет рядом с файлом бэкапа маркеры:
    - ``<filename>.integrity_ok`` → ``"ok"``
    - ``<filename>.integrity_fail`` → ``"fail"``
    - отсутствуют оба → ``"unchecked"``
    """
    ok_marker = backup_path.with_name(backup_path.name + ".integrity_ok")
    fail_marker = backup_path.with_name(backup_path.name + ".integrity_fail")
    if ok_marker.is_file():
        return "ok"
    if fail_marker.is_file():
        return "fail"
    return "unchecked"


def _safe_backup_path(backup_dir: Path, filename: str, category: str) -> Path:
    """
    Проверяет, что файл находится внутри backup_dir (защита от path traversal).

    Возвращает полный нормализованный путь к файлу бэкапа.
    Выбрасывает ``ValueError``, если путь выходит за пределы backup_dir
    или содержит недопустимые символы.
    """
    # Запрещаем path separators и relative traversal в имени файла
    if "/" in filename or "\\" in filename or ".." in filename:
        raise ValueError(f"Недопустимое имя файла: {filename}")

    if category not in _CATEGORIES:
        raise ValueError(f"Недопустимая категория: {category}")

    full_path = (backup_dir / category / filename).resolve()
    expected_prefix = backup_dir.resolve()

    try:
        full_path.relative_to(expected_prefix)
    except ValueError as e:
        raise ValueError(f"Path traversal обнаружен: {filename} → {full_path}") from e

    return full_path


def _find_backup_file(backup_dir: Path, filename: str) -> Path | None:
    """
    Ищет файл бэкапа по имени в daily/, weekly/, monthly/.

    Возвращает полный путь или None, если файл не найден.
    """
    for category in _CATEGORIES:
        candidate = backup_dir / category / filename
        if candidate.is_file():
            return candidate.resolve()
    return None


def _scan_backup_dirs_sync(backup_dir: Path) -> list[dict[str, Any]]:
    """
    Сканирует все категории бэкапов и возвращает плоский список с метаданными.

    Синхронная функция — вызывается из async-эндпоинтов через
    ``loop.run_in_executor``.
    """
    backups: list[dict[str, Any]] = []

    for category in _CATEGORIES:
        cat_dir = backup_dir / category
        if not cat_dir.is_dir():
            continue

        try:
            entries = list(cat_dir.iterdir())
        except OSError:
            logger.warning("Не удалось прочитать директорию %s", cat_dir)
            continue

        for entry_path in entries:
            name = entry_path.name
            if not name.startswith("bot_") or not name.endswith(".db"):
                continue
            if not entry_path.is_file():
                continue

            try:
                stat = entry_path.stat()
            except OSError:
                continue

            size_bytes = stat.st_size
            mtime_dt = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
            integrity = _check_integrity(entry_path)

            backups.append(
                {
                    "filename": name,
                    "category": category,
                    "size": _human_size(size_bytes),
                    "size_bytes": size_bytes,
                    "mtime": mtime_dt.isoformat(),
                    "integrity": integrity,
                }
            )

    # Сортировка: сначала по категории (monthly=0, weekly=1, daily=2),
    # затем по mtime (новые первыми)
    backups.sort(
        key=lambda b: (
            _CATEGORY_SORT_ORDER.get(b["category"], 99),
            -datetime.fromisoformat(b["mtime"]).timestamp(),
        )
    )

    return backups


def _run_subprocess_sync(
    args: list[str],
    env: dict[str, str],
    timeout: int,
    cwd: str,
) -> subprocess.CompletedProcess[str]:
    """
    Синхронная обёртка для ``subprocess.run``.

    Вызывается из async-эндпоинтов через ``loop.run_in_executor``.
    """
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=cwd,
        env=env,
    )


def _resolve_backup_dir() -> Path:
    """Разрешает путь к директории бэкапов относительно корня проекта."""
    backup_dir = settings.backup_dir
    if not Path(backup_dir).is_absolute():
        return (_PROJECT_ROOT / backup_dir).resolve()
    return Path(backup_dir).resolve()


def _is_lock_busy() -> bool:
    """
    Проверяет, занят ли lock-файл /tmp/backup.lock.

    Использует ``fcntl.flock`` (Linux/Docker). На Windows всегда возвращает False.
    """
    lock_path = "/tmp/backup.lock"
    try:
        import fcntl  # pyright: ignore[reportUnreachable]
    except ImportError:
        # fcntl недоступен (Windows) — пропускаем проверку
        return False

    try:
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    except OSError:
        # Нет доступа к /tmp — пропускаем проверку
        return False

    try:
        # pyright: ignore[reportAttributeAccessIssue] — flock есть только на Linux
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]
        fcntl.flock(fd, fcntl.LOCK_UN)  # type: ignore[attr-defined]
        return False
    except (BlockingIOError, OSError):
        return True
    finally:
        os.close(fd)


# ── Вспомогательные async-функции ────────────────────────────


async def _load_tokens() -> dict[str, dict[str, Any]]:
    """Загружает токены восстановления из JSON-файла (асинхронно)."""
    try:
        loop = asyncio.get_running_loop()

        def _read() -> dict[str, dict[str, Any]]:
            tokens_file = str(_TOKENS_FILE)
            if not os.path.isfile(tokens_file):
                return {}
            with open(tokens_file, encoding="utf-8") as f:
                result: dict[str, dict[str, Any]] = json.load(f)
                return result

        return await loop.run_in_executor(None, _read)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Не удалось загрузить restore-токены: %s", e)
        return {}


async def _save_tokens(tokens: dict[str, dict[str, Any]]) -> None:
    """Сохраняет токены восстановления в JSON-файл (асинхронно)."""
    try:
        loop = asyncio.get_running_loop()

        def _write() -> None:
            tokens_file = str(_TOKENS_FILE)
            os.makedirs(os.path.dirname(tokens_file), exist_ok=True)
            with open(tokens_file, "w", encoding="utf-8") as f:
                json.dump(tokens, f, ensure_ascii=False, indent=2)

        await loop.run_in_executor(None, _write)
    except OSError as e:
        logger.error("Не удалось сохранить restore-токены: %s", e)


async def _cleanup_expired_tokens(
    tokens: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Удаляет просроченные токены. Возвращает очищенный словарь."""
    now = datetime.now(UTC)
    expired = []
    for token, info in tokens.items():
        expires_str = info.get("expires_at", "")
        if expires_str:
            try:
                expires_at = datetime.fromisoformat(expires_str)
                if expires_at < now:
                    expired.append(token)
            except (ValueError, TypeError):
                expired.append(token)

    for token in expired:
        del tokens[token]

    if expired:
        logger.debug("Удалено %d просроченных restore-токенов", len(expired))

    return tokens


# ── Эндпоинты ────────────────────────────────────────────────


@router.get("")
async def list_backups(request: Request) -> dict[str, Any]:
    """
    Список всех бэкапов с метаданными.

    Сканирует daily/, weekly/, monthly/ внутри backup_dir.
    Возвращает плоский список, отсортированный: monthly (новые) → weekly → daily.
    """
    loop = asyncio.get_running_loop()
    backup_dir = _resolve_backup_dir()
    backups = await loop.run_in_executor(None, _scan_backup_dirs_sync, backup_dir)
    return {"backups": backups}


@router.post("/run", response_model=None)
async def run_backup(request: Request) -> dict[str, Any] | JSONResponse:
    """
    Ручной запуск резервного копирования (вне расписания cron).

    Проверяет lock-файл /tmp/backup.lock. Если занят — возвращает 409 Conflict.
    Вызывает ``scripts/backup.sh`` через subprocess с таймаутом 120 секунд.
    """
    # Проверка lock-файла
    if _is_lock_busy():
        return JSONResponse(
            status_code=409,
            content={
                "status": "error",
                "message": (
                    "Бэкап уже выполняется (lock-файл занят). Попробуйте позже."
                ),
            },
        )

    loop = asyncio.get_running_loop()
    backup_script = str(_PROJECT_ROOT / "scripts" / "backup.sh")

    if not await loop.run_in_executor(None, os.path.isfile, backup_script):
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Скрипт бэкапа не найден: {backup_script}",
            },
        )

    # Переменные окружения для скрипта
    script_env = os.environ.copy()
    script_env["SQLITE_DB_PATH"] = str(_PROJECT_ROOT / "data" / "bot.db")
    script_env["BACKUP_DIR"] = str(_resolve_backup_dir())
    script_env["BACKUP_DAILY_RETENTION"] = str(settings.backup_daily_retention)
    script_env["BACKUP_WEEKLY_RETENTION"] = str(settings.backup_weekly_retention)
    script_env["BACKUP_MONTHLY_RETENTION"] = str(settings.backup_monthly_retention)
    script_env["BACKUP_MANUAL_RETENTION"] = str(settings.backup_manual_retention)
    # Ручной бэкап → кладём в manual/ вместо daily/
    script_env["MANUAL_BACKUP"] = "true"
    if settings.ntfy_backup_topic:
        script_env["NTFY_BACKUP_TOPIC"] = settings.ntfy_backup_topic

    logger.info(
        "Ручной запуск бэкапа: script=%s, backup_dir=%s, cwd=%s",
        backup_script,
        script_env["BACKUP_DIR"],
        _PROJECT_ROOT,
    )

    try:
        result = await loop.run_in_executor(
            None,
            _run_subprocess_sync,
            ["bash", backup_script, "daily"],
            script_env,
            _SCRIPT_TIMEOUT,
            str(_PROJECT_ROOT),
        )
    except subprocess.TimeoutExpired:
        logger.error("Таймаут (%dс) при выполнении backup.sh", _SCRIPT_TIMEOUT)
        return JSONResponse(
            status_code=504,
            content={
                "status": "error",
                "message": f"Бэкап не завершился за {_SCRIPT_TIMEOUT} секунд.",
            },
        )
    except FileNotFoundError:
        logger.error("bash не найден в системе")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Интерпретатор bash не найден в системе.",
            },
        )
    except Exception as e:
        logger.exception("Неожиданная ошибка при запуске backup.sh")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Ошибка запуска бэкапа: {e}",
            },
        )

    output = result.stdout.strip()
    if result.returncode == 0:
        logger.info("Ручной бэкап успешно завершён (rc=%d)", result.returncode)
        # Извлекаем имя файла из вывода скрипта (последняя строка с .db)
        filename = ""
        for line in reversed(result.stdout.splitlines()):
            if ".db" in line:
                import re

                match = re.search(r"(bot_\d{4}-\d{2}-\d{2}_\d{6}\.db)", line)
                if match:
                    filename = match.group(1)
                    break
        return {
            "status": "ok",
            "output": output,
            "filename": filename,
        }
    else:
        logger.error(
            "Ручной бэкап завершился с ошибкой (rc=%d): %s",
            result.returncode,
            result.stderr.strip() or result.stdout.strip(),
        )
        return {
            "status": "error",
            "message": f"Бэкап завершился с кодом {result.returncode}.",
            "output": output,
            "stderr": result.stderr.strip(),
        }


@router.post("/restore/{filename:path}", response_model=None)
async def restore_backup(
    request: Request,
    filename: str,
    token: str | None = Query(None, description="Токен подтверждения (шаг 2)"),
) -> dict[str, Any] | JSONResponse:
    """
    Двухфакторное восстановление БД из бэкапа.

    **Шаг 1 (без токена):** проверяет существование файла, генерирует
    UUID4-токен, сохраняет в ``data/backups/restore_tokens.json`` с TTL 5 минут,
    возвращает статус ``confirm_required``.

    **Шаг 2 (с токеном):** проверяет токен (существует, не просрочен,
    привязан к filename), удаляет использованный токен, вызывает
    ``scripts/restore.sh <full_path>``, возвращает результат.
    """
    loop = asyncio.get_running_loop()
    backup_dir = _resolve_backup_dir()

    # Проверяем существование файла в одной из категорий
    full_path = await loop.run_in_executor(
        None, _find_backup_file, backup_dir, filename
    )
    if full_path is None:
        return JSONResponse(
            status_code=404,
            content={
                "status": "error",
                "message": f"Файл бэкапа не найден: {filename}",
            },
        )

    # Дополнительная проверка path traversal (перестраховка)
    try:
        category = full_path.parent.name
        safe_path = _safe_backup_path(backup_dir, filename, category)
        full_path = safe_path
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(e)},
        )

    # ── Шаг 1: запрос подтверждения (без токена) ──────────────
    if token is None:
        restore_token = str(uuid.uuid4())
        expires_at = datetime.now(UTC) + timedelta(minutes=_TOKEN_TTL_MINUTES)

        # Загружаем текущие токены, чистим просроченные
        tokens = await _load_tokens()
        tokens = await _cleanup_expired_tokens(tokens)

        tokens[restore_token] = {
            "filename": filename,
            "full_path": str(full_path),
            "created_at": datetime.now(UTC).isoformat(),
            "expires_at": expires_at.isoformat(),
        }

        await _save_tokens(tokens)

        logger.warning(
            "Запрошен токен подтверждения восстановления: filename=%s, token=%s",
            filename,
            restore_token,
        )

        return {
            "status": "confirm_required",
            "token": restore_token,
            "message": (
                "Отправьте повторный запрос с токеном для подтверждения восстановления."
            ),
        }

    # ── Шаг 2: подтверждение с токеном ────────────────────────
    tokens = await _load_tokens()
    tokens = await _cleanup_expired_tokens(tokens)

    token_info = tokens.get(token)
    if token_info is None:
        return JSONResponse(
            status_code=403,
            content={
                "status": "error",
                "message": "Токен недействителен или просрочен.",
            },
        )

    if token_info.get("filename") != filename:
        return JSONResponse(
            status_code=403,
            content={
                "status": "error",
                "message": "Токен не соответствует указанному файлу бэкапа.",
            },
        )

    # Удаляем использованный токен
    del tokens[token]
    await _save_tokens(tokens)

    # Запускаем restore
    restore_script = str(_PROJECT_ROOT / "scripts" / "restore.sh")

    if not await loop.run_in_executor(None, os.path.isfile, restore_script):
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": (f"Скрипт восстановления не найден: {restore_script}"),
            },
        )

    script_env = os.environ.copy()
    script_env["SQLITE_DB_PATH"] = str(_PROJECT_ROOT / "data" / "bot.db")
    script_env["BACKUP_DIR"] = str(_resolve_backup_dir())
    script_env["RESTORE_IN_CONTAINER"] = str(settings.restore_in_container).lower()
    if settings.ntfy_backup_topic:
        script_env["NTFY_BACKUP_TOPIC"] = settings.ntfy_backup_topic

    logger.critical(
        "Запуск восстановления из бэкапа: filename=%s, full_path=%s, "
        "restore_in_container=%s",
        filename,
        full_path,
        settings.restore_in_container,
    )

    try:
        result = await loop.run_in_executor(
            None,
            _run_subprocess_sync,
            ["bash", restore_script, str(full_path)],
            script_env,
            _SCRIPT_TIMEOUT,
            str(_PROJECT_ROOT),
        )
    except subprocess.TimeoutExpired:
        logger.critical(
            "Таймаут (%dс) при восстановлении из %s",
            _SCRIPT_TIMEOUT,
            filename,
        )
        return JSONResponse(
            status_code=504,
            content={
                "status": "error",
                "message": (
                    f"Восстановление не завершилось за {_SCRIPT_TIMEOUT} секунд."
                ),
            },
        )
    except FileNotFoundError:
        logger.critical("bash не найден при попытке restore")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Интерпретатор bash не найден в системе.",
            },
        )
    except Exception as e:
        logger.critical("Неожиданная ошибка при восстановлении из %s: %s", filename, e)
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Ошибка восстановления: {e}",
            },
        )

    output = result.stdout.strip()

    if result.returncode == 0:
        logger.critical(
            "Восстановление из %s успешно завершено (rc=%d)",
            filename,
            result.returncode,
        )
        return {
            "status": "ok",
            "output": output,
            "filename": filename,
        }
    else:
        logger.critical(
            "Восстановление из %s завершилось с ошибкой (rc=%d): %s",
            filename,
            result.returncode,
            result.stderr.strip() or output,
        )
        return {
            "status": "error",
            "message": (f"Восстановление завершилось с кодом {result.returncode}."),
            "output": output,
            "stderr": result.stderr.strip(),
        }


@router.delete("/{filename:path}", response_model=None)
async def delete_backup(
    request: Request,
    filename: str,
) -> dict[str, Any] | JSONResponse:
    """
    Удаляет файл бэкапа и его маркерные файлы.

    Ищет файл в daily/, weekly/, monthly/, manual/.
    При удалении также удаляет ``.integrity_ok`` и ``.integrity_fail``
    маркеры рядом с файлом бэкапа.
    """
    loop = asyncio.get_running_loop()
    backup_dir = _resolve_backup_dir()

    # Ищем файл во всех категориях
    full_path = await loop.run_in_executor(
        None, _find_backup_file, backup_dir, filename
    )
    if full_path is None:
        return JSONResponse(
            status_code=404,
            content={
                "status": "error",
                "message": f"Файл бэкапа не найден: {filename}",
            },
        )

    # Дополнительная проверка path traversal
    try:
        category = full_path.parent.name
        safe_path = _safe_backup_path(backup_dir, filename, category)
        full_path = safe_path
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(e)},
        )

    category = full_path.parent.name
    logger.warning(
        "Удаление бэкапа: filename=%s, category=%s, path=%s",
        filename,
        category,
        full_path,
    )

    # Удаляем файл бэкапа и маркеры
    removed_files: list[str] = []
    try:
        if full_path.is_file():
            full_path.unlink()
            removed_files.append(str(full_path))
    except OSError as e:
        logger.error("Ошибка удаления файла %s: %s", full_path, e)
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Не удалось удалить файл: {e}",
            },
        )

    # Удаляем маркеры целостности
    for suffix in (".integrity_ok", ".integrity_fail"):
        marker = full_path.with_name(full_path.name + suffix)
        try:
            if marker.is_file():
                marker.unlink()
                removed_files.append(str(marker))
        except OSError:
            logger.warning("Не удалось удалить маркер %s", marker)

    logger.info(
        "Бэкап удалён: filename=%s, category=%s, удалено файлов: %d",
        filename,
        category,
        len(removed_files),
    )

    return {
        "status": "ok",
        "message": f"Бэкап {filename} удалён.",
        "removed": removed_files,
    }


@router.get("/status", response_model=None)
async def backup_status(request: Request) -> dict[str, Any] | JSONResponse:
    """
    Сводный статус системы бэкапов.

    Вызывает ``scripts/backup_healthcheck.sh``, парсит JSON-вывод,
    добавляет ``restore_in_container`` из настроек.

    Возвращает статус, даже если healthcheck-скрипт завершился с ошибкой
    (в этом случае общий статус будет ``"issues"``).
    """
    loop = asyncio.get_running_loop()
    healthcheck_script = str(_PROJECT_ROOT / "scripts" / "backup_healthcheck.sh")

    if not await loop.run_in_executor(None, os.path.isfile, healthcheck_script):
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": (f"Скрипт healthcheck не найден: {healthcheck_script}"),
            },
        )

    script_env = os.environ.copy()
    script_env["BACKUP_DIR"] = str(_resolve_backup_dir())

    try:
        result = await loop.run_in_executor(
            None,
            _run_subprocess_sync,
            ["bash", healthcheck_script],
            script_env,
            30,  # отдельный таймаут для healthcheck
            str(_PROJECT_ROOT),
        )
    except subprocess.TimeoutExpired:
        logger.error("Таймаут при выполнении backup_healthcheck.sh")
        return JSONResponse(
            status_code=504,
            content={
                "status": "error",
                "message": "Healthcheck не завершился за 30 секунд.",
            },
        )
    except FileNotFoundError:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Интерпретатор bash не найден в системе.",
            },
        )
    except Exception as e:
        logger.exception("Неожиданная ошибка при выполнении backup_healthcheck.sh")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Ошибка healthcheck: {e}",
            },
        )

    stdout = result.stdout.strip()

    # Парсим JSON-вывод healthcheck-скрипта
    try:
        health_data: dict[str, Any] = json.loads(stdout)
    except json.JSONDecodeError as e:
        logger.error(
            "Не удалось разобрать JSON от backup_healthcheck.sh: %s\nВывод: %s",
            e,
            stdout[:500],
        )
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Некорректный JSON-ответ от healthcheck-скрипта.",
                "raw_output": stdout[:1000],
            },
        )

    # Добавляем restore_in_container из настроек
    health_data["restore_in_container"] = settings.restore_in_container

    # Если скрипт вернул код != 0, но JSON валидный — статус "issues"
    if result.returncode != 0:
        health_data["status"] = "issues"

    return health_data
