"""Structured logging configuration.

Logs are emitted as one JSON object per line by default, which makes them
directly ingestible by log aggregators. Every record automatically carries the
current ``correlation_id``, the service name and the environment.
"""

from __future__ import annotations

import logging
import sys
import time

from pythonjsonlogger.json import JsonFormatter

from app.core.config import LogFormat, Settings
from app.core.correlation import get_correlation_id

APP_LOGGER_NAME = "autoguard"


class CorrelationContextFilter(logging.Filter):
    """Attach correlation ID and service context to every log record."""

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._service = settings.app_name
        self._environment = settings.environment.value

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "correlation_id", None):
            record.correlation_id = get_correlation_id()
        record.service = self._service
        record.environment = self._environment
        return True


def build_log_formatter(settings: Settings) -> logging.Formatter:
    """Build the formatter matching the configured log format."""
    if settings.log_format is LogFormat.CONSOLE:
        return logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(correlation_id)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )

    formatter = JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
        json_ensure_ascii=False,
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    formatter.converter = time.gmtime
    return formatter


def configure_logging(settings: Settings) -> None:
    """(Re)configure the application logger hierarchy.

    Safe to call multiple times (e.g. once per app factory invocation in
    tests): previous handlers are detached and closed first.
    """
    logger = logging.getLogger(APP_LOGGER_NAME)
    logger.setLevel(settings.log_level)
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(build_log_formatter(settings))
    handler.addFilter(CorrelationContextFilter(settings))
    logger.addHandler(handler)


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger under the ``autoguard`` hierarchy."""
    if not name:
        return logging.getLogger(APP_LOGGER_NAME)
    if name.startswith(APP_LOGGER_NAME):
        return logging.getLogger(name)
    return logging.getLogger(f"{APP_LOGGER_NAME}.{name}")
