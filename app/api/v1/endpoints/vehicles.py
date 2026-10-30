"""Vehicle fleet, telemetry ingestion and diagnosis endpoints."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import DiagnosticsServiceDep, TelemetryServiceDep
from app.core.correlation import get_correlation_id
from app.models.diagnostics import DiagnosticReport
from app.models.telemetry import VehicleTelemetry
from app.models.vehicle import VehicleDetail, VehicleSummary

router = APIRouter(tags=["Vehicles"])


@router.post(
    "/vehicles/telemetry",
    response_model=DiagnosticReport,
    status_code=status.HTTP_200_OK,
    summary="Ingest telemetry and run the diagnostic workflow",
    description=(
        "Validates and stores one simulated telemetry frame, then runs the "
        "multi-agent workflow (Diagnostic → Risk Assessment → Maintenance → "
        "Reporting). The response is the completed report, including a "
        "deterministic risk level and an advisory maintenance plan. No inspection "
        "or repair is performed. Unknown fields, implausible sensor values, naive "
        "timestamps and malformed diagnostic trouble codes are rejected with a 422 "
        "error envelope."
    ),
    responses={
        404: {"description": "Vehicle is not part of the simulated fleet"},
        422: {"description": "Payload failed validation"},
        500: {"description": "An agent failed after exhausting its retry budget"},
    },
)
async def ingest_telemetry(
    payload: VehicleTelemetry,
    telemetry_service: TelemetryServiceDep,
    diagnostics_service: DiagnosticsServiceDep,
) -> DiagnosticReport:
    """Store a validated frame and return its diagnostic report."""
    record = telemetry_service.ingest(payload, correlation_id=get_correlation_id())
    return await diagnostics_service.analyze(record)


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
