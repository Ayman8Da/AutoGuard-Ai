"""Shared API response models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Machine-readable error payload."""

    code: str = Field(description="Stable error code, e.g. NOT_FOUND")
    message: str = Field(description="Human-readable error message")
    details: dict[str, Any] | list[Any] | None = Field(
        default=None, description="Optional structured context (e.g. validation errors)"
    )
    correlation_id: str = Field(description="Correlation ID for this request")


class ErrorResponse(BaseModel):
    """Envelope used for every error returned by the API."""

    error: ErrorDetail


class HealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"


class ComponentHealth(BaseModel):
    """Health of a single application component."""

    status: HealthStatus
    detail: str | None = None


class HealthResponse(BaseModel):
    """Payload returned by the health probe."""

    status: HealthStatus
    service: str
    version: str
    environment: str
    timestamp: datetime
    uptime_seconds: float
    correlation_id: str
    checks: dict[str, ComponentHealth]


class ServiceInfo(BaseModel):
    """Service metadata exposed at the API root."""

    service: str
    version: str
    environment: str
    docs: str
    health: str
    api_prefix: str
