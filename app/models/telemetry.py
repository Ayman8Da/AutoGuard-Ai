"""Vehicle telemetry contracts.

These models are the boundary between the simulator / API client and the agent
workflow. They are deliberately strict:

- unknown fields are rejected (``extra="forbid"``);
- sensor values must be finite and physically plausible;
- timestamps must be timezone-aware and cannot come from the far future;
- diagnostic trouble codes are normalised to the OBD-II letter + 4 hex format.

``None`` represents an **unavailable sensor reading**. That is different from a
missing field: a sensor failure scenario legitimately reports ``null`` values and
must still be accepted so it can be diagnosed.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import VehicleStatus
from app.utils.time import utc_now

_DTC_PATTERN = re.compile(r"^[PCBU][0-9A-F]{4}$")
MAX_FUTURE_SKEW = timedelta(minutes=5)


class SensorReadings(BaseModel):
    """Raw sensor values. ``None`` means the sensor did not report a value."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    engine_temperature_c: Annotated[
        float | None,
        Field(default=None, ge=-50, le=300, description="Coolant temperature in °C"),
    ]
    battery_voltage_v: Annotated[
        float | None,
        Field(default=None, ge=0, le=40, description="Battery terminal voltage in V"),
    ]
    engine_vibration_mm_s: Annotated[
        float | None,
        Field(default=None, ge=0, le=100, description="Engine vibration in mm/s RMS"),
    ]

    @property
    def available(self) -> list[str]:
        """Names of sensors that reported a value."""
        return [
            name
            for name in ("engine_temperature_c", "battery_voltage_v", "engine_vibration_mm_s")
            if getattr(self, name) is not None
        ]


class VehicleTelemetry(BaseModel):
    """One telemetry frame emitted by a simulated vehicle."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "vehicle_id": "VH-001",
                    "timestamp": "2026-10-30T10:00:00Z",
                    "status": "driving",
                    "sensors": {
                        "engine_temperature_c": 89.5,
                        "battery_voltage_v": 13.9,
                        "engine_vibration_mm_s": 2.2,
                    },
                    "error_codes": [],
                }
            ]
        },
    )

    vehicle_id: Annotated[
        str,
        Field(pattern=r"^VH-\d{3}$", description="Simulated vehicle identifier"),
    ]
    timestamp: Annotated[datetime, Field(description="Reading time (ISO-8601, timezone-aware)")]
    status: VehicleStatus
    sensors: SensorReadings
    error_codes: Annotated[
        list[str],
        Field(
            default_factory=list,
            max_length=20,
            description="OBD-II diagnostic trouble codes, e.g. P0128",
        ),
    ]

    @field_validator("timestamp")
    @classmethod
    def _validate_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone offset (e.g. 2026-10-30T10:00:00Z)")
        if value > utc_now() + MAX_FUTURE_SKEW:
            raise ValueError("timestamp cannot be more than 5 minutes in the future")
        return value.astimezone(UTC)

    @field_validator("error_codes")
    @classmethod
    def _normalise_error_codes(cls, codes: list[str]) -> list[str]:
        normalised: list[str] = []
        for raw_code in codes:
            code = raw_code.strip().upper()
            if not _DTC_PATTERN.fullmatch(code):
                raise ValueError(f"invalid diagnostic trouble code: {raw_code!r}")
            if code not in normalised:
                normalised.append(code)
        return normalised


class TelemetryRecord(BaseModel):
    """A telemetry frame persisted by the API."""

    telemetry_id: str = Field(description="Server-generated telemetry identifier")
    correlation_id: str = Field(description="Correlation ID of the ingesting request")
    received_at: datetime = Field(description="Server receipt time (UTC)")
    telemetry: VehicleTelemetry
