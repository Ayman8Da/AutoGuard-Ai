"""Unit tests for correlation ID generation and propagation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.core.correlation import (
    CORRELATION_ID_PATTERN,
    UNBOUND_CORRELATION_ID,
    bind_correlation_id,
    generate_correlation_id,
    get_correlation_id,
    reset_correlation_id,
    sanitize_correlation_id,
)


def test_generated_id_matches_expected_format() -> None:
    correlation_id = generate_correlation_id()

    assert CORRELATION_ID_PATTERN.fullmatch(correlation_id)
    assert correlation_id.startswith("CORR-")
    assert len(correlation_id) == len("CORR-20261030-") + 12


def test_generated_id_uses_supplied_timestamp() -> None:
    moment = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)

    correlation_id = generate_correlation_id(moment)

    assert correlation_id.startswith("CORR-20261030-")


def test_generated_ids_are_unique() -> None:
    ids = {generate_correlation_id() for _ in range(200)}

    assert len(ids) == 200


def test_context_starts_unbound() -> None:
    assert get_correlation_id() == UNBOUND_CORRELATION_ID


def test_bind_and_reset_round_trip() -> None:
    token = bind_correlation_id("CORR-20261030-ABCDEF123456")

    assert get_correlation_id() == "CORR-20261030-ABCDEF123456"

    reset_correlation_id(token)

    assert get_correlation_id() == UNBOUND_CORRELATION_ID


@pytest.mark.parametrize(
    "value",
    [
        "CORR-20261030-ABCDEF123456",
        "abc-1234",
        "trace_42",
        "A" * 128,
    ],
)
def test_sanitize_accepts_valid_ids(value: str) -> None:
    assert sanitize_correlation_id(value) == value


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "short",
        "has space inside",
        "line\nbreak",
        "semi;colon",
        "tab\there",
        "A" * 129,
        "=SUM(A1)",
    ],
)
def test_sanitize_rejects_invalid_ids(value: str | None) -> None:
    assert sanitize_correlation_id(value) is None
