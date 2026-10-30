"""Unit tests for incidents and operational runbooks."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.agents.diagnostic import DiagnosticAgent
from app.agents.llm import MockNarrativeClient
from app.agents.maintenance import MaintenanceAgent
from app.agents.reporting import ReportingAgent
from app.agents.risk import RiskAssessmentAgent
from app.core.errors import AgentExecutionError
from app.incidents.manager import IncidentManager
from app.incidents.models import IncidentSeverity, IncidentStatus
from app.incidents.runbooks import RUNBOOKS, get_runbook
from app.models.diagnostics import ReportWarning
from app.models.telemetry import TelemetryRecord
from app.utils.ids import generate_id
from simulator.scenarios import Scenario
from simulator.vehicle_simulator import build_scenario_telemetry

TIMESTAMP = datetime(2025, 1, 15, 8, 0, tzinfo=UTC)
CORRELATION_ID = "CORR-20261030-INCIDENT01"


async def _report(
    scenario: Scenario,
    *,
    degraded: bool = False,
    vehicle_id: str = "VH-001",
):
    record = TelemetryRecord(
        telemetry_id=generate_id("TEL", TIMESTAMP),
        correlation_id=CORRELATION_ID,
        received_at=TIMESTAMP,
        telemetry=build_scenario_telemetry(scenario, vehicle_id, TIMESTAMP),
    )
    diagnostic = await DiagnosticAgent(MockNarrativeClient()).analyze(record.telemetry)
    warnings = []
    if degraded:
        diagnostic = diagnostic.model_copy(
            update={
                "narrative_source": "fallback",
                "llm_error": "ConnectionError: provider offline",
                "llm_attempts": 2,
            }
        )
        warnings = [
            ReportWarning(
                code="LLM_NARRATIVE_UNAVAILABLE",
                message="The narrative provider was unavailable.",
            )
        ]
    risk = RiskAssessmentAgent().assess(record.telemetry, diagnostic)
    maintenance = MaintenanceAgent().recommend(diagnostic, risk)
    return ReportingAgent().build(
        telemetry_record=record,
        workflow_id=generate_id("WF", TIMESTAMP),
        diagnostic=diagnostic,
        risk=risk,
        maintenance=maintenance,
        executions=[],
        warnings=warnings,
    )


def _agent_error() -> AgentExecutionError:
    return AgentExecutionError(
        "DiagnosticAgent failed after 2 attempt(s).",
        details={
            "agent_name": "DiagnosticAgent",
            "workflow_id": "WF-20261030-FAILED01",
            "attempts": 2,
            "error_type": "RuntimeError",
        },
    )


def test_three_runbooks_are_registered_and_complete() -> None:
    assert set(RUNBOOKS) == {
        "high_risk_vehicle",
        "agent_failure",
        "llm_provider_failure",
    }
    for runbook in RUNBOOKS.values():
        assert runbook.steps
        assert [step.order for step in runbook.steps] == list(
            range(1, len(runbook.steps) + 1)
        )
        assert runbook.owner
        assert runbook.verification
        assert runbook.trigger


def test_unknown_runbook_is_rejected() -> None:
    with pytest.raises(KeyError, match="unknown runbook"):
        get_runbook("does_not_exist")


@pytest.mark.asyncio
async def test_critical_report_raises_high_severity_incident() -> None:
    manager = IncidentManager()

    report = await _report(Scenario.CRITICAL, vehicle_id="VH-003")
    incidents = manager.process_report(report)

    assert len(incidents) == 1
    incident = incidents[0]
    assert incident.code == "CRITICAL_VEHICLE_RISK"
    assert incident.severity is IncidentSeverity.CRITICAL
    assert incident.status is IncidentStatus.OPEN
    assert incident.runbook_id == "high_risk_vehicle"
    assert incident.runbook_title == "High-risk vehicle response"
    assert incident.vehicle_id == "VH-003"
    assert incident.diagnostic_id == report.diagnostic_id
    assert incident.workflow_id == report.workflow_id
    assert incident.correlation_id == CORRELATION_ID
    assert incident.metadata["risk_score"] == report.risk.score
    assert incident.metadata["hard_override"] is True
    assert "ENGINE_TEMPERATURE_CRITICAL" in incident.metadata["finding_codes"]
    assert "P0217" in incident.metadata["dtc_codes"]
    assert manager.get_incident(incident.incident_id) == incident
    assert manager.count() == 1
    assert manager.active_count() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", [Scenario.NORMAL, Scenario.WARNING, Scenario.SENSOR_FAILURE])
async def test_non_critical_report_raises_no_incident(scenario: Scenario) -> None:
    manager = IncidentManager()

    incidents = manager.process_report(await _report(scenario))

    assert incidents == []
    assert manager.count() == 0


@pytest.mark.asyncio
async def test_degraded_narrative_raises_medium_incident() -> None:
    manager = IncidentManager()

    report = await _report(Scenario.WARNING, degraded=True)
    incidents = manager.process_report(report)

    assert len(incidents) == 1
    incident = incidents[0]
    assert incident.code == "LLM_PROVIDER_FAILURE"
    assert incident.severity is IncidentSeverity.MEDIUM
    assert incident.runbook_id == "llm_provider_failure"
    assert incident.metadata["analysis_mode"] == "degraded_deterministic"
    assert incident.metadata["llm_attempts"] == 2


@pytest.mark.asyncio
async def test_critical_and_degraded_report_raises_two_incidents() -> None:
    manager = IncidentManager()

    report = await _report(Scenario.CRITICAL, degraded=True)
    incidents = manager.process_report(report)

    assert {incident.code for incident in incidents} == {
        "CRITICAL_VEHICLE_RISK",
        "LLM_PROVIDER_FAILURE",
    }
    assert manager.count() == 2


def test_agent_failure_incident_references_runbook_and_details() -> None:
    manager = IncidentManager()

    incident = manager.record_agent_failure(_agent_error(), correlation_id=CORRELATION_ID)

    assert incident.code == "AGENT_EXECUTION_FAILED"
    assert incident.severity is IncidentSeverity.HIGH
    assert incident.runbook_id == "agent_failure"
    assert incident.title == "DiagnosticAgent failed"
    assert incident.workflow_id == "WF-20261030-FAILED01"
    assert incident.correlation_id == CORRELATION_ID
    assert incident.metadata == {
        "agent_name": "DiagnosticAgent",
        "attempts": 2,
        "error_type": "RuntimeError",
        "error_message": "DiagnosticAgent failed after 2 attempt(s).",
    }


@pytest.mark.asyncio
async def test_listing_is_newest_first_and_filters_narrow_results() -> None:
    manager = IncidentManager()
    critical = await _report(Scenario.CRITICAL, vehicle_id="VH-003")
    degraded = await _report(Scenario.WARNING, degraded=True, vehicle_id="VH-002")
    critical_incident, = [
        item
        for item in manager.process_report(critical)
        if item.code == "CRITICAL_VEHICLE_RISK"
    ]
    narrative_incident, = manager.process_report(degraded)

    assert [item.code for item in manager.list_incidents()] == [
        "LLM_PROVIDER_FAILURE",
        "CRITICAL_VEHICLE_RISK",
    ]
    assert manager.list_incidents(limit=1) == [narrative_incident]
    assert manager.list_incidents(severity=IncidentSeverity.CRITICAL) == [critical_incident]
    assert manager.list_incidents(status=IncidentStatus.RESOLVED) == []
    assert manager.list_incidents(vehicle_id="VH-003") == [critical_incident]

    with pytest.raises(ValueError, match="limit"):
        manager.list_incidents(limit=0)


@pytest.mark.asyncio
async def test_capacity_evicts_the_oldest_incidents() -> None:
    manager = IncidentManager(max_entries=1)
    first = await _report(Scenario.CRITICAL, vehicle_id="VH-001")
    second = await _report(Scenario.CRITICAL, vehicle_id="VH-002")

    first_incident, = manager.process_report(first)
    second_incident, = manager.process_report(second)

    assert manager.count() == 1
    assert manager.get_incident(first_incident.incident_id) is None
    assert manager.get_incident(second_incident.incident_id) == second_incident


def test_invalid_capacity_is_rejected() -> None:
    with pytest.raises(ValueError, match="max_entries"):
        IncidentManager(max_entries=0)
