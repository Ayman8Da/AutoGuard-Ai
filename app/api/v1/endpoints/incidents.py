"""Incident read endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import IncidentManagerDep
from app.incidents.models import Incident, IncidentSeverity, IncidentStatus

router = APIRouter(tags=["Incidents"])


@router.get(
    "/incidents",
    response_model=list[Incident],
    summary="List incidents",
    description=(
        "Returns operational incidents newest first. Incidents are raised for CRITICAL "
        "vehicle risk, degraded LLM narration and agent failures, and each one references "
        "an operational runbook."
    ),
)
async def list_incidents(
    manager: IncidentManagerDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    status: IncidentStatus | None = None,
    severity: IncidentSeverity | None = None,
    vehicle_id: str | None = None,
) -> list[Incident]:
    return manager.list_incidents(
        limit=limit,
        status=status,
        severity=severity,
        vehicle_id=vehicle_id,
    )
