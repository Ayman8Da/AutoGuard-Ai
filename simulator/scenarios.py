"""Deterministic telemetry scenarios.

Each scenario defines a reproducible fixture (exact sensor values, operating
status and diagnostic trouble codes) plus the band its jittered values must stay
inside. The bands foreshadow the deterministic risk rules implemented in a later
phase; they are not real-world engineering thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.models.enums import VehicleStatus


class Scenario(StrEnum):
    """Supported simulator scenarios."""

    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
    SENSOR_FAILURE = "sensor_failure"


@dataclass(frozen=True)
class ScenarioDefinition:
    """Immutable description of one telemetry scenario."""

    key: Scenario
    description: str
    status: VehicleStatus
    sensors: dict[str, float | None]
    error_codes: tuple[str, ...]


SCENARIO_DEFINITIONS: dict[Scenario, ScenarioDefinition] = {
    Scenario.NORMAL: ScenarioDefinition(
        key=Scenario.NORMAL,
        description=(
            "All readings within normal bands: temperature 80-98 C, "
            "battery 13.5-14.4 V, vibration 0-3 mm/s. No trouble codes."
        ),
        status=VehicleStatus.DRIVING,
        sensors={
            "engine_temperature_c": 89.5,
            "battery_voltage_v": 13.9,
            "engine_vibration_mm_s": 2.2,
        },
        error_codes=(),
    ),
    Scenario.WARNING: ScenarioDefinition(
        key=Scenario.WARNING,
        description=(
            "Cooling degradation: temperature 100-112 C, battery 12.2-13.0 V, "
            "vibration 5-7 mm/s. Thermostat code P0128."
        ),
        status=VehicleStatus.DRIVING,
        sensors={
            "engine_temperature_c": 104.2,
            "battery_voltage_v": 12.6,
            "engine_vibration_mm_s": 5.8,
        },
        error_codes=("P0128",),
    ),
    Scenario.CRITICAL: ScenarioDefinition(
        key=Scenario.CRITICAL,
        description=(
            "Severe overheating and electrical stress: temperature >= 116 C, "
            "battery <= 11.5 V, vibration >= 8.4 mm/s. Overheat and misfire codes."
        ),
        status=VehicleStatus.DRIVING,
        sensors={
            "engine_temperature_c": 121.8,
            "battery_voltage_v": 11.2,
            "engine_vibration_mm_s": 9.4,
        },
        error_codes=("P0217", "P0301"),
    ),
    Scenario.SENSOR_FAILURE: ScenarioDefinition(
        key=Scenario.SENSOR_FAILURE,
        description=(
            "Temperature and vibration sensors unavailable (null), battery still "
            "reporting. Communication loss code U0100."
        ),
        status=VehicleStatus.FAULT,
        sensors={
            "engine_temperature_c": None,
            "battery_voltage_v": 13.1,
            "engine_vibration_mm_s": None,
        },
        error_codes=("U0100",),
    ),
}


def get_scenario(value: Scenario | str) -> ScenarioDefinition:
    """Resolve a scenario from its enum or string value."""
    try:
        scenario = Scenario(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in Scenario)
        raise ValueError(f"unknown scenario {value!r}; expected one of: {allowed}") from exc
    return SCENARIO_DEFINITIONS[scenario]
