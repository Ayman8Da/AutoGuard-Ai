"""Shared state for the diagnostic LangGraph workflow.

The state is intentionally small: each node reads the outputs of the previous
one and adds its own artifact. Agent executions are *not* stored here because
they must also survive a failed node (LangGraph discards state mutations when a
node raises); ``AgentRunner`` keeps that ledger instead.
"""

from __future__ import annotations

from typing import TypedDict

from app.models.diagnostics import (
    DiagnosticReport,
    DiagnosticResult,
    MaintenancePlan,
    RiskAssessment,
)
from app.models.telemetry import TelemetryRecord


class WorkflowState(TypedDict, total=False):
    """Graph state passed between diagnostic agents."""

    telemetry_record: TelemetryRecord
    workflow_id: str
    diagnostic: DiagnosticResult
    risk: RiskAssessment
    maintenance: MaintenancePlan
    report: DiagnosticReport
