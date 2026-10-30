"""Versioned API router.

Domain routers (vehicles, diagnostics, monitoring, incidents) are attached here
as the corresponding phases are implemented. Keeping the aggregation in one
place means ``main.py`` never needs to change when a new endpoint group lands.
"""

from __future__ import annotations

from fastapi import APIRouter

api_router = APIRouter()
