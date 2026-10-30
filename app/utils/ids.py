"""Identifier generation helpers."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.utils.time import utc_now


def generate_id(prefix: str, now: datetime | None = None) -> str:
    """Generate a sortable, human-readable identifier.

    Example: ``TEL-20261030-9F1C2A7B44``.
    """
    moment = now or utc_now()
    return f"{prefix.upper()}-{moment:%Y%m%d}-{uuid4().hex[:10].upper()}"
