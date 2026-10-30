"""Operational monitoring endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import DiagnosticsServiceDep, IncidentManagerDep, MonitoringAgentDep
from app.monitoring.metrics import MonitoringSnapshot
from app.utils.time import utc_now

router = APIRouter(tags=["Monitoring"])


@router.get(
    "/monitoring",
    response_model=MonitoringSnapshot,
    summary="Agent and workflow monitoring snapshot",
    description=(
        "Returns process-level counters, per-agent execution statistics and incident "
        "counts. Statistics cover the current process lifetime and reset on restart."
    ),
)
async def get_monitoring(
    request: Request,
    monitoring: MonitoringAgentDep,
    diagnostics: DiagnosticsServiceDep,
    incidents: IncidentManagerDep,
) -> MonitoringSnapshot:
    started_at = request.app.state.started_at
    return monitoring.snapshot(
        uptime_seconds=(utc_now() - started_at).total_seconds(),
        diagnostics_stored=diagnostics.count(),
        incidents_total=incidents.count(),
        incidents_active=incidents.active_count(),
        llm_provider=request.app.state.settings.llm_provider.value,
    )
