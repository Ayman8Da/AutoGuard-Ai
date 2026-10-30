"""The simulated vehicle fleet used by the API and the simulator."""

from __future__ import annotations

from app.models.enums import FuelType
from app.models.vehicle import Vehicle

SIMULATED_FLEET: tuple[Vehicle, ...] = (
    Vehicle(
        vehicle_id="VH-001",
        make="Toyota",
        model="Corolla",
        year=2021,
        fuel_type=FuelType.HYBRID,
    ),
    Vehicle(
        vehicle_id="VH-002",
        make="Ford",
        model="Focus",
        year=2019,
        fuel_type=FuelType.PETROL,
    ),
    Vehicle(
        vehicle_id="VH-003",
        make="BMW",
        model="320i",
        year=2020,
        fuel_type=FuelType.PETROL,
    ),
    Vehicle(
        vehicle_id="VH-004",
        make="Renault",
        model="Clio",
        year=2018,
        fuel_type=FuelType.DIESEL,
    ),
    Vehicle(
        vehicle_id="VH-005",
        make="Volkswagen",
        model="Golf",
        year=2022,
        fuel_type=FuelType.PETROL,
    ),
)

FLEET_BY_ID: dict[str, Vehicle] = {vehicle.vehicle_id: vehicle for vehicle in SIMULATED_FLEET}
