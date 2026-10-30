"""Vehicle catalogue schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import FuelType, VehicleStatus
from app.models.telemetry import TelemetryRecord


class Vehicle(BaseModel):
    """Static description of a simulated vehicle."""

    vehicle_id: str = Field(description="Fleet identifier, e.g. VH-001")
    make: str
    model: str
    year: int = Field(ge=1990, le=2030)
    fuel_type: FuelType


class VehicleSummary(Vehicle):
    """Vehicle plus the most recent operating state, if any."""

    operating_status: VehicleStatus | None = Field(
        default=None, description="Status from the latest telemetry frame"
    )
    last_seen: datetime | None = Field(
        default=None, description="Timestamp of the latest telemetry frame"
    )


class VehicleDetail(VehicleSummary):
    """Vehicle with its latest telemetry record."""

    latest_telemetry: TelemetryRecord | None = None
