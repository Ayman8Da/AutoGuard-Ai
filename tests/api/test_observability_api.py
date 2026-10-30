"""API tests for monitoring, incidents and degraded/failed workflows."""

from __future__ import annotations

import pytest
from app.agents.diagnostic import DiagnosticAgent
from app.agents.llm import NarrativeRequest
from app.core.correlation import CORRELATION_HEADER
from app.utils.time import utc_now
from fastapi.testclient import TestClient
from simulator.scenarios import Scenario
from simulator.vehicle_simulator import build_scenario_telemetry

TELEMETRY_URL = "/api/v1/vehicles/telemetry"
MONITORING_URL = "/api/v1/monitoring"
INCIDENTS_URL = "/api/v1/incidents"


def _payload(scenario: Scenario = Scenario.NORMAL, vehicle_id: str = "VH-001") -> dict:
    return build_scenario_telemetry(scenario, vehicle_id, utc_now()).model_dump(mode="json")


class _FailingNarrativeClient:
    provider_name = "failing"

    async def summarise(self, request: NarrativeRequest) -> str:
        raise ConnectionError("provider offline")


class _BrokenDiagnosticAgent:
    name = "DiagnosticAgent"

    async def analyze(self, telemetry):  # noqa: ANN001 - protocol double
        raise RuntimeError("deterministic rule engine crashed")


# --------------------------------------------------------------------------- #
# Monitoring
# --------------------------------------------------------------------------- #


def test_empty_monitoring_snapshot(client: TestClient) -> None:
    response = client.get(MONITORING_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["llm_provider"] == "mock"
    assert body["uptime_seconds"] >= 0
    assert body["workflows_started"] == 0
    assert body["workflows_completed"] == 0
    assert body["workflows_degraded"] == 0
    assert body["workflows_failed"] == 0
    assert body["agent_executions_total"] == 0
    assert body["agents"] == []
    assert body["diagnostics_stored"] == 0
    assert body["incidents_total"] == 0
    assert body["incidents_active"] == 0


def test_monitoring_aggregates_a_successful_workflow(client: TestClient) -> None:
    report = client.post(TELEMETRY_URL, json=_payload(Scenario.NORMAL)).json()

    body = client.get(MONITORING_URL).json()

    assert body["workflows_started"] == 1
    assert body["workflows_completed"] == 1
    assert body["workflows_degraded"] == 0
    assert body["workflows_failed"] == 0
    assert body["workflow_success_rate_percent"] == 100.0
    assert body["avg_workflow_duration_ms"] > 0
    assert body["agent_executions_total"] == len(report["agent_executions"]) == 5
    assert body["agent_failures_total"] == 0
    assert body["agent_success_rate_percent"] == 100.0
    assert [item["agent_name"] for item in body["agents"]] == [
        "DiagnosticAgent",
        "MaintenanceAgent",
        "OrchestratorAgent",
        "ReportingAgent",
        "RiskAssessmentAgent",
    ]
    assert body["diagnostics_stored"] == 1
    assert body["incidents_total"] == 0


def test_monitoring_counts_critical_incidents(client: TestClient) -> None:
    client.post(TELEMETRY_URL, json=_payload(Scenario.CRITICAL))

    body = client.get(MONITORING_URL).json()

    assert body["incidents_total"] == 1
    assert body["incidents_active"] == 1
    assert body["workflows_completed"] == 1


def test_monitoring_endpoint_is_documented(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert "/api/v1/monitoring" in schema["paths"]


# --------------------------------------------------------------------------- #
# Incidents
# --------------------------------------------------------------------------- #


def test_empty_incident_list(client: TestClient) -> None:
    response = client.get(INCIDENTS_URL)

    assert response.status_code == 200
    assert response.json() == []


def test_critical_ingestion_creates_a_queryable_incident(client: TestClient) -> None:
    report = client.post(
        TELEMETRY_URL,
        json=_payload(Scenario.CRITICAL, "VH-003"),
        headers={CORRELATION_HEADER: "CORR-20261030-APIINCIDENT"},
    ).json()

    incidents = client.get(INCIDENTS_URL).json()

    assert len(incidents) == 1
    incident = incidents[0]
    assert incident["incident_id"].startswith("INC-")
    assert incident["code"] == "CRITICAL_VEHICLE_RISK"
    assert incident["severity"] == "critical"
    assert incident["status"] == "open"
    assert incident["runbook_id"] == "high_risk_vehicle"
    assert incident["vehicle_id"] == "VH-003"
    assert incident["diagnostic_id"] == report["diagnostic_id"]
    assert incident["workflow_id"] == report["workflow_id"]
    assert incident["correlation_id"] == "CORR-20261030-APIINCIDENT"
    assert incident["metadata"]["risk_score"] == report["risk"]["score"]


def test_incident_filters_and_limit_are_applied(client: TestClient) -> None:
    client.post(TELEMETRY_URL, json=_payload(Scenario.CRITICAL, "VH-003"))
    client.post(TELEMETRY_URL, json=_payload(Scenario.NORMAL, "VH-001"))

    assert len(client.get(INCIDENTS_URL).json()) == 1
    assert client.get(f"{INCIDENTS_URL}?limit=1").json()[0]["vehicle_id"] == "VH-003"
    assert (
        len(client.get(f"{INCIDENTS_URL}?severity=critical&status=open").json()) == 1
    )
    assert client.get(f"{INCIDENTS_URL}?severity=medium").json() == []
    assert client.get(f"{INCIDENTS_URL}?status=resolved").json() == []
    assert client.get(f"{INCIDENTS_URL}?vehicle_id=VH-001").json() == []
    assert len(client.get(f"{INCIDENTS_URL}?vehicle_id=VH-003").json()) == 1


@pytest.mark.parametrize("query", ["limit=0", "limit=201", "severity=bogus", "status=bogus"])
def test_invalid_incident_query_is_rejected(client: TestClient, query: str) -> None:
    response = client.get(f"{INCIDENTS_URL}?{query}")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_incident_endpoint_is_documented(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert "/api/v1/incidents" in schema["paths"]


# --------------------------------------------------------------------------- #
# Degraded and failed workflows
# --------------------------------------------------------------------------- #


def test_narrative_outage_creates_degraded_incident(
    app, client: TestClient  # noqa: ANN001 - pytest fixture
) -> None:
    app.state.diagnostic_workflow._diagnostic_agent = DiagnosticAgent(
        _FailingNarrativeClient(), max_llm_retries=1
    )

    response = client.post(TELEMETRY_URL, json=_payload(Scenario.CRITICAL, "VH-002"))

    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "completed_degraded"
    assert report["analysis_mode"] == "degraded_deterministic"
    assert report["risk"]["level"] == "critical"

    incidents = client.get(INCIDENTS_URL).json()
    assert {item["code"] for item in incidents} == {
        "CRITICAL_VEHICLE_RISK",
        "LLM_PROVIDER_FAILURE",
    }
    narrative = next(item for item in incidents if item["code"] == "LLM_PROVIDER_FAILURE")
    assert narrative["severity"] == "medium"
    assert narrative["runbook_id"] == "llm_provider_failure"

    monitoring = client.get(MONITORING_URL).json()
    assert monitoring["workflows_completed"] == 0
    assert monitoring["workflows_degraded"] == 1
    assert monitoring["incidents_total"] == 2


def test_agent_failure_creates_incident_and_failed_counter(
    app, client: TestClient  # noqa: ANN001 - pytest fixture
) -> None:
    app.state.diagnostic_workflow._diagnostic_agent = _BrokenDiagnosticAgent()

    response = client.post(
        TELEMETRY_URL,
        json=_payload(Scenario.NORMAL, "VH-001"),
        headers={CORRELATION_HEADER: "CORR-20261030-APIFAILURE"},
    )

    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "AGENT_EXECUTION_FAILED"
    assert error["details"]["agent_name"] == "DiagnosticAgent"
    assert error["details"]["attempts"] == 2
    assert error["correlation_id"] == "CORR-20261030-APIFAILURE"

    incidents = client.get(INCIDENTS_URL).json()
    assert len(incidents) == 1
    incident = incidents[0]
    assert incident["code"] == "AGENT_EXECUTION_FAILED"
    assert incident["runbook_id"] == "agent_failure"
    assert incident["correlation_id"] == "CORR-20261030-APIFAILURE"
    assert incident["workflow_id"] == error["details"]["workflow_id"]

    monitoring = client.get(MONITORING_URL).json()
    assert monitoring["workflows_failed"] == 1
    assert monitoring["workflows_completed"] == 0
    assert monitoring["workflow_success_rate_percent"] == 0.0
    assert monitoring["agent_failures_total"] == 2
    assert monitoring["diagnostics_stored"] == 0
    # Telemetry is stored even when diagnosis aborts.
    vehicle = client.get("/api/v1/vehicles/VH-001").json()
    assert vehicle["latest_telemetry"] is not None
    assert vehicle["latest_telemetry"]["correlation_id"] == "CORR-20261030-APIFAILURE"
