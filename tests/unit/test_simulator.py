"""Unit tests for deterministic scenarios and the seeded simulator."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from app.models.telemetry import VehicleTelemetry
from simulator.scenarios import Scenario, get_scenario
from simulator.vehicle_simulator import (
    VehicleSimulator,
    build_scenario_telemetry,
    main,
)

FIXED_TIMESTAMP = datetime(2025, 1, 15, 8, 30, tzinfo=UTC)


@pytest.mark.parametrize("scenario", list(Scenario))
def test_each_scenario_builds_valid_telemetry(scenario: Scenario) -> None:
    telemetry = build_scenario_telemetry(scenario, "VH-001", FIXED_TIMESTAMP)

    assert isinstance(telemetry, VehicleTelemetry)
    assert telemetry.vehicle_id == "VH-001"
    assert telemetry.status is get_scenario(scenario).status
    assert telemetry.error_codes == list(get_scenario(scenario).error_codes)


def test_normal_fixture_is_within_normal_bands() -> None:
    telemetry = build_scenario_telemetry(Scenario.NORMAL, timestamp=FIXED_TIMESTAMP)

    assert 80 <= telemetry.sensors.engine_temperature_c <= 98
    assert 13.5 <= telemetry.sensors.battery_voltage_v <= 14.4
    assert 0 <= telemetry.sensors.engine_vibration_mm_s <= 3
    assert telemetry.error_codes == []


def test_critical_fixture_carries_overheat_and_misfire_codes() -> None:
    telemetry = build_scenario_telemetry(Scenario.CRITICAL, timestamp=FIXED_TIMESTAMP)

    assert telemetry.sensors.engine_temperature_c >= 116
    assert telemetry.sensors.battery_voltage_v <= 11.5
    assert telemetry.sensors.engine_vibration_mm_s >= 8.4
    assert telemetry.error_codes == ["P0217", "P0301"]


def test_sensor_failure_fixture_has_unavailable_readings() -> None:
    telemetry = build_scenario_telemetry(Scenario.SENSOR_FAILURE, timestamp=FIXED_TIMESTAMP)

    assert telemetry.sensors.engine_temperature_c is None
    assert telemetry.sensors.engine_vibration_mm_s is None
    assert telemetry.sensors.battery_voltage_v is not None
    assert telemetry.sensors.available == ["battery_voltage_v"]
    assert telemetry.error_codes == ["U0100"]


def test_seeded_simulator_is_reproducible() -> None:
    first = VehicleSimulator(seed=42).generate(Scenario.WARNING, timestamp=FIXED_TIMESTAMP)
    second = VehicleSimulator(seed=42).generate(Scenario.WARNING, timestamp=FIXED_TIMESTAMP)

    assert first.model_dump() == second.model_dump()


def test_jitter_changes_values_but_keeps_scenario_band() -> None:
    simulator = VehicleSimulator(seed=7)

    for _ in range(25):
        telemetry = simulator.generate(Scenario.WARNING, timestamp=FIXED_TIMESTAMP)
        assert 100 <= telemetry.sensors.engine_temperature_c <= 112
        assert 12.2 <= telemetry.sensors.battery_voltage_v <= 13.0
        assert 5 <= telemetry.sensors.engine_vibration_mm_s <= 7

    fixture = build_scenario_telemetry(Scenario.WARNING, timestamp=FIXED_TIMESTAMP)
    assert telemetry.sensors.engine_temperature_c != fixture.sensors.engine_temperature_c


def test_no_jitter_matches_fixture_exactly() -> None:
    generated = VehicleSimulator(seed=1).generate(
        Scenario.CRITICAL, timestamp=FIXED_TIMESTAMP, jitter=False
    )
    fixture = build_scenario_telemetry(Scenario.CRITICAL, timestamp=FIXED_TIMESTAMP)

    assert generated.model_dump() == fixture.model_dump()


def test_random_scenario_is_always_supported() -> None:
    simulator = VehicleSimulator(seed=3)

    selections = {simulator.random_scenario() for _ in range(100)}

    assert selections <= set(Scenario)
    assert len(selections) > 1


def test_unknown_scenario_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown scenario"):
        get_scenario("meltdown")


def test_unknown_vehicle_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown vehicle"):
        build_scenario_telemetry(Scenario.NORMAL, "VH-999")


def test_cli_all_emits_every_scenario(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["--all", "--no-jitter"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert [item["status"] for item in payload] == ["driving", "driving", "driving", "fault"]
    assert len(payload) == len(Scenario)


def test_cli_rejects_unknown_vehicle() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--vehicle", "VH-999"])

    assert excinfo.value.code == 2
