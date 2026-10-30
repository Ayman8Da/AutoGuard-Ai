"""Versioned API router.

Domain routers are attached here as the corresponding phases are implemented.
Keeping the aggregation in one place means ``main.py`` never needs to change when
a new endpoint group lands.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import diagnostics, vehicles

api_router = APIRouter()
api_router.include_router(vehicles.router)
api_router.include_router(diagnostics.router)
