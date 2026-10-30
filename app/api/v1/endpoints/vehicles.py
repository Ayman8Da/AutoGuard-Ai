"""Vehicle fleet and telemetry ingestion endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.api.deps import TelemetryServiceDep
from app.models.telemetry import TelemetryRecord, VehicleTelemetry
from app.models.vehicle import VehicleDetail, VehicleSummary

router = APIRouter(tags=["Vehicles"])


@router.post(
    "/vehicles/telemetry",
    response_model=TelemetryRecord,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a vehicle telemetry frame",
    description=(
        "Validates and stores one simulated telemetry frame. Unknown fields, "
        "implausible sensor values, naive timestamps and malformed diagnostic "
        "trouble codes are rejected with a 422 error envelope. The multi-agent "
        "diagnostic workflow will be attached to this response in a later phase."
    ),
    responses={
        404: {"description": "Vehicle is not part of the simulated fleet"},
        422: {"description": "Payload failed validation"},
    },
)
async def ingest_telemetry(
    payload: VehicleTelemetry,
    request: Request,
    service: TelemetryServiceDep,
) -> TelemetryRecord:
    """Store a validated telemetry frame and return the persisted record."""
    correlation_id = request.state.correlation_id
    return service.ingest(payload, correlation_id=correlation_id)


@router.get(
    "/vehicles",
    response_model=list[VehicleSummary],
    summary="List simulated vehicles",
    description="Returns the fleet with the operating state from its latest telemetry frame.",
)
async def list_vehicles(service: TelemetryServiceDep) -> list[VehicleSummary]:
    return service.list_vehicles()


@router.get(
    "/vehicles/{vehicle_id}",
    response_model=VehicleDetail,
    summary="Get a simulated vehicle",
    description="Returns one fleet vehicle and its most recent telemetry record.",
    responses={404: {"description": "Vehicle is not part of the simulated fleet"}},
)
async def get_vehicle(vehicle_id: str, service: TelemetryServiceDep) -> VehicleDetail:
    return service.get_vehicle(vehicle_id)
