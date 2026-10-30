"""FastAPI dependency providers."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from app.orchestration.workflow import DiagnosticWorkflow
from app.services.diagnostics_service import DiagnosticsService
from app.services.telemetry_service import TelemetryService


def get_telemetry_service(request: Request) -> TelemetryService:
    """Return the application-scoped telemetry service."""
    return cast(TelemetryService, request.app.state.telemetry_service)


def get_diagnostics_service(request: Request) -> DiagnosticsService:
    """Return the application-scoped diagnostics service."""
    return cast(DiagnosticsService, request.app.state.diagnostics_service)


def get_diagnostic_workflow(request: Request) -> DiagnosticWorkflow:
    """Return the application-scoped workflow (used by tests to inject doubles)."""
    return cast(DiagnosticWorkflow, request.app.state.diagnostic_workflow)


TelemetryServiceDep = Annotated[TelemetryService, Depends(get_telemetry_service)]
DiagnosticsServiceDep = Annotated[DiagnosticsService, Depends(get_diagnostics_service)]
DiagnosticWorkflowDep = Annotated[DiagnosticWorkflow, Depends(get_diagnostic_workflow)]
