"""Unit tests for the diagnostic, risk, maintenance and reporting agents."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.agents.diagnostic import DiagnosticAgent
from app.agents.llm import MockNarrativeClient, NarrativeRequest
from app.agents.maintenance import MaintenanceAgent
from app.agents.reporting import DISCLAIMER, ReportingAgent
from app.agents.risk import RiskAssessmentAgent
from app.models.diagnostics import (
    AnalysisMode,
    MaintenancePriority,
    ReportStatus,
    ReportWarning,
    RiskLevel,
)
from app.models.telemetry import TelemetryRecord
from app.utils.ids import generate_id
from simulator.scenarios import Scenario
from simulator.vehicle_simulator import build_scenario_telemetry

TIMESTAMP = datetime(2025, 1, 15, 8, 30, tzinfo=UTC)


def _record(scenario: Scenario, vehicle_id: str = "VH-001") -> TelemetryRecord:
    return TelemetryRecord(
        telemetry_id=generate_id("TEL", TIMESTAMP),
        correlation_id="CORR-20261030-AGENTTEST1",
        received_at=TIMESTAMP,
        telemetry=build_scenario_telemetry(scenario, vehicle_id, TIMESTAMP),
    )


class _StaticClient:
    provider_name = "static"

    def __init__(self, summary: str = "LLM summary.") -> None:
        self.summary = summary
        self.calls = 0

    async def summarise(self, request: NarrativeRequest) -> str:
        self.calls += 1
        return self.summary


class _FailingClient:
    provider_name = "failing"

    def __init__(self) -> None:
        self.calls = 0

    async def summarise(self, request: NarrativeRequest) -> str:
        self.calls += 1
        raise ConnectionError("provider offline")


class _FlakyClient:
    provider_name = "flaky"

    def __init__(self) -> None:
        self.calls = 0

    async def summarise(self, request: NarrativeRequest) -> str:
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("first attempt timed out")
        return "Recovered narrative."


# --------------------------------------------------------------------------- #
# Diagnostic Agent
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_normal_frame_has_no_findings() -> None:
    diagnostic = await DiagnosticAgent(MockNarrativeClient()).analyze(
        _record(Scenario.NORMAL).telemetry
    )

    assert diagnostic.findings == []
    assert diagnostic.dtc_interpretations == []
    assert diagnostic.unavailable_sensors == []
    assert diagnostic.suspected_faults == []
    assert diagnostic.narrative_source == "mock"
    assert "No abnormal sensor readings" in diagnostic.summary


@pytest.mark.asyncio
async def test_critical_frame_reports_findings_codes_and_suspects() -> None:
    diagnostic = await DiagnosticAgent(MockNarrativeClient()).analyze(
        _record(Scenario.CRITICAL).telemetry
    )

    codes = {finding.code for finding in diagnostic.findings}
    assert codes == {
        "ENGINE_TEMPERATURE_CRITICAL",
        "BATTERY_VOLTAGE_CRITICAL",
        "ENGINE_VIBRATION_CRITICAL",
    }
    assert [item.code for item in diagnostic.dtc_interpretations] == ["P0217", "P0301"]
    assert all(item.known for item in diagnostic.dtc_interpretations)
    assert "Severe cooling failure" in " ".join(diagnostic.suspected_faults)
    assert "Cylinder 1 misfire" in " ".join(diagnostic.suspected_faults)
    assert diagnostic.findings[0].unit == "°C"
    assert diagnostic.findings[0].threshold == "> 118 °C"


@pytest.mark.asyncio
async def test_sensor_failure_is_a_finding_not_a_validation_error() -> None:
    diagnostic = await DiagnosticAgent(MockNarrativeClient()).analyze(
        _record(Scenario.SENSOR_FAILURE).telemetry
    )

    assert diagnostic.unavailable_sensors == ["engine_temperature_c", "engine_vibration_mm_s"]
    unavailable = [item for item in diagnostic.findings if item.code == "SENSOR_UNAVAILABLE"]
    assert len(unavailable) == 2
    assert {item.sensor for item in unavailable} == {
        "engine_temperature_c",
        "engine_vibration_mm_s",
    }
    assert any(
        "sensor, wiring or connector fault" in suspect
        for suspect in diagnostic.suspected_faults
    )


@pytest.mark.asyncio
async def test_llm_narrative_is_used_when_available() -> None:
    client = _StaticClient("Cooling and electrical faults are likely.")

    diagnostic = await DiagnosticAgent(client).analyze(_record(Scenario.WARNING).telemetry)

    assert diagnostic.summary == "Cooling and electrical faults are likely."
    assert diagnostic.narrative_source == "llm"
    assert diagnostic.llm_attempts == 1
    assert diagnostic.llm_error is None


@pytest.mark.asyncio
async def test_llm_failure_falls_back_without_losing_findings() -> None:
    client = _FailingClient()

    diagnostic = await DiagnosticAgent(client, max_llm_retries=1).analyze(
        _record(Scenario.CRITICAL).telemetry
    )

    assert client.calls == 2
    assert diagnostic.narrative_source == "fallback"
    assert diagnostic.llm_attempts == 2
    assert "ConnectionError" in (diagnostic.llm_error or "")
    assert "3 abnormal reading(s) and 2 trouble code(s)" in diagnostic.summary
    assert len(diagnostic.findings) == 3
    assert len(diagnostic.dtc_interpretations) == 2


@pytest.mark.asyncio
async def test_llm_transient_failure_is_retried() -> None:
    client = _FlakyClient()

    diagnostic = await DiagnosticAgent(client, max_llm_retries=1).analyze(
        _record(Scenario.NORMAL).telemetry
    )

    assert client.calls == 2
    assert diagnostic.narrative_source == "llm"
    assert diagnostic.llm_attempts == 2
    assert diagnostic.summary == "Recovered narrative."


# --------------------------------------------------------------------------- #
# Risk Assessment Agent
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scenario", "level", "score", "override"),
    [
        (Scenario.NORMAL, RiskLevel.LOW, 0, False),
        (Scenario.WARNING, RiskLevel.MEDIUM, 5, False),
        (Scenario.CRITICAL, RiskLevel.CRITICAL, 26, True),
        (Scenario.SENSOR_FAILURE, RiskLevel.HIGH, 8, False),
    ],
)
async def test_risk_levels_for_each_scenario(
    scenario: Scenario, level: RiskLevel, score: int, override: bool
) -> None:
    telemetry = _record(scenario).telemetry
    diagnostic = await DiagnosticAgent(MockNarrativeClient()).analyze(telemetry)

    risk = RiskAssessmentAgent().assess(telemetry, diagnostic)

    assert risk.level is level
    assert risk.score == score
    assert risk.hard_override is override
    assert risk.threshold_version == "1.0"


@pytest.mark.asyncio
async def test_risk_reasons_explain_the_score() -> None:
    telemetry = _record(Scenario.CRITICAL).telemetry
    diagnostic = await DiagnosticAgent(MockNarrativeClient()).analyze(telemetry)

    risk = RiskAssessmentAgent().assess(telemetry, diagnostic)

    codes = [reason.code for reason in risk.reasons]
    assert "SAFETY_OVERRIDE" in codes
    assert "DTC_P0217" in codes
    assert sum(reason.score for reason in risk.reasons) == risk.score


@pytest.mark.asyncio
async def test_clean_frame_gets_explicit_no_anomalies_reason() -> None:
    telemetry = _record(Scenario.NORMAL).telemetry
    diagnostic = await DiagnosticAgent(MockNarrativeClient()).analyze(telemetry)

    risk = RiskAssessmentAgent().assess(telemetry, diagnostic)

    assert [reason.code for reason in risk.reasons] == ["NO_ANOMALIES"]


@pytest.mark.asyncio
async def test_overheated_engine_forces_critical_even_with_low_score_inputs() -> None:
    record = _record(Scenario.NORMAL)
    telemetry = record.telemetry.model_copy(
        update={"sensors": record.telemetry.sensors.model_copy(
            update={"engine_temperature_c": 118.5}
        )}
    )
    diagnostic = await DiagnosticAgent(MockNarrativeClient()).analyze(telemetry)

    risk = RiskAssessmentAgent().assess(telemetry, diagnostic)

    assert risk.hard_override is True
    assert risk.level is RiskLevel.CRITICAL
    assert "SAFETY_OVERRIDE" in [reason.code for reason in risk.reasons]


# --------------------------------------------------------------------------- #
# Maintenance Agent
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_clean_frame_gets_routine_monitoring_only() -> None:
    telemetry = _record(Scenario.NORMAL).telemetry
    diagnostic = await DiagnosticAgent(MockNarrativeClient()).analyze(telemetry)
    risk = RiskAssessmentAgent().assess(telemetry, diagnostic)

    plan = MaintenanceAgent().recommend(diagnostic, risk)

    assert plan.priority is MaintenancePriority.ROUTINE
    assert [action.title for action in plan.actions] == ["Continue routine monitoring"]
    assert plan.repair_performed is False
    assert "No inspection or repair has been performed" in plan.notes


@pytest.mark.asyncio
async def test_critical_frame_gets_immediate_targeted_actions() -> None:
    telemetry = _record(Scenario.CRITICAL).telemetry
    diagnostic = await DiagnosticAgent(MockNarrativeClient()).analyze(telemetry)
    risk = RiskAssessmentAgent().assess(telemetry, diagnostic)

    plan = MaintenanceAgent().recommend(diagnostic, risk)

    assert plan.priority is MaintenancePriority.IMMEDIATE
    titles = " ".join(action.title for action in plan.actions)
    assert "cooling system" in titles
    assert "battery" in titles.lower()
    assert "vibration" in titles.lower()
    assert "over-temperature" in titles.lower()
    assert "cylinder 1 misfire" in titles.lower()
    assert all(action.priority is MaintenancePriority.IMMEDIATE for action in plan.actions)
    assert all(action.rationale for action in plan.actions)


@pytest.mark.asyncio
async def test_sensor_failure_gets_circuit_inspection_and_communication_action() -> None:
    telemetry = _record(Scenario.SENSOR_FAILURE).telemetry
    diagnostic = await DiagnosticAgent(MockNarrativeClient()).analyze(telemetry)
    risk = RiskAssessmentAgent().assess(telemetry, diagnostic)

    plan = MaintenanceAgent().recommend(diagnostic, risk)

    titles = [action.title for action in plan.actions]
    assert any("sensor circuit" in title for title in titles)
    assert any("ECM/PCM" in title for title in titles)
    assert plan.priority is MaintenancePriority.URGENT


@pytest.mark.asyncio
async def test_unknown_dtc_requests_a_full_scan() -> None:
    record = _record(Scenario.NORMAL)
    telemetry = record.telemetry.model_copy(update={"error_codes": ["P0999"]})
    diagnostic = await DiagnosticAgent(MockNarrativeClient()).analyze(telemetry)
    risk = RiskAssessmentAgent().assess(telemetry, diagnostic)

    plan = MaintenanceAgent().recommend(diagnostic, risk)

    assert any("full diagnostic scan for P0999" in action.title for action in plan.actions)


@pytest.mark.asyncio
async def test_duplicate_actions_are_merged() -> None:
    telemetry = _record(Scenario.CRITICAL).telemetry
    diagnostic = await DiagnosticAgent(MockNarrativeClient()).analyze(telemetry)
    risk = RiskAssessmentAgent().assess(telemetry, diagnostic)
    duplicated = diagnostic.model_copy(
        update={
            "dtc_interpretations": [
                *diagnostic.dtc_interpretations,
                diagnostic.dtc_interpretations[0],
            ]
        }
    )

    plan = MaintenanceAgent().recommend(duplicated, risk)

    overheat_actions = [
        action
        for action in plan.actions
        if action.title.startswith("Investigate the over-temperature")
    ]
    assert len(overheat_actions) == 1
    assert overheat_actions[0].related_findings == ["P0217"]


# --------------------------------------------------------------------------- #
# Reporting Agent
# --------------------------------------------------------------------------- #


async def _artifacts(scenario: Scenario):
    record = _record(scenario)
    diagnostic = await DiagnosticAgent(MockNarrativeClient()).analyze(record.telemetry)
    risk = RiskAssessmentAgent().assess(record.telemetry, diagnostic)
    maintenance = MaintenanceAgent().recommend(diagnostic, risk)
    return record, diagnostic, risk, maintenance


@pytest.mark.asyncio
async def test_report_records_deterministic_mode_and_metadata() -> None:
    record, diagnostic, risk, maintenance = await _artifacts(Scenario.WARNING)

    report = ReportingAgent().build(
        telemetry_record=record,
        workflow_id="WF-20261030-REPORTTEST",
        diagnostic=diagnostic,
        risk=risk,
        maintenance=maintenance,
        executions=[],
        warnings=[],
    )

    assert report.status is ReportStatus.COMPLETED
    assert report.analysis_mode is AnalysisMode.DETERMINISTIC
    assert report.diagnostic_id.startswith("DIAG-")
    assert report.telemetry_id == record.telemetry_id
    assert report.correlation_id == record.correlation_id
    assert report.vehicle_id == record.telemetry.vehicle_id
    assert report.disclaimer == DISCLAIMER
    assert report.maintenance.repair_performed is False


@pytest.mark.asyncio
async def test_report_maps_llm_and_fallback_modes() -> None:
    record, diagnostic, risk, maintenance = await _artifacts(Scenario.NORMAL)
    llm_diagnostic = diagnostic.model_copy(
        update={"narrative_source": "llm", "summary": "LLM summary."}
    )
    fallback_diagnostic = diagnostic.model_copy(
        update={"narrative_source": "fallback", "llm_error": "TimeoutError: timeout"}
    )
    warning = ReportWarning(
        code="LLM_NARRATIVE_UNAVAILABLE", message="Provider unavailable; fallback used."
    )

    llm_report = ReportingAgent().build(
        telemetry_record=record,
        workflow_id="WF-LLM",
        diagnostic=llm_diagnostic,
        risk=risk,
        maintenance=maintenance,
        executions=[],
        warnings=[],
    )
    degraded_report = ReportingAgent().build(
        telemetry_record=record,
        workflow_id="WF-FALLBACK",
        diagnostic=fallback_diagnostic,
        risk=risk,
        maintenance=maintenance,
        executions=[],
        warnings=[warning],
    )

    assert llm_report.analysis_mode is AnalysisMode.LLM_ASSISTED
    assert llm_report.status is ReportStatus.COMPLETED
    assert degraded_report.analysis_mode is AnalysisMode.DEGRADED_DETERMINISTIC
    assert degraded_report.status is ReportStatus.COMPLETED_DEGRADED
    assert degraded_report.warnings == [warning]
