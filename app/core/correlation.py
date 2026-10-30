"""Correlation ID generation and propagation.

One correlation ID is created per inbound HTTP request and stored in a
``ContextVar`` so that every log line, agent execution and incident produced by
that request can be traced back to a single workflow.
"""

from __future__ import annotations

import re
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from uuid import uuid4

CORRELATION_HEADER = "X-Correlation-ID"
UNBOUND_CORRELATION_ID = "unbound"

#: Conservative allow-list: no whitespace or control characters, so a client
#: supplied value can never be used for log injection.
CORRELATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")

_correlation_id: ContextVar[str | None] = ContextVar("autoguard_correlation_id", default=None)


def generate_correlation_id(now: datetime | None = None) -> str:
    """Create a new correlation ID, e.g. ``CORR-20261030-9F1C2A7B44DE``."""
    moment = now or datetime.now(UTC)
    return f"CORR-{moment:%Y%m%d}-{uuid4().hex[:12].upper()}"


def sanitize_correlation_id(value: str | None) -> str | None:
    """Return a safe correlation ID or ``None`` when the value is unusable."""
    if not value:
        return None
    candidate = value.strip()
    return candidate if CORRELATION_ID_PATTERN.fullmatch(candidate) else None


def bind_correlation_id(value: str) -> Token[str | None]:
    """Bind a correlation ID to the current execution context."""
    return _correlation_id.set(value)


def reset_correlation_id(token: Token[str | None]) -> None:
    """Restore the previous correlation ID."""
    _correlation_id.reset(token)


def get_correlation_id() -> str:
    """Return the active correlation ID, or ``unbound`` outside a request."""
    return _correlation_id.get() or UNBOUND_CORRELATION_ID
