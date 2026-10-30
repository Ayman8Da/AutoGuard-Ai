"""End-to-end tests for the LangGraph diagnostic workflow."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.agents.diagnostic import DiagnosticAgent
from app.agents.llm import MockNarrativeClient, NarrativeRequest
from app.agents.maintenance import MaintenanceAgent
from app.agents.reporting import ReportingAgent
from app.agents.risk import RiskAssessmentAgent
from app.core.correlation import bind_correlation_id, reset_correlation_id
from app.core.errors import AgentExecutionError
from app.models.diagnostics import (
    AnalysisMode,
    ExecutionStatus,
    ReportStatus,
    RiskLevel,
)
from app.models.telemetry import TelemetryRecord
from app.orchestration.workflow import LLM_NARRATIVE_WARNING, DiagnosticWorkflow
from app.utils.ids import generate_id
from simulator.scenarios import Scenario
from simulator.vehicle_simulator import build_scenario_telemetry

TIMESTAMP = datetime(2025, 1, 15, 8, 30, tzinfo=UTC)
CORRELATION_ID = "CORR-20261030-WORKFLOW001"


def _record(scenario: Scenario, vehicle_id: str = "VH-001") -> TelemetryRecord:
    return TelemetryRecord(
        telemetry_id=generate_id("TEL", TIMESTAMP),
        correlation_id=CORRELATION_ID,
        received_at=TIMESTAMP,
        telemetry=build_scenario_telemetry(scenario, vehicle_id, TIMESTAMP),
    )


def _workflow(diagnostic_agent: DiagnosticAgent | None = None, max_retries: int = 1):
    return DiagnosticWorkflow(
        diagnostic_agent=diagnostic_agent or DiagnosticAgent(MockNarrativeClient()),
        risk_agent=RiskAssessmentAgent(),
        maintenance_agent=MaintenanceAgent(),
        reporting_agent=ReportingAgent(),
        max_retries=max_retries,
    )


class _FailingNarrativeClient:
    provider_name = "failing"

    async def summarise(self, request: NarrativeRequest) -> str:
        raise ConnectionError("provider offline")


class _BrokenDiagnosticAgent:
    name = "DiagnosticAgent"

    async def analyze(self, telemetry):  # noqa: ANN001 - protocol double
        raise RuntimeError("deterministic rule engine crashed")


class _FlakyDiagnosticAgent:
    name = "DiagnosticAgent"

    def __init__(self) -> None:
        self._delegate = DiagnosticAgent(MockNarrativeClient())
        self.calls = 0

    async def analyze(self, telemetry):  # noqa: ANN001 - protocol double
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("transient timeout")
        return await self._delegate.analyze(telemetry)


@pytest.mark.asyncio
async def test_workflow_produces_a_complete_traceable_report() -> None:
    token = bind_correlation_id(CORRELATION_ID)
    try:
        report = await _workflow().run(_record(Scenario.NORMAL))
    finally:
        reset_correlation_id(token)

    assert report.workflow_id.startswith("WF-")
    assert report.correlation_id == CORRELATION_ID
    assert report.vehicle_id == "VH-001"
    assert report.risk.level is RiskLevel.LOW
    assert report.status is ReportStatus.COMPLETED
    assert report.analysis_mode is AnalysisMode.DETERMINISTIC
    assert report.warnings == []
    assert report.maintenance.repair_performed is False

    assert [item.agent_name for item in report.agent_executions] == [
        "OrchestratorAgent",
        "DiagnosticAgent",
        "RiskAssessmentAgent",
        "MaintenanceAgent",
        "ReportingAgent",
    ]
    assert all(item.status is ExecutionStatus.SUCCESS for item in report.agent_executions)
    assert all(item.attempt == 1 for item in report.agent_executions)
    assert all(item.correlation_id == CORRELATION_ID for item in report.agent_executions)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scenario", "level"),
    [
        (Scenario.WARNING, RiskLevel.MEDIUM),
        (Scenario.CRITICAL, RiskLevel.CRITICAL),
        (Scenario.SENSOR_FAILURE, RiskLevel.HIGH),
    ],
)
async def test_workflow_classifies_each_scenario(scenario: Scenario, level: RiskLevel) -> None:
    report = await _workflow().run(_record(scenario))

    assert report.risk.level is level
    assert report.maintenance.priority.value in {"immediate", "urgent", "scheduled"}


@pytest.mark.asyncio
async def test_workflow_accepts_an_explicit_workflow_id() -> None:
    report = await _workflow().run(_record(Scenario.NORMAL), workflow_id="WF-EXPLICIT-1")

    assert report.workflow_id == "WF-EXPLICIT-1"


@pytest.mark.asyncio
async def test_llm_outage_degrades_report_without_failing_workflow() -> None:
    agent = DiagnosticAgent(_FailingNarrativeClient(), max_llm_retries=1)

    report = await _workflow(agent).run(_record(Scenario.CRITICAL))

    assert report.status is ReportStatus.COMPLETED_DEGRADED
    assert report.analysis_mode is AnalysisMode.DEGRADED_DETERMINISTIC
    assert [warning.code for warning in report.warnings] == [LLM_NARRATIVE_WARNING]
    assert report.diagnostic.narrative_source == "fallback"
    assert report.diagnostic.llm_attempts == 2
    assert "ConnectionError" in (report.diagnostic.llm_error or "")
    # Deterministic safety output is untouched by the narrative outage.
    assert report.risk.level is RiskLevel.CRITICAL
    assert report.risk.hard_override is True
    assert report.maintenance.actions


@pytest.mark.asyncio
async def test_agent_failure_after_retries_aborts_the_workflow() -> None:
    with pytest.raises(AgentExecutionError) as excinfo:
        await _workflow(_BrokenDiagnosticAgent(), max_retries=1).run(_record(Scenario.NORMAL))

    assert excinfo.value.details == {
        "agent_name": "DiagnosticAgent",
        "workflow_id": excinfo.value.details["workflow_id"],
        "attempts": 2,
        "error_type": "RuntimeError",
    }


@pytest.mark.asyncio
async def test_transient_agent_failure_is_retried_and_reported() -> None:
    agent = _FlakyDiagnosticAgent()

    report = await _workflow(agent, max_retries=1).run(_record(Scenario.NORMAL))

    assert agent.calls == 2
    executions = [item for item in report.agent_executions if item.agent_name == "DiagnosticAgent"]
    assert [item.attempt for item in executions] == [1, 2]
    assert [item.status for item in executions] == [
        ExecutionStatus.FAILED,
        ExecutionStatus.SUCCESS,
    ]
    assert executions[0].error_type == "TimeoutError"
