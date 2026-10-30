"""Unit tests for structured log formatting and correlation propagation."""

from __future__ import annotations

import io
import json
import logging

from app.core.config import LogFormat, Settings
from app.core.correlation import bind_correlation_id, reset_correlation_id
from app.core.logging import (
    CorrelationContextFilter,
    build_log_formatter,
    configure_logging,
)


def test_json_formatter_emits_structured_payload(settings: Settings) -> None:
    formatter = build_log_formatter(settings)
    record = logging.LogRecord(
        name="autoguard.agents.diagnostic",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="diagnostic_completed",
        args=(),
        exc_info=None,
    )
    record.correlation_id = "CORR-20261030-ABCDEF123456"
    record.agent = "DiagnosticAgent"

    payload = json.loads(formatter.format(record))

    assert payload["message"] == "diagnostic_completed"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "autoguard.agents.diagnostic"
    assert payload["correlation_id"] == "CORR-20261030-ABCDEF123456"
    assert payload["agent"] == "DiagnosticAgent"
    assert payload["timestamp"].endswith("Z")


def test_context_filter_injects_active_correlation_id(settings: Settings) -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(build_log_formatter(settings))
    handler.addFilter(CorrelationContextFilter(settings))

    logger = logging.getLogger("autoguard.test.filter")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    token = bind_correlation_id("CORR-20261030-123456789ABC")
    try:
        logger.info("risk_assessed", extra={"risk_level": "HIGH"})
    finally:
        reset_correlation_id(token)

    payload = json.loads(stream.getvalue())

    assert payload["correlation_id"] == "CORR-20261030-123456789ABC"
    assert payload["risk_level"] == "HIGH"
    assert payload["service"] == settings.app_name
    assert payload["environment"] == settings.environment.value


def test_configure_logging_is_idempotent(settings: Settings) -> None:
    configure_logging(settings)
    configure_logging(settings)

    logger = logging.getLogger("autoguard")

    assert len(logger.handlers) == 1
    assert logger.propagate is False


def test_console_format_contains_correlation_placeholder(
    settings: Settings,
) -> None:
    console_settings = settings.model_copy(update={"log_format": LogFormat.CONSOLE})

    formatter = build_log_formatter(console_settings)

    assert "%(correlation_id)s" in formatter._fmt  # noqa: SLF001 - format string assertion
