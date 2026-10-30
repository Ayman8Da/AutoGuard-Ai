"""Unit tests for telemetry contract validation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.models.telemetry import SensorReadings, VehicleTelemetry
from app.utils.time import utc_now
from pydantic import ValidationError


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "vehicle_id": "VH-001",
        "timestamp": utc_now().isoformat(),
        "status": "driving",
        "sensors": {
            "engine_temperature_c": 90.2,
            "battery_voltage_v": 13.8,
            "engine_vibration_mm_s": 2.4,
        },
        "error_codes": ["P0128"],
    }
    payload.update(overrides)
    return payload


def test_valid_payload_is_accepted() -> None:
    telemetry = VehicleTelemetry.model_validate(_payload())

    assert telemetry.vehicle_id == "VH-001"
    assert telemetry.sensors.engine_temperature_c == 90.2


def test_sensor_values_can_be_unavailable() -> None:
    telemetry = VehicleTelemetry.model_validate(
        _payload(sensors={"engine_temperature_c": None, "battery_voltage_v": 13.1})
    )

    assert telemetry.sensors.engine_temperature_c is None
    assert telemetry.sensors.engine_vibration_mm_s is None
    assert telemetry.sensors.available == ["battery_voltage_v"]


@pytest.mark.parametrize("missing", ["vehicle_id", "timestamp", "status", "sensors"])
def test_required_fields_are_enforced(missing: str) -> None:
    payload = _payload()
    payload.pop(missing)

    with pytest.raises(ValidationError):
        VehicleTelemetry.model_validate(payload)


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        VehicleTelemetry.model_validate(_payload(engine_rpm=2100))


def test_unknown_sensor_field_is_rejected() -> None:
    payload = _payload(sensors={"engine_temperature_c": 90.0, "oil_pressure_bar": 3.1})

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        VehicleTelemetry.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("engine_temperature_c", 400.0),
        ("engine_temperature_c", -80.0),
        ("battery_voltage_v", -1.0),
        ("battery_voltage_v", 50.0),
        ("engine_vibration_mm_s", 150.0),
    ],
)
def test_implausible_sensor_values_are_rejected(field: str, value: float) -> None:
    payload = _payload(sensors={field: value})

    with pytest.raises(ValidationError):
        VehicleTelemetry.model_validate(payload)


def test_non_finite_sensor_values_are_rejected() -> None:
    with pytest.raises(ValidationError):
        SensorReadings(engine_temperature_c=float("nan"))


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone offset"):
        VehicleTelemetry.model_validate(_payload(timestamp="2026-10-30T10:00:00"))


def test_far_future_timestamp_is_rejected() -> None:
    future = (utc_now() + timedelta(minutes=30)).isoformat()

    with pytest.raises(ValidationError, match="future"):
        VehicleTelemetry.model_validate(_payload(timestamp=future))


def test_timestamp_is_normalised_to_utc() -> None:
    telemetry = VehicleTelemetry.model_validate(
        _payload(timestamp="2026-01-01T12:00:00+02:00")
    )

    assert telemetry.timestamp == datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    assert telemetry.timestamp.tzinfo is UTC


@pytest.mark.parametrize("code", ["BROKEN", "P128", "P01285", "12345", "P01G8"])
def test_malformed_trouble_codes_are_rejected(code: str) -> None:
    with pytest.raises(ValidationError, match="invalid diagnostic trouble code"):
        VehicleTelemetry.model_validate(_payload(error_codes=[code]))


def test_trouble_codes_are_normalised_and_deduplicated() -> None:
    telemetry = VehicleTelemetry.model_validate(
        _payload(error_codes=["p0128", " P0128 ", "U0100"])
    )

    assert telemetry.error_codes == ["P0128", "U0100"]


def test_too_many_trouble_codes_are_rejected() -> None:
    codes = [f"P{i:04d}" for i in range(21)]

    with pytest.raises(ValidationError):
        VehicleTelemetry.model_validate(_payload(error_codes=codes))


def test_vehicle_id_format_is_enforced() -> None:
    with pytest.raises(ValidationError, match="vehicle_id"):
        VehicleTelemetry.model_validate(_payload(vehicle_id="CAR-1"))
