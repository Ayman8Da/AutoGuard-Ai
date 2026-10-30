"""API tests for the simulated fleet read endpoints."""

from __future__ import annotations

from datetime import datetime

from app.utils.time import utc_now
from fastapi.testclient import TestClient
from simulator.scenarios import Scenario
from simulator.vehicle_simulator import build_scenario_telemetry

VEHICLES_URL = "/api/v1/vehicles"


def _payload(scenario: Scenario, vehicle_id: str = "VH-001") -> dict[str, object]:
    return build_scenario_telemetry(scenario, vehicle_id, utc_now()).model_dump(mode="json")


def test_fleet_lists_all_simulated_vehicles(client: TestClient) -> None:
    response = client.get(VEHICLES_URL)

    assert response.status_code == 200
    vehicles = response.json()
    assert len(vehicles) == 5
    assert [vehicle["vehicle_id"] for vehicle in vehicles] == [
        "VH-001",
        "VH-002",
        "VH-003",
        "VH-004",
        "VH-005",
    ]
    assert all(vehicle["last_seen"] is None for vehicle in vehicles)
    assert all(vehicle["operating_status"] is None for vehicle in vehicles)


def test_fleet_reflects_latest_ingested_telemetry(client: TestClient) -> None:
    payload = _payload(Scenario.CRITICAL, "VH-002")
    client.post("/api/v1/vehicles/telemetry", json=payload)

    vehicles = client.get(VEHICLES_URL).json()
    updated = next(vehicle for vehicle in vehicles if vehicle["vehicle_id"] == "VH-002")

    assert updated["operating_status"] == "driving"
    assert datetime.fromisoformat(updated["last_seen"]) == datetime.fromisoformat(
        payload["timestamp"]
    )
    # Other vehicles are untouched.
    assert next(v for v in vehicles if v["vehicle_id"] == "VH-001")["last_seen"] is None


def test_vehicle_detail_without_telemetry(client: TestClient) -> None:
    response = client.get(f"{VEHICLES_URL}/VH-003")

    assert response.status_code == 200
    body = response.json()
    assert body["make"] == "BMW"
    assert body["model"] == "320i"
    assert body["latest_telemetry"] is None


def test_vehicle_detail_returns_latest_telemetry(client: TestClient) -> None:
    payload = _payload(Scenario.WARNING, "VH-003")
    ingested = client.post("/api/v1/vehicles/telemetry", json=payload).json()

    response = client.get(f"{VEHICLES_URL}/VH-003")

    assert response.status_code == 200
    body = response.json()
    assert body["operating_status"] == "driving"
    assert body["latest_telemetry"]["telemetry_id"] == ingested["telemetry_id"]
    assert body["latest_telemetry"]["telemetry"]["error_codes"] == ["P0128"]


def test_vehicle_detail_uses_newest_frame(client: TestClient) -> None:
    client.post("/api/v1/vehicles/telemetry", json=_payload(Scenario.NORMAL, "VH-004"))
    newest = client.post(
        "/api/v1/vehicles/telemetry", json=_payload(Scenario.CRITICAL, "VH-004")
    ).json()

    body = client.get(f"{VEHICLES_URL}/VH-004").json()

    assert body["latest_telemetry"]["telemetry_id"] == newest["telemetry_id"]


def test_unknown_vehicle_detail_returns_404(client: TestClient) -> None:
    response = client.get(f"{VEHICLES_URL}/VH-999")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "VEHICLE_NOT_FOUND"
    assert error["details"] == {"vehicle_id": "VH-999"}


def test_vehicles_endpoints_are_documented(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert "/api/v1/vehicles" in schema["paths"]
    assert "/api/v1/vehicles/telemetry" in schema["paths"]
    assert "/api/v1/vehicles/{vehicle_id}" in schema["paths"]
