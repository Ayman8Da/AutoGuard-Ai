"""Monitoring endpoint contracts."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AgentStatistics(BaseModel):
    """Aggregated execution statistics for one agent."""

    model_config = ConfigDict(extra="forbid")

    agent_name: str
    executions: int = Field(ge=0)
    successes: int = Field(ge=0)
    failures: int = Field(ge=0)
    retries: int = Field(ge=0, description="Attempts beyond the first attempt")
    success_rate_percent: float = Field(ge=0, le=100)
    avg_duration_ms: float = Field(ge=0)
    last_execution_at: datetime | None = None


class MonitoringSnapshot(BaseModel):
    """Current process-level monitoring view."""

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    uptime_seconds: float = Field(ge=0)
    llm_provider: str

    workflows_started: int = Field(ge=0)
    workflows_completed: int = Field(ge=0)
    workflows_degraded: int = Field(ge=0)
    workflows_failed: int = Field(ge=0)
    workflow_success_rate_percent: float = Field(ge=0, le=100)
    avg_workflow_duration_ms: float = Field(ge=0)

    agent_executions_total: int = Field(ge=0)
    agent_failures_total: int = Field(ge=0)
    agent_retries_total: int = Field(ge=0)
    agent_success_rate_percent: float = Field(ge=0, le=100)
    agents: list[AgentStatistics] = Field(default_factory=list)

    diagnostics_stored: int = Field(ge=0)
    incidents_total: int = Field(ge=0)
    incidents_active: int = Field(ge=0)
