"""Diagnostic domain models shared by agents, API and reporting."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.telemetry import VehicleTelemetry


class FindingSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    HIGH = "high"
    CRITICAL = "critical"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MaintenancePriority(StrEnum):
    IMMEDIATE = "immediate"
    URGENT = "urgent"
    SCHEDULED = "scheduled"
    ROUTINE = "routine"


class ReportStatus(StrEnum):
    COMPLETED = "completed"
    COMPLETED_DEGRADED = "completed_degraded"


class AnalysisMode(StrEnum):
    DETERMINISTIC = "deterministic"
    LLM_ASSISTED = "llm_assisted"
    DEGRADED_DETERMINISTIC = "degraded_deterministic"


class ExecutionStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


class Finding(BaseModel):
    """One abnormal condition detected from telemetry."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(description="Stable finding code, e.g. ENGINE_TEMPERATURE_HIGH")
    sensor: str | None = Field(default=None, description="Sensor field involved, if any")
    title: str
    detail: str
    severity: FindingSeverity
    value: float | None = None
    unit: str | None = None
    threshold: str | None = None


class DTCInterpretation(BaseModel):
    """Interpretation of a diagnostic trouble code."""

    model_config = ConfigDict(extra="forbid")

    code: str
    description: str
    system: str
    severity: FindingSeverity
    known: bool = Field(description="False when the code is not in the local catalogue")


class DiagnosticResult(BaseModel):
    """Structured output of the Diagnostic Agent."""

    model_config = ConfigDict(extra="forbid")

    findings: list[Finding] = Field(default_factory=list)
    dtc_interpretations: list[DTCInterpretation] = Field(default_factory=list)
    unavailable_sensors: list[str] = Field(default_factory=list)
    suspected_faults: list[str] = Field(default_factory=list)
    summary: str
    narrative_source: Literal["mock", "llm", "fallback"]
    llm_attempts: int = Field(default=0, ge=0)
    llm_error: str | None = None
    llm_duration_ms: float | None = Field(default=None, ge=0)


class RiskReason(BaseModel):
    """Deterministic explanation of part of the risk score."""

    model_config = ConfigDict(extra="forbid")

    code: str
    description: str
    score: int = Field(ge=0)


class RiskAssessment(BaseModel):
    """Deterministic risk classification. Never produced by an LLM."""

    model_config = ConfigDict(extra="forbid")

    level: RiskLevel
    score: int = Field(ge=0)
    reasons: list[RiskReason] = Field(default_factory=list)
    hard_override: bool = Field(
        default=False,
        description="True when a safety-critical threshold forced CRITICAL",
    )
    threshold_version: str = "1.0"


class MaintenanceAction(BaseModel):
    """One recommended maintenance/inspection action."""

    model_config = ConfigDict(extra="forbid")

    title: str
    description: str
    category: str
    priority: MaintenancePriority
    rationale: str
    related_findings: list[str] = Field(default_factory=list)


class MaintenancePlan(BaseModel):
    """Recommendations only: no repair has been performed."""

    model_config = ConfigDict(extra="forbid")

    priority: MaintenancePriority
    actions: list[MaintenanceAction] = Field(default_factory=list)
    notes: str
    repair_performed: Literal[False] = False


class AgentExecution(BaseModel):
    """Observation of a single agent attempt."""

    model_config = ConfigDict(extra="forbid")

    agent_name: str
    correlation_id: str
    workflow_id: str
    status: ExecutionStatus
    attempt: int = Field(ge=1)
    started_at: datetime
    ended_at: datetime
    execution_time_ms: float = Field(ge=0)
    error_type: str | None = None
    error_message: str | None = None


class ReportWarning(BaseModel):
    """Non-fatal degradation explicitly recorded in the report."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class DiagnosticReport(BaseModel):
    """Complete, traceable output of the diagnostic workflow."""

    model_config = ConfigDict(extra="forbid")

    diagnostic_id: str
    workflow_id: str
    telemetry_id: str
    correlation_id: str
    vehicle_id: str
    created_at: datetime
    status: ReportStatus
    analysis_mode: AnalysisMode
    telemetry: VehicleTelemetry
    diagnostic: DiagnosticResult
    risk: RiskAssessment
    maintenance: MaintenancePlan
    agent_executions: list[AgentExecution] = Field(default_factory=list)
    warnings: list[ReportWarning] = Field(default_factory=list)
    disclaimer: str


class DiagnosticSummary(BaseModel):
    """Compact report view for list endpoints."""

    model_config = ConfigDict(extra="forbid")

    diagnostic_id: str
    workflow_id: str
    vehicle_id: str
    created_at: datetime
    status: ReportStatus
    analysis_mode: AnalysisMode
    risk_level: RiskLevel
    correlation_id: str
