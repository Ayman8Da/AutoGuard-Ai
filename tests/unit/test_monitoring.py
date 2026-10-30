"""Unit tests for the Monitoring Agent's aggregation and bounds."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.models.diagnostics import (
    AgentExecution,
    AnalysisMode,
    DiagnosticReport,
    DiagnosticResult,
    ExecutionStatus,
    MaintenancePlan,
    MaintenancePriority,
    ReportStatus,
    ReportWarning,
    RiskAssessment,
    RiskLevel,
)
from app.monitoring.agent import MonitoringAgent
from simulator.scenarios import Scenario
from simulator.vehicle_simulator import build_scenario_telemetry

BASE_TIME = datetime(2025, 1, 15, 8, 0, tzinfo=UTC)


def _execution(
    agent_name: str,
    *,
    attempt: int = 1,
    status: ExecutionStatus = ExecutionStatus.SUCCESS,
    duration_ms: float = 10.0,
    offset_seconds: int = 0,
) -> AgentExecution:
    started = BASE_TIME + timedelta(seconds=offset_seconds)
    return AgentExecution(
        agent_name=agent_name,
        correlation_id="CORR-20261030-MONITOR001",
        workflow_id="WF-20261030-MONITOR001",
        status=status,
        attempt=attempt,
        started_at=started,
        ended_at=started + timedelta(milliseconds=duration_ms),
        execution_time_ms=duration_ms,
        error_type="RuntimeError" if status is ExecutionStatus.FAILED else None,
    )


def _report(
    *,
    status: ReportStatus = ReportStatus.COMPLETED,
    risk_level: RiskLevel = RiskLevel.LOW,
    warnings: list[ReportWarning] | None = None,
) -> DiagnosticReport:
    telemetry = build_scenario_telemetry(Scenario.NORMAL, "VH-001", BASE_TIME)
    return DiagnosticReport(
        diagnostic_id="DIAG-20261030-MONITOR001",
        workflow_id="WF-20261030-MONITOR001",
        telemetry_id="TEL-20261030-MONITOR001",
        correlation_id="CORR-20261030-MONITOR001",
        vehicle_id="VH-001",
        created_at=BASE_TIME,
        status=status,
        analysis_mode=(
            AnalysisMode.DEGRADED_DETERMINISTIC
            if status is ReportStatus.COMPLETED_DEGRADED
            else AnalysisMode.DETERMINISTIC
        ),
        telemetry=telemetry,
        diagnostic=DiagnosticResult(
            summary="No abnormal sensor readings detected.",
            narrative_source="mock",
        ),
        risk=RiskAssessment(level=risk_level, score=0),
        maintenance=MaintenancePlan(
            priority=MaintenancePriority.ROUTINE,
            actions=[],
            notes="Continue routine monitoring.",
        ),
        warnings=warnings or [],
        disclaimer="Simulated telemetry only.",
    )


def test_empty_snapshot_has_zeroed_counters() -> None:
    agent = MonitoringAgent()

    snapshot = agent.snapshot(
        uptime_seconds=12.5,
        diagnostics_stored=0,
        incidents_total=0,
        incidents_active=0,
        llm_provider="mock",
    )

    assert snapshot.workflows_started == 0
    assert snapshot.workflows_completed == 0
    assert snapshot.workflows_degraded == 0
    assert snapshot.workflows_failed == 0
    assert snapshot.workflow_success_rate_percent == 0.0
    assert snapshot.avg_workflow_duration_ms == 0.0
    assert snapshot.agent_executions_total == 0
    assert snapshot.agent_success_rate_percent == 0.0
    assert snapshot.agents == []
    assert snapshot.uptime_seconds == 12.5
    assert snapshot.llm_provider == "mock"


def test_agent_statistics_are_grouped_and_sorted() -> None:
    agent = MonitoringAgent()
    agent.record_execution(_execution("RiskAssessmentAgent", duration_ms=4.0))
    agent.record_execution(
        _execution("DiagnosticAgent", status=ExecutionStatus.FAILED, duration_ms=2.0)
    )
    agent.record_execution(
        _execution("DiagnosticAgent", attempt=2, duration_ms=8.0, offset_seconds=1)
    )

    statistics = agent.snapshot(
        uptime_seconds=1.0,
        diagnostics_stored=0,
        incidents_total=0,
        incidents_active=0,
        llm_provider="mock",
    ).agents

    assert [item.agent_name for item in statistics] == [
        "DiagnosticAgent",
        "RiskAssessmentAgent",
    ]
    diagnostic = statistics[0]
    assert diagnostic.executions == 2
    assert diagnostic.successes == 1
    assert diagnostic.failures == 1
    assert diagnostic.retries == 1
    assert diagnostic.success_rate_percent == 50.0
    assert diagnostic.avg_duration_ms == 5.0
    assert diagnostic.last_execution_at == BASE_TIME + timedelta(seconds=1, milliseconds=8)


def test_workflow_counters_distinguish_degraded_and_failed() -> None:
    agent = MonitoringAgent()
    agent.record_workflow_started()
    agent.record_workflow_started()
    agent.record_workflow_started()
    agent.record_execution(_execution("DiagnosticAgent"))
    agent.record_workflow_completed(_report(), 100.0)
    agent.record_workflow_completed(
        _report(
            status=ReportStatus.COMPLETED_DEGRADED,
            warnings=[ReportWarning(code="LLM_NARRATIVE_UNAVAILABLE", message="fallback")],
        ),
        300.0,
    )
    agent.record_workflow_failed("RuntimeError", 200.0)

    snapshot = agent.snapshot(
        uptime_seconds=1.0,
        diagnostics_stored=2,
        incidents_total=3,
        incidents_active=1,
        llm_provider="groq",
    )

    assert snapshot.workflows_started == 3
    assert snapshot.workflows_completed == 1
    assert snapshot.workflows_degraded == 1
    assert snapshot.workflows_failed == 1
    # A degraded report is still a successful (completed) workflow.
    assert snapshot.workflow_success_rate_percent == 66.67
    assert snapshot.avg_workflow_duration_ms == 200.0
    assert snapshot.agent_executions_total == 1
    assert snapshot.agent_failures_total == 0
    assert snapshot.agent_retries_total == 0
    assert snapshot.agent_success_rate_percent == 100.0
    assert snapshot.diagnostics_stored == 2
    assert snapshot.incidents_total == 3
    assert snapshot.incidents_active == 1


def test_execution_buffer_drops_the_oldest_entries() -> None:
    agent = MonitoringAgent(max_executions=2)
    agent.record_execution(_execution("AgentA", offset_seconds=0))
    agent.record_execution(_execution("AgentB", offset_seconds=1))
    agent.record_execution(_execution("AgentC", offset_seconds=2))

    snapshot = agent.snapshot(
        uptime_seconds=1.0,
        diagnostics_stored=0,
        incidents_total=0,
        incidents_active=0,
        llm_provider="mock",
    )

    assert [item.agent_name for item in snapshot.agents] == ["AgentB", "AgentC"]
    assert snapshot.agent_executions_total == 2


def test_invalid_buffer_size_is_rejected() -> None:
    with pytest.raises(ValueError, match="max_executions"):
        MonitoringAgent(max_executions=0)


def test_snapshot_clamps_negative_uptime() -> None:
    snapshot = MonitoringAgent().snapshot(
        uptime_seconds=-5.0,
        diagnostics_stored=0,
        incidents_total=0,
        incidents_active=0,
        llm_provider="mock",
    )

    assert snapshot.uptime_seconds == 0.0
