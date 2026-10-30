"""Application error types mapped to HTTP responses by the API layer."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for expected, domain-level failures.

    Carries the HTTP status, a stable machine-readable error code and optional
    structured details. Unexpected exceptions are never represented by this
    class so they can be logged with a full stack trace.
    """

    status_code: int = 500
    code: str = "INTERNAL_ERROR"
    default_message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | list[Any] | None = None,
    ) -> None:
        self.message = message or self.default_message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details
        super().__init__(self.message)


class BadRequestError(AppError):
    status_code = 400
    code = "BAD_REQUEST"
    default_message = "The request could not be processed."


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"
    default_message = "The requested resource was not found."


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "SERVICE_UNAVAILABLE"
    default_message = "A required dependency is currently unavailable."


class AgentExecutionError(AppError):
    """Raised when an agent fails after exhausting its safe retry budget."""

    status_code = 500
    code = "AGENT_EXECUTION_FAILED"
    default_message = "An agent failed while processing the workflow."
