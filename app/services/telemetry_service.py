"""Telemetry ingestion and fleet read models."""

from __future__ import annotations

from collections.abc import Sequence

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.models.telemetry import TelemetryRecord, VehicleTelemetry
from app.models.vehicle import Vehicle, VehicleDetail, VehicleSummary
from app.services.fleet import SIMULATED_FLEET
from app.services.repositories import TelemetryRepository
from app.utils.ids import generate_id
from app.utils.time import utc_now

logger = get_logger("services.telemetry")


class TelemetryService:
    """Coordinates validation outcomes, persistence and fleet read models."""

    def __init__(
        self,
        repository: TelemetryRepository,
        fleet: Sequence[Vehicle] = SIMULATED_FLEET,
    ) -> None:
        self._repository = repository
        self._fleet: dict[str, Vehicle] = {vehicle.vehicle_id: vehicle for vehicle in fleet}

    def ingest(self, telemetry: VehicleTelemetry, correlation_id: str) -> TelemetryRecord:
        """Persist one telemetry frame for a known fleet vehicle."""
        self._require_vehicle(telemetry.vehicle_id)

        record = TelemetryRecord(
            telemetry_id=generate_id("TEL"),
            correlation_id=correlation_id,
            received_at=utc_now(),
            telemetry=telemetry,
        )
        self._repository.add(record)

        logger.info(
            "telemetry_ingested",
            extra={
                "telemetry_id": record.telemetry_id,
                "vehicle_id": telemetry.vehicle_id,
                "operating_status": telemetry.status.value,
                "available_sensors": telemetry.sensors.available,
                "error_codes": telemetry.error_codes,
            },
        )
        return record

    def list_vehicles(self) -> list[VehicleSummary]:
        """Return the whole simulated fleet with its latest known state."""
        summaries: list[VehicleSummary] = []
        for vehicle in self._fleet.values():
            latest = self._repository.latest_for_vehicle(vehicle.vehicle_id)
            summaries.append(
                VehicleSummary(
                    **vehicle.model_dump(),
                    operating_status=latest.telemetry.status if latest else None,
                    last_seen=latest.telemetry.timestamp if latest else None,
                )
            )
        return summaries

    def get_vehicle(self, vehicle_id: str) -> VehicleDetail:
        """Return one fleet vehicle, including its latest telemetry frame."""
        vehicle = self._require_vehicle(vehicle_id)
        latest = self._repository.latest_for_vehicle(vehicle_id)
        return VehicleDetail(
            **vehicle.model_dump(),
            operating_status=latest.telemetry.status if latest else None,
            last_seen=latest.telemetry.timestamp if latest else None,
            latest_telemetry=latest,
        )

    def _require_vehicle(self, vehicle_id: str) -> Vehicle:
        vehicle = self._fleet.get(vehicle_id)
        if vehicle is None:
            raise NotFoundError(
                f"Vehicle '{vehicle_id}' is not part of the simulated fleet.",
                code="VEHICLE_NOT_FOUND",
                details={"vehicle_id": vehicle_id},
            )
        return vehicle
