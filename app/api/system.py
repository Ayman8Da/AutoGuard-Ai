"""Root-level operational endpoints: service metadata and health probe."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Request

from app.core.config import Settings
from app.models.common import (
    ComponentHealth,
    HealthResponse,
    HealthStatus,
    ServiceInfo,
)
from app.utils.time import utc_now

router = APIRouter()


@router.get("/", response_model=ServiceInfo, include_in_schema=False)
async def service_info(request: Request) -> ServiceInfo:
    """Small discovery payload for humans and smoke tests."""
    settings: Settings = request.app.state.settings
    return ServiceInfo(
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment.value,
        docs="/docs",
        health="/health",
        api_prefix=settings.api_v1_prefix,
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["System"],
    summary="Health probe",
    description=(
        "Liveness/readiness probe used by Docker, Render and load balancers. "
        "Returns 200 while the HTTP stack and configuration are usable."
    ),
)
async def health(request: Request) -> HealthResponse:
    settings: Settings = request.app.state.settings
    started_at: datetime = request.app.state.started_at
    now = utc_now()
    uptime_seconds = max(0.0, (now - started_at).total_seconds())

    checks = {
        "api": ComponentHealth(status=HealthStatus.OK, detail="HTTP stack responding"),
        "configuration": ComponentHealth(
            status=HealthStatus.OK,
            detail=(
                f"environment={settings.environment.value}, "
                f"llm_provider={settings.llm_provider.value}"
            ),
        ),
    }

    return HealthResponse(
        status=HealthStatus.OK,
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment.value,
        timestamp=now,
        uptime_seconds=round(uptime_seconds, 3),
        correlation_id=request.state.correlation_id,
        checks=checks,
    )
