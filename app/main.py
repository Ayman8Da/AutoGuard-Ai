"""FastAPI application factory and ASGI entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.diagnostic import DiagnosticAgent
from app.agents.llm import build_narrative_client
from app.agents.maintenance import MaintenanceAgent
from app.agents.reporting import ReportingAgent
from app.agents.risk import RiskAssessmentAgent
from app.api.exception_handlers import register_exception_handlers
from app.api.system import router as system_router
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.correlation import CORRELATION_HEADER
from app.core.logging import configure_logging, get_logger
from app.core.middleware import CorrelationIdMiddleware
from app.incidents.manager import IncidentManager
from app.monitoring.agent import MonitoringAgent
from app.orchestration.workflow import DiagnosticWorkflow
from app.services.diagnostics_repository import InMemoryDiagnosticRepository
from app.services.diagnostics_service import DiagnosticsService
from app.services.repositories import InMemoryTelemetryRepository
from app.services.telemetry_service import TelemetryService
from app.utils.time import utc_now

APP_DESCRIPTION = """
Agentic predictive maintenance and intelligent vehicle fault diagnosis.

Simulated vehicle telemetry is processed by a supervised multi-agent workflow
(Orchestrator, Diagnostic, Risk Assessment, Maintenance, Reporting and
Monitoring agents). Every request is traceable through a correlation ID.
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure a FastAPI application instance."""
    settings = settings or get_settings()
    configure_logging(settings)
    lifecycle_logger = get_logger("app.lifecycle")

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.started_at = utc_now()
        lifecycle_logger.info(
            "application_started",
            extra={
                "version": settings.app_version,
                "environment": settings.environment.value,
                "llm_provider": settings.llm_provider.value,
            },
        )
        try:
            yield
        finally:
            uptime = (utc_now() - application.state.started_at).total_seconds()
            lifecycle_logger.info(
                "application_stopped",
                extra={"uptime_seconds": round(uptime, 3)},
            )

    application = FastAPI(
        title=settings.app_name,
        description=APP_DESCRIPTION,
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
        debug=settings.debug,
    )

    application.state.settings = settings
    application.state.started_at = utc_now()
    application.state.telemetry_repository = InMemoryTelemetryRepository(
        max_entries=settings.telemetry_buffer_size
    )
    application.state.telemetry_service = TelemetryService(
        application.state.telemetry_repository
    )

    narrative_client = build_narrative_client(settings)
    application.state.monitoring_agent = MonitoringAgent(
        max_executions=settings.monitoring_buffer_size
    )
    application.state.incident_manager = IncidentManager(
        max_entries=settings.incident_buffer_size
    )
    application.state.diagnostic_workflow = DiagnosticWorkflow(
        diagnostic_agent=DiagnosticAgent(
            narrative_client, max_llm_retries=settings.agent_max_retries
        ),
        risk_agent=RiskAssessmentAgent(),
        maintenance_agent=MaintenanceAgent(),
        reporting_agent=ReportingAgent(),
        max_retries=settings.agent_max_retries,
        monitoring=application.state.monitoring_agent,
    )
    application.state.diagnostics_repository = InMemoryDiagnosticRepository(
        max_entries=settings.diagnostics_buffer_size
    )
    application.state.diagnostics_service = DiagnosticsService(
        application.state.diagnostics_repository,
        application.state.diagnostic_workflow,
        incidents=application.state.incident_manager,
    )

    if settings.cors_origin_list:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=[CORRELATION_HEADER],
        )

    # Added last so it wraps the CORS middleware and every request is traced.
    application.add_middleware(
        CorrelationIdMiddleware,
        catch_unhandled=not settings.debug,
    )

    register_exception_handlers(application)
    application.include_router(system_router)
    application.include_router(api_router, prefix=settings.api_v1_prefix)
    return application


app = create_app()
