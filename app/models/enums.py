"""Domain enumerations shared by telemetry, agents and reporting."""

from __future__ import annotations

from enum import StrEnum


class VehicleStatus(StrEnum):
    """Operating status reported by the vehicle."""

    PARKED = "parked"
    IDLE = "idle"
    DRIVING = "driving"
    FAULT = "fault"


class FuelType(StrEnum):
    """Powertrain type of a simulated vehicle."""

    PETROL = "petrol"
    DIESEL = "diesel"
    HYBRID = "hybrid"
