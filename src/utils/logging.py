"""
Loguru logging configuration for the entire application.

Provides:
- Colorful console output
- File logging with rotation (auto-cleanup old logs)
- JSON logging (optional, disabled by default)
- InterceptHandler to bridge all standard-library logging calls into Loguru
"""

import logging
import sys
import types
from pathlib import Path

from loguru import logger


class InterceptHandler(logging.Handler):
    """
    Redirects all standard-library logging messages to Loguru.

    This ensures that third-party libraries using the standard ``logging``
    module (e.g. ``aiogram``, ``httpx``, ``aiosqlite``) appear in the same
    Loguru sink and with the same formatting as the project's own logs.
    """

    def emit(self, record: logging.LogRecord) -> None:
        # Get the corresponding Loguru level
        level: str | int
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find the caller frame
        current: types.FrameType | None = logging.currentframe()
        depth = 2
        while current is not None and depth > 0:
            current = current.f_back
            depth -= 1

        logger.opt(depth=6, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(
    *,
    log_dir: str = "logs",
    log_file: str = "error.log",
    rotation: str = "10 MB",
    retention: str = "30 days",
    json_serialize: bool = False,
    level: str = "INFO",
) -> None:
    """
    Configure Loguru sinks and install the intercept handler.

    Parameters
    ----------
    log_dir:
        Directory where log files are stored.
    log_file:
        Base name of the log file (e.g. ``error.log``).
    rotation:
        Rotate log files when they reach this size (e.g. ``"10 MB"``).
    retention:
        Keep log files for this duration (e.g. ``"30 days"``).
    json_serialize:
        If ``True``, also write a JSON-structured log file.
    level:
        Minimum log level for console output.
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Remove any default Loguru sink
    logger.remove()

    # --- Console sink (colorful, human-readable) ---
    logger.add(
        sys.stdout,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        level=level.upper(),
        colorize=True,
    )

    # --- File sink (plain text, with rotation) ---
    logger.add(
        log_path / log_file,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
            "{name}:{function}:{line} | {message}"
        ),
        level="DEBUG",
        rotation=rotation,
        retention=retention,
        encoding="utf-8",
    )

    # --- Optional JSON sink ---
    if json_serialize:
        logger.add(
            log_path / f"{Path(log_file).stem}.json",
            level="DEBUG",
            rotation=rotation,
            retention=retention,
            serialize=True,
            encoding="utf-8",
        )

    # --- Bridge standard ``logging`` → Loguru ---
    intercept_handler = InterceptHandler()
    logging.basicConfig(handlers=[intercept_handler], level=logging.DEBUG, force=True)

    # Suppress noisy loggers from third-party libraries
    for lib_name in (
        "aiogram",
        "httpx",
        "httpcore",
        "aiosqlite",
        "asyncio",
    ):
        lib_logger = logging.getLogger(lib_name)
        lib_logger.handlers = [intercept_handler]
        lib_logger.propagate = False

    logger.info(
        "Loguru logging initialised (level=%s, file=%s)", level, log_path / log_file
    )
