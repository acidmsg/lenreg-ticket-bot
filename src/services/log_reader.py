"""Чтение файла логов бота для страницы «Логи» дашборда.

Логи пишет loguru в формате ``{time} | {level} | {name}:{function}:{line} | {message}``
(см. ``src/utils/logging.py``). Файл растёт и ротируется по 10 МБ, поэтому хвост
читается порциями с конца, а не целиком: дашборд не должен тянуть гигабайты.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

# Строка из setup_logging(): "2026-09-20 23:04:11 | INFO     | src.x:y:12 | текст"
_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| (?P<level>[A-Z]+)\s*\| "
    r"(?P<source>[^:]+):(?P<function>[^:]*):(?P<line>\d+) \| (?P<message>.*)$"
)

LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

# Размер порции чтения с конца файла и потолок сканирования на один запрос.
_SCAN_CHUNK = 256 * 1024
_MAX_SCAN_BYTES = 4 * 1024 * 1024

# Потолок разового дочитывания в режиме «следить»: старт слежения и ротация
# читают только хвост файла, а не весь файл целиком.
_TAIL_SCAN_BYTES = 256 * 1024


@dataclass(frozen=True)
class LogRecord:
    """Разобранная строка лога."""

    ts: str
    level: str
    source: str
    message: str


def parse_line(raw: str) -> LogRecord | None:
    """Разбирает строку лога; многострочные хвосты (трассировки) — None."""
    match = _LINE_RE.match(raw.rstrip("\n"))
    if match is None:
        return None
    return LogRecord(
        ts=match.group("ts"),
        level=match.group("level"),
        source=match.group("source"),
        message=match.group("message"),
    )


def _matches(
    record: LogRecord,
    *,
    level: str | None,
    sources: Sequence[str] | None,
    query: str | None,
) -> bool:
    """Проверяет запись против фильтров страницы.

    Источников может быть несколько — запись проходит, если совпал любой
    из выбранных префиксов.
    """
    if level and record.level != level:
        return False
    if sources and not any(record.source.startswith(item) for item in sources):
        return False
    if query:
        return query.lower() in record.message.lower()
    return True


def _iter_records_backwards(
    path: Path,
    *,
    scan_limit: int = _MAX_SCAN_BYTES,
    state: dict[str, bool] | None = None,
) -> Iterator[LogRecord]:
    """Отдаёт записи от новых к старым, читая файл с конца порциями.

    Args:
        scan_limit: Потолок чтения в байтах за один проход.
        state: Если передан, получает ``complete=True``, когда файл прочитан
            до начала (а не остановлен потолком сканирования).

    Yields:
        Разобранные записи; непросканированные байты не читаются вовсе.
    """
    with path.open("rb") as handle:
        handle.seek(0, 2)
        position = handle.tell()
        tail = b""
        scanned = 0
        while position > 0 and scanned < scan_limit:
            step = min(_SCAN_CHUNK, position)
            position -= step
            handle.seek(position)
            chunk = handle.read(step) + tail
            scanned += step
            lines = chunk.split(b"\n")
            # Первый элемент может быть обрывком строки — переносим в следующий круг.
            tail = lines.pop(0) if position > 0 else b""
            for raw in reversed(lines):
                record = parse_line(raw.decode("utf-8", "replace"))
                if record is not None:
                    yield record
        if tail:
            record = parse_line(tail.decode("utf-8", "replace"))
            if record is not None:
                yield record
        if state is not None:
            state["complete"] = position == 0


def read_logs(
    path: Path,
    *,
    level: str | None = None,
    sources: Sequence[str] | None = None,
    query: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[LogRecord], bool]:
    """Возвращает страницу отфильтрованных логов (новые сверху).

    Returns:
        (записи, усечён_ли_поиск_потолком_сканирования)
    """
    need = offset + limit
    collected: list[LogRecord] = []
    state: dict[str, bool] = {"complete": False}
    for record in _iter_records_backwards(path, state=state):
        if _matches(record, level=level, sources=sources, query=query):
            collected.append(record)
            if len(collected) >= need:
                break
    # Усечение — только когда файл не прочитан до начала и записей не хватило.
    truncated = len(collected) < need and not state["complete"]
    return collected[offset : offset + limit], truncated


def collect_sources(path: Path, *, limit: int = 4000) -> list[str]:
    """Собирает уникальные источники (имена логгеров) из хвоста файла."""
    seen: dict[str, None] = {}
    for index, record in enumerate(_iter_records_backwards(path)):
        if index >= limit:
            break
        seen.setdefault(record.source, None)
    return sorted(seen)


def read_tail(
    path: Path,
    *,
    after_offset: int | None,
    limit: int = 200,
    level: str | None = None,
    sources: Sequence[str] | None = None,
    query: str | None = None,
) -> tuple[list[LogRecord], int, bool]:
    """Дочитывает файл с позиции ``after_offset`` (для режима «следить»).

    При первом запросе (``after_offset`` не задан) и после ротации читается
    только хвост файла: догоняющий режим не должен тянуть весь файл целиком.
    Фильтры те же, что на странице, — иначе в таблицу попадут строки, которые
    пользователь отфильтровал.

    Returns:
        (записи в порядке от старых к новым, позиция для следующего запроса,
        была_ли_ротация)
    """
    try:
        size = path.stat().st_size
    except OSError:
        # Файл исчез между is_file() и stat() (ротация) — начинаем слежение заново.
        return [], 0, True
    negative = after_offset is not None and after_offset < 0
    rotated = after_offset is not None and (negative or after_offset > size)
    # Хвостовое сканирование — позиция произвольная (начало слежения или ротация).
    tail_scan = after_offset is None or rotated
    # Догон после долгой паузы (вкладка была закрыта) — тоже хвост: разница
    # больше потолка означает, что читать её целиком нельзя.
    if (
        not tail_scan
        and after_offset is not None
        and size - after_offset > _TAIL_SCAN_BYTES
    ):
        tail_scan = True
    if tail_scan:
        start = max(0, size - _TAIL_SCAN_BYTES)
    else:
        start = after_offset if after_offset is not None else 0

    try:
        with path.open("rb") as handle:
            handle.seek(start)
            chunk = handle.read()
            # Позиция после чтения — фактический конец файла: между stat() и read()
            # лог мог дорасти, и опираться на прежний size нельзя (задвоение строк).
            read_end = handle.tell()
    except OSError:
        # Файл ротировали в момент чтения — пустой ответ, слежение начнётся заново.
        return [], 0, True

    # При хвостовом сканировании первая строка может быть обрывком. Позиция
    # из предыдущего чтения всегда стоит на границе строки — там резать нельзя.
    if tail_scan and start > 0:
        first_newline = chunk.find(b"\n")
        if first_newline == -1:
            return [], read_end, rotated
        chunk = chunk[first_newline + 1 :]

    parts = chunk.split(b"\n")
    # Последний фрагмент без перевода строки мог быть дописан в момент чтения —
    # его не разбираем и не считаем прочитанным, иначе потеряем или задвоим строку.
    tail_partial = parts.pop() if parts else b""
    records: list[LogRecord] = []
    for raw in parts:
        record = parse_line(raw.decode("utf-8", "replace"))
        if record is not None and _matches(
            record, level=level, sources=sources, query=query
        ):
            records.append(record)

    next_offset = read_end - len(tail_partial)
    return records[-limit:], next_offset, rotated


def default_log_path() -> Path:
    """Путь к файлу логов бота: ``logs/error.log`` от корня проекта."""
    return Path(__file__).resolve().parents[2] / "logs" / "error.log"
