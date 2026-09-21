"""Application core logging configuration."""

import logging
import logging.handlers
import os

from app.core.config import get_settings


def configure_logging() -> None:
    """Configure console and rotating-file logging."""

    settings = get_settings()

    log_directory = os.path.dirname(settings.log_file)
    if log_directory:
        os.makedirs(log_directory, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level.upper())

    root_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = logging.handlers.RotatingFileHandler(
        settings.log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


def debug_logger(name: str) -> logging.Logger:
    """
    Return a logger that ONLY emits when `debug_pipeline` is enabled.

    Uses WARNING level so records are not filtered out by the root
    logger's INFO level. When `debug_pipeline` is False (production),
    a filter drops all records from this logger.
    """
    logger = logging.getLogger(name)
    settings = get_settings()

    if not settings.debug_pipeline:

        class _DropAll(logging.Filter):
            def filter(self, record: logging.LogRecord) -> bool:
                return False

        if not any(isinstance(f, _DropAll) for f in logger.filters):
            logger.addFilter(_DropAll())

    return logger
