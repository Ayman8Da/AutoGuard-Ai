"""Failure-path acceptance tests.

These tests assert the properties that matter when things go wrong:

* invalid input is rejected before any agent runs;
* an LLM outage degrades but never breaks the diagnosis;
* an agent outage fails safely, stores no report and raises an incident;
* observability failures cannot break a diagnosis;
* correlation IDs survive every path.
"""

from __future__ import annotations

import pytest
from app.agents.diagnostic import DiagnosticAgent
from app.agents.llm import MockNarrativeClient, NarrativeRequest
from app.agents.maintenance import MaintenanceAgent
from app.agents.reporting import ReportingAgent
from app.agents.risk import RiskAssessmentAgent
from app.core.correlation import CORRELATION_HEADER
from app.models.telemetry import TelemetryRecord
from app.orchestration.workflow import DiagnosticWorkflow
from app.utils.ids import generate_id
from app.utils.time import utc_now
from fastapi.testclient import TestClient
from simulator.scenarios import Scenario
from simulator.vehicle_simulator import build_scenario_telemetry

TELEMETRY_URL = "/api/v1/vehicles/telemetry"
DIAGNOSTICS_URL = "/api/v1/diagnostics"
INCIDENTS_URL = "/api/v1/incidents"
MONITORING_URL = "/api/v1/monitoring"


def _payload(scenario: Scenario = Scenario.NORMAL, vehicle_id: str = "VH-001") -> dict:
    payload = build_scenario_telemetry(scenario, "VH-001", utc_now()).model_dump(mode="json")
    payload["vehicle_id"] = vehicle_id
    return payload


class _FailingNarrativeClient:
    provider_name = "failing"

    async def summarise(self, request: NarrativeRequest) -> str:
        raise TimeoutError("provider timed out")


class _BrokenDiagnosticAgent:
    name = "DiagnosticAgent"

    async def analyze(self, telemetry):  # noqa: ANN001 - protocol double
        raise RuntimeError("rule engine crashed")


class _BrokenMonitoring:
    """Observer that fails on every call — must never reach the caller."""

    def record_workflow_started(self) -> None:
        raise RuntimeError("monitoring start hook failed")

    def record_execution(self, execution) -> None:  # noqa: ANN001 - protocol double
        raise RuntimeError("monitoring observer failed")

    def record_workflow_completed(self, report, duration_ms: float) -> None:  # noqa: ANN001
        raise RuntimeError("monitoring completion hook failed")

    def record_workflow_failed(self, error_type: str, duration_ms: float) -> None:
        raise RuntimeError("monitoring failure hook failed")


def test_invalid_telemetry_is_rejected_before_any_side_effect(client: TestClient) -> None:
    payload = _payload()
    payload["sensors"]["engine_temperature_c"] = 900.0

    response = client.post(
        TELEMETRY_URL,
        json=payload,
        headers={CORRELATION_HEADER: "CORR-20261030-BOUNDARY01"},
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["correlation_id"] == "CORR-20261030-BOUNDARY01"
    assert client.get(DIAGNOSTICS_URL).json() == []
    assert client.get(INCIDENTS_URL).json() == []
    assert client.get(MONITORING_URL).json()["workflows_started"] == 0


def test_unknown_vehicle_creates_no_diagnosis_or_incident(client: TestClient) -> None:
    response = client.post(TELEMETRY_URL, json=_payload(vehicle_id="VH-999"))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "VEHICLE_NOT_FOUND"
    assert client.get(DIAGNOSTICS_URL).json() == []
    assert client.get(INCIDENTS_URL).json() == []
    assert client.get(MONITORING_URL).json()["workflows_started"] == 0


def test_provider_outage_degrades_instead_of_failing(
    app, client: TestClient  # noqa: ANN001 - pytest fixture
) -> None:
    app.state.diagnostic_workflow._diagnostic_agent = DiagnosticAgent(
        _FailingNarrativeClient(), max_llm_retries=1
    )

    response = client.post(
        TELEMETRY_URL,
        json=_payload(Scenario.CRITICAL),
        headers={CORRELATION_HEADER: "CORR-20261030-DEGRADED1"},
    )

    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "completed_degraded"
    assert report["analysis_mode"] == "degraded_deterministic"
    assert report["warnings"][0]["code"] == "LLM_NARRATIVE_UNAVAILABLE"
    # Safety output is unaffected by the narrative outage.
    assert report["risk"]["level"] == "critical"
    assert report["risk"]["hard_override"] is True
    assert report["maintenance"]["repair_performed"] is False
    assert client.get(f"{DIAGNOSTICS_URL}/{report['diagnostic_id']}").status_code == 200


def test_agent_outage_fails_safely_and_leaves_an_audit_trail(
    app, client: TestClient  # noqa: ANN001 - pytest fixture
) -> None:
    app.state.diagnostic_workflow._diagnostic_agent = _BrokenDiagnosticAgent()

    response = client.post(
        TELEMETRY_URL,
        json=_payload(Scenario.NORMAL),
        headers={CORRELATION_HEADER: "CORR-20261030-FAILPATH1"},
    )

    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "AGENT_EXECUTION_FAILED"
    assert error["correlation_id"] == "CORR-20261030-FAILPATH1"
    assert error["details"]["attempts"] == 2
    # No report is fabricated, but telemetry and an incident remain.
    assert client.get(DIAGNOSTICS_URL).json() == []
    incidents = client.get(INCIDENTS_URL).json()
    assert len(incidents) == 1
    assert incidents[0]["code"] == "AGENT_EXECUTION_FAILED"
    assert incidents[0]["correlation_id"] == "CORR-20261030-FAILPATH1"
    assert client.get("/api/v1/vehicles/VH-001").json()["latest_telemetry"] is not None
    monitoring = client.get(MONITORING_URL).json()
    assert monitoring["workflows_failed"] == 1
    assert monitoring["diagnostics_stored"] == 0


@pytest.mark.asyncio
async def test_broken_monitoring_never_breaks_the_workflow() -> None:
    timestamp = utc_now()
    record = TelemetryRecord(
        telemetry_id=generate_id("TEL", timestamp),
        correlation_id="CORR-20261030-MONBROKEN1",
        received_at=timestamp,
        telemetry=build_scenario_telemetry(Scenario.WARNING, "VH-002", timestamp),
    )
    workflow = DiagnosticWorkflow(
        diagnostic_agent=DiagnosticAgent(MockNarrativeClient()),
        risk_agent=RiskAssessmentAgent(),
        maintenance_agent=MaintenanceAgent(),
        reporting_agent=ReportingAgent(),
        monitoring=_BrokenMonitoring(),
    )

    report = await workflow.run(record)

    assert report.risk.level.value == "medium"
    assert len(report.agent_executions) == 5
    assert all(item.status.value == "success" for item in report.agent_executions)
    assert report.correlation_id == "CORR-20261030-MONBROKEN1"


def test_every_failure_response_carries_a_correlation_id(client: TestClient) -> None:
    responses = [
        client.post(TELEMETRY_URL, json={"vehicle_id": "VH-001"}),
        client.post(TELEMETRY_URL, json=_payload(vehicle_id="VH-999")),
        client.get(f"{DIAGNOSTICS_URL}/DIAG-20261030-MISSING"),
        client.get(f"{INCIDENTS_URL}?limit=0"),
    ]

    for response in responses:
        assert response.status_code in {404, 422}
        assert response.json()["error"]["correlation_id"] == response.headers[CORRELATION_HEADER]
