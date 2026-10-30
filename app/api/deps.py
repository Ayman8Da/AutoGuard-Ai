"""FastAPI dependency providers."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from app.services.telemetry_service import TelemetryService


def get_telemetry_service(request: Request) -> TelemetryService:
    """Return the application-scoped telemetry service."""
    return cast(TelemetryService, request.app.state.telemetry_service)


TelemetryServiceDep = Annotated[TelemetryService, Depends(get_telemetry_service)]
