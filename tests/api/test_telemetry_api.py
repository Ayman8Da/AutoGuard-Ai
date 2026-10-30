"""API tests for POST /api/v1/vehicles/telemetry."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from app.core.correlation import CORRELATION_HEADER
from app.models.telemetry import VehicleTelemetry
from app.utils.time import utc_now
from fastapi.testclient import TestClient
from simulator.scenarios import Scenario
from simulator.vehicle_simulator import build_scenario_telemetry

TELEMETRY_URL = "/api/v1/vehicles/telemetry"
_TELEMETRY_ID_PATTERN = re.compile(r"^TEL-\d{8}-[0-9A-F]{10}$")


def _payload(
    scenario: Scenario = Scenario.NORMAL,
    vehicle_id: str = "VH-001",
    **overrides: object,
) -> dict[str, object]:
    payload: dict[str, object] = build_scenario_telemetry(
        scenario, "VH-001", utc_now()
    ).model_dump(mode="json")
    # Applied after generation so unknown / malformed IDs can be tested end-to-end.
    payload["vehicle_id"] = vehicle_id
    payload.update(overrides)
    return payload


def test_valid_telemetry_is_stored(client: TestClient) -> None:
    payload = _payload()

    response = client.post(TELEMETRY_URL, json=payload)

    assert response.status_code == 201
    body = response.json()
    assert _TELEMETRY_ID_PATTERN.fullmatch(body["telemetry_id"])
    assert body["correlation_id"] == response.headers[CORRELATION_HEADER]
    assert body["telemetry"]["vehicle_id"] == "VH-001"
    assert body["telemetry"]["sensors"]["engine_temperature_c"] == 89.5
    assert datetime.fromisoformat(body["received_at"]).tzinfo is not None
    VehicleTelemetry.model_validate(body["telemetry"])


def test_warning_scenario_keeps_trouble_code(client: TestClient) -> None:
    response = client.post(TELEMETRY_URL, json=_payload(Scenario.WARNING))

    assert response.status_code == 201
    assert response.json()["telemetry"]["error_codes"] == ["P0128"]


def test_critical_scenario_keeps_all_trouble_codes(client: TestClient) -> None:
    response = client.post(TELEMETRY_URL, json=_payload(Scenario.CRITICAL))

    assert response.status_code == 201
    assert response.json()["telemetry"]["error_codes"] == ["P0217", "P0301"]


def test_sensor_failure_payload_is_accepted(client: TestClient) -> None:
    response = client.post(TELEMETRY_URL, json=_payload(Scenario.SENSOR_FAILURE))

    assert response.status_code == 201
    sensors = response.json()["telemetry"]["sensors"]
    assert sensors["engine_temperature_c"] is None
    assert sensors["engine_vibration_mm_s"] is None
    assert sensors["battery_voltage_v"] == 13.1


def test_client_correlation_id_is_propagated(client: TestClient) -> None:
    correlation_id = "CORR-20261030-INGEST000001"

    response = client.post(
        TELEMETRY_URL,
        json=_payload(),
        headers={CORRELATION_HEADER: correlation_id},
    )

    assert response.headers[CORRELATION_HEADER] == correlation_id
    assert response.json()["correlation_id"] == correlation_id


def test_unknown_vehicle_returns_404(client: TestClient) -> None:
    response = client.post(TELEMETRY_URL, json=_payload(vehicle_id="VH-999"))

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "VEHICLE_NOT_FOUND"
    assert error["details"] == {"vehicle_id": "VH-999"}


def test_missing_vehicle_id_is_rejected(client: TestClient) -> None:
    payload = _payload()
    payload.pop("vehicle_id")

    response = client.post(TELEMETRY_URL, json=payload)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"][0]["loc"] == ["body", "vehicle_id"]
    assert error["correlation_id"] == response.headers[CORRELATION_HEADER]


def test_malformed_vehicle_id_is_rejected(client: TestClient) -> None:
    response = client.post(TELEMETRY_URL, json=_payload(vehicle_id="CAR-1"))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_implausible_sensor_reading_is_rejected(client: TestClient) -> None:
    payload = _payload()
    payload["sensors"] = {"engine_temperature_c": 400.0}

    response = client.post(TELEMETRY_URL, json=payload)

    assert response.status_code == 422
    details = response.json()["error"]["details"]
    assert any(item["loc"] == ["body", "sensors", "engine_temperature_c"] for item in details)


def test_malformed_trouble_code_is_rejected(client: TestClient) -> None:
    response = client.post(TELEMETRY_URL, json=_payload(error_codes=["NOT-A-CODE"]))

    assert response.status_code == 422
    assert "invalid diagnostic trouble code" in str(response.json()["error"]["details"])


def test_naive_timestamp_is_rejected(client: TestClient) -> None:
    response = client.post(
        TELEMETRY_URL,
        json=_payload(timestamp="2026-10-30T10:00:00"),
    )

    assert response.status_code == 422
    assert "timezone" in str(response.json()["error"]["details"])


def test_future_timestamp_is_rejected(client: TestClient) -> None:
    future = (utc_now() + timedelta(minutes=15)).isoformat()

    response = client.post(TELEMETRY_URL, json=_payload(timestamp=future))

    assert response.status_code == 422
    assert "future" in str(response.json()["error"]["details"])


def test_unknown_payload_field_is_rejected(client: TestClient) -> None:
    response = client.post(TELEMETRY_URL, json=_payload(engine_rpm=2500))

    assert response.status_code == 422
    assert "Extra inputs are not permitted" in str(response.json()["error"]["details"])


def test_unknown_operating_status_is_rejected(client: TestClient) -> None:
    response = client.post(TELEMETRY_URL, json=_payload(status="flying"))

    assert response.status_code == 422
