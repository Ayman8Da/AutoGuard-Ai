"""API tests for diagnosis-triggering ingestion and report endpoints."""

from __future__ import annotations

import pytest
from app.core.correlation import CORRELATION_HEADER
from app.utils.time import utc_now
from fastapi.testclient import TestClient
from simulator.scenarios import Scenario
from simulator.vehicle_simulator import build_scenario_telemetry

TELEMETRY_URL = "/api/v1/vehicles/telemetry"
DIAGNOSTICS_URL = "/api/v1/diagnostics"


def _payload(scenario: Scenario = Scenario.NORMAL, vehicle_id: str = "VH-001") -> dict:
    return build_scenario_telemetry(scenario, vehicle_id, utc_now()).model_dump(mode="json")


def test_empty_report_list(client: TestClient) -> None:
    response = client.get(DIAGNOSTICS_URL)

    assert response.status_code == 200
    assert response.json() == []


def test_ingestion_returns_and_persists_a_report(client: TestClient) -> None:
    response = client.post(TELEMETRY_URL, json=_payload(Scenario.WARNING, "VH-002"))

    assert response.status_code == 200
    report = response.json()
    diagnostic_id = report["diagnostic_id"]

    listed = client.get(DIAGNOSTICS_URL)
    assert listed.status_code == 200
    summaries = listed.json()
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary["diagnostic_id"] == diagnostic_id
    assert summary["vehicle_id"] == "VH-002"
    assert summary["risk_level"] == "medium"
    assert summary["status"] == "completed"
    assert summary["analysis_mode"] == "deterministic"
    assert summary["correlation_id"] == report["correlation_id"]

    detail = client.get(f"{DIAGNOSTICS_URL}/{diagnostic_id}")
    assert detail.status_code == 200
    assert detail.json() == report


@pytest.mark.parametrize(
    ("scenario", "risk_level", "hard_override"),
    [
        (Scenario.NORMAL, "low", False),
        (Scenario.WARNING, "medium", False),
        (Scenario.CRITICAL, "critical", True),
        (Scenario.SENSOR_FAILURE, "high", False),
    ],
)
def test_reports_carry_deterministic_risk_levels(
    client: TestClient, scenario: Scenario, risk_level: str, hard_override: bool
) -> None:
    report = client.post(TELEMETRY_URL, json=_payload(scenario)).json()

    assert report["risk"]["level"] == risk_level
    assert report["risk"]["hard_override"] is hard_override
    assert report["risk"]["reasons"]
    assert report["maintenance"]["repair_performed"] is False


def test_critical_report_lists_all_agent_executions(client: TestClient) -> None:
    report = client.post(TELEMETRY_URL, json=_payload(Scenario.CRITICAL)).json()

    executions = report["agent_executions"]
    assert [item["agent_name"] for item in executions] == [
        "OrchestratorAgent",
        "DiagnosticAgent",
        "RiskAssessmentAgent",
        "MaintenanceAgent",
        "ReportingAgent",
    ]
    assert all(item["status"] == "success" for item in executions)
    assert all(item["attempt"] == 1 for item in executions)
    assert all(item["correlation_id"] == report["correlation_id"] for item in executions)
    assert all(item["workflow_id"] == report["workflow_id"] for item in executions)


def test_correlation_id_is_propagated_through_the_workflow(client: TestClient) -> None:
    correlation_id = "CORR-20261030-APIWORKFLOW1"

    report = client.post(
        TELEMETRY_URL,
        json=_payload(Scenario.NORMAL),
        headers={CORRELATION_HEADER: correlation_id},
    ).json()

    assert report["correlation_id"] == correlation_id
    assert all(item["correlation_id"] == correlation_id for item in report["agent_executions"])
    assert client.get(DIAGNOSTICS_URL).json()[0]["correlation_id"] == correlation_id


def test_unknown_vehicle_does_not_create_a_report(client: TestClient) -> None:
    payload = _payload(Scenario.NORMAL)
    payload["vehicle_id"] = "VH-999"

    response = client.post(TELEMETRY_URL, json=payload)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "VEHICLE_NOT_FOUND"
    assert client.get(DIAGNOSTICS_URL).json() == []


def test_unknown_diagnostic_returns_404(client: TestClient) -> None:
    response = client.get(f"{DIAGNOSTICS_URL}/DIAG-20261030-UNKNOWN")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "DIAGNOSTIC_NOT_FOUND"
    assert error["details"] == {"diagnostic_id": "DIAG-20261030-UNKNOWN"}
    assert error["correlation_id"] == response.headers[CORRELATION_HEADER]


def test_report_list_is_newest_first_and_honours_limit(client: TestClient) -> None:
    first = client.post(TELEMETRY_URL, json=_payload(Scenario.NORMAL, "VH-001")).json()
    second = client.post(TELEMETRY_URL, json=_payload(Scenario.WARNING, "VH-002")).json()
    third = client.post(TELEMETRY_URL, json=_payload(Scenario.CRITICAL, "VH-003")).json()

    newest = client.get(f"{DIAGNOSTICS_URL}?limit=2").json()

    assert [item["diagnostic_id"] for item in newest] == [
        third["diagnostic_id"],
        second["diagnostic_id"],
    ]
    assert first["diagnostic_id"] not in {item["diagnostic_id"] for item in newest}


@pytest.mark.parametrize("limit", [0, 201, -5])
def test_invalid_report_limit_is_rejected(client: TestClient, limit: int) -> None:
    response = client.get(f"{DIAGNOSTICS_URL}?limit={limit}")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_diagnostics_endpoints_are_documented(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert "/api/v1/diagnostics" in schema["paths"]
    assert "/api/v1/diagnostics/{diagnostic_id}" in schema["paths"]
    post_schema = schema["paths"]["/api/v1/vehicles/telemetry"]["post"]
    assert post_schema["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DiagnosticReport"
    }
