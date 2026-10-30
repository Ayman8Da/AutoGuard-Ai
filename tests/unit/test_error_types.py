"""Unit tests for domain error types."""

from __future__ import annotations

import pytest
from app.core.errors import (
    AgentExecutionError,
    AppError,
    BadRequestError,
    NotFoundError,
    ServiceUnavailableError,
)


def test_base_error_defaults() -> None:
    error = AppError()

    assert error.status_code == 500
    assert error.code == "INTERNAL_ERROR"
    assert error.message == "An unexpected error occurred."
    assert error.details is None
    assert str(error) == error.message


def test_error_overrides_are_applied() -> None:
    error = AppError(
        "Custom failure",
        code="CUSTOM",
        status_code=418,
        details={"sensor": "battery_voltage"},
    )

    assert error.message == "Custom failure"
    assert error.code == "CUSTOM"
    assert error.status_code == 418
    assert error.details == {"sensor": "battery_voltage"}


@pytest.mark.parametrize(
    ("error_class", "status_code", "code"),
    [
        (BadRequestError, 400, "BAD_REQUEST"),
        (NotFoundError, 404, "NOT_FOUND"),
        (ServiceUnavailableError, 503, "SERVICE_UNAVAILABLE"),
        (AgentExecutionError, 500, "AGENT_EXECUTION_FAILED"),
    ],
)
def test_specialised_errors_carry_http_semantics(
    error_class: type[AppError], status_code: int, code: str
) -> None:
    error = error_class()

    assert error.status_code == status_code
    assert error.code == code
    assert error.message
