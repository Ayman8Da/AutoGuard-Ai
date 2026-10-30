"""Incident and runbook domain models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IncidentSeverity(StrEnum):
    """Operational severity of an incident."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(StrEnum):
    """Lifecycle state of an incident."""

    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class RunbookStep(BaseModel):
    """One ordered remediation step."""

    model_config = ConfigDict(extra="forbid")

    order: int = Field(ge=1)
    title: str
    detail: str


class Runbook(BaseModel):
    """Operational runbook attached to an incident type."""

    model_config = ConfigDict(extra="forbid")

    runbook_id: str
    title: str
    trigger: str
    summary: str
    owner: str
    steps: list[RunbookStep] = Field(default_factory=list)
    verification: str


class Incident(BaseModel):
    """A traceable operational incident derived from a workflow outcome."""

    model_config = ConfigDict(extra="forbid")

    incident_id: str
    code: str = Field(description="Stable incident type, e.g. CRITICAL_VEHICLE_RISK")
    title: str
    description: str
    severity: IncidentSeverity
    status: IncidentStatus = IncidentStatus.OPEN
    runbook_id: str
    runbook_title: str
    vehicle_id: str | None = None
    diagnostic_id: str | None = None
    workflow_id: str | None = None
    correlation_id: str
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
