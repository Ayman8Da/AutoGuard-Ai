"""Simulated vehicle telemetry generator.

Two modes are supported:

* **Fixture mode** (``build_scenario_telemetry``, ``--no-jitter``): exact,
  reproducible values taken from ``scenarios.SCENARIO_DEFINITIONS``.
* **Jitter mode** (``VehicleSimulator(seed=...)``, default): small, seeded
  random variation around the fixture that keeps the scenario classification.

Usage::

    python -m simulator.vehicle_simulator --scenario critical --pretty
    python -m simulator.vehicle_simulator --all --seed 42 --pretty
"""

from __future__ import annotations

import argparse
import json
import random
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from app.models.telemetry import SensorReadings, VehicleTelemetry
from app.services.fleet import FLEET_BY_ID
from app.utils.time import utc_now

from simulator.scenarios import Scenario, ScenarioDefinition, get_scenario

DEFAULT_VEHICLE_ID = "VH-001"

#: Maximum absolute jitter per sensor. Kept small so a jittered frame never
#: crosses into another scenario's band.
_JITTER_SPREADS: dict[Scenario, dict[str, float]] = {
    Scenario.NORMAL: {
        "engine_temperature_c": 2.0,
        "battery_voltage_v": 0.15,
        "engine_vibration_mm_s": 0.3,
    },
    Scenario.WARNING: {
        "engine_temperature_c": 3.0,
        "battery_voltage_v": 0.2,
        "engine_vibration_mm_s": 0.8,
    },
    Scenario.CRITICAL: {
        "engine_temperature_c": 4.0,
        "battery_voltage_v": 0.3,
        "engine_vibration_mm_s": 1.0,
    },
    Scenario.SENSOR_FAILURE: {
        "battery_voltage_v": 0.2,
    },
}


def _resolve_definition(scenario: Scenario | str) -> ScenarioDefinition:
    return get_scenario(scenario)


def _require_known_vehicle(vehicle_id: str) -> None:
    if vehicle_id not in FLEET_BY_ID:
        known = ", ".join(FLEET_BY_ID)
        raise ValueError(f"unknown vehicle {vehicle_id!r}; simulated fleet: {known}")


def build_scenario_telemetry(
    scenario: Scenario | str,
    vehicle_id: str = DEFAULT_VEHICLE_ID,
    timestamp: datetime | None = None,
) -> VehicleTelemetry:
    """Build the exact (non-jittered) fixture for a scenario."""
    definition = _resolve_definition(scenario)
    _require_known_vehicle(vehicle_id)
    return VehicleTelemetry(
        vehicle_id=vehicle_id,
        timestamp=timestamp or utc_now(),
        status=definition.status,
        sensors=SensorReadings(**definition.sensors),
        error_codes=list(definition.error_codes),
    )


class VehicleSimulator:
    """Stateful simulator with an optional reproducible random seed."""

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def generate(
        self,
        scenario: Scenario | str = Scenario.NORMAL,
        vehicle_id: str = DEFAULT_VEHICLE_ID,
        timestamp: datetime | None = None,
        *,
        jitter: bool = True,
    ) -> VehicleTelemetry:
        """Generate one telemetry frame for the given scenario."""
        definition = _resolve_definition(scenario)
        _require_known_vehicle(vehicle_id)

        sensors = dict(definition.sensors)
        if jitter:
            for field, spread in _JITTER_SPREADS[definition.key].items():
                value = sensors.get(field)
                if value is None:
                    continue
                sensors[field] = round(max(0.0, value + self._rng.uniform(-spread, spread)), 2)

        return VehicleTelemetry(
            vehicle_id=vehicle_id,
            timestamp=timestamp or utc_now(),
            status=definition.status,
            sensors=SensorReadings(**sensors),
            error_codes=list(definition.error_codes),
        )

    def random_scenario(self) -> Scenario:
        """Pick a scenario using realistic-ish weights (mostly normal)."""
        return self._rng.choices(
            list(Scenario),
            weights=[0.50, 0.30, 0.15, 0.05],
            k=1,
        )[0]


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint: print JSON telemetry ready for the ingest endpoint."""
    parser = argparse.ArgumentParser(
        description="Generate simulated AutoGuard AI vehicle telemetry as JSON.",
    )
    scenario_group = parser.add_mutually_exclusive_group()
    scenario_group.add_argument(
        "--scenario",
        choices=[scenario.value for scenario in Scenario],
        default=None,
        help="Scenario to generate (default: normal)",
    )
    scenario_group.add_argument(
        "--all",
        action="store_true",
        help="Emit one frame for every scenario",
    )
    parser.add_argument(
        "--vehicle",
        default=DEFAULT_VEHICLE_ID,
        help=f"Fleet vehicle ID (default: {DEFAULT_VEHICLE_ID})",
    )
    parser.add_argument("--seed", type=int, default=None, help="Seed for jitter reproducibility")
    parser.add_argument(
        "--no-jitter",
        action="store_true",
        help="Emit the exact fixture values instead of jittered readings",
    )
    parser.add_argument("--pretty", action="store_true", help="Indent the JSON output")
    args = parser.parse_args(argv)

    simulator = VehicleSimulator(seed=args.seed)
    jitter = not args.no_jitter

    try:
        if args.all:
            payload: Any = [
                simulator.generate(scenario, args.vehicle, jitter=jitter).model_dump(mode="json")
                for scenario in Scenario
            ]
        else:
            scenario = args.scenario or Scenario.NORMAL.value
            payload = simulator.generate(scenario, args.vehicle, jitter=jitter).model_dump(
                mode="json"
            )
    except ValueError as exc:
        parser.error(str(exc))

    print(json.dumps(payload, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
