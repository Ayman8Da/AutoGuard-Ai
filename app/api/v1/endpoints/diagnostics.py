"""Diagnostic report read endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DiagnosticsServiceDep
from app.models.diagnostics import DiagnosticReport, DiagnosticSummary

router = APIRouter(tags=["Diagnostics"])


@router.get(
    "/diagnostics",
    response_model=list[DiagnosticSummary],
    summary="List diagnostic reports",
    description=(
        "Returns the most recent completed diagnostic reports, newest first, as "
        "compact summaries. Full findings are available from the detail endpoint."
    ),
)
async def list_diagnostics(
    service: DiagnosticsServiceDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[DiagnosticSummary]:
    return service.list_reports(limit=limit)


@router.get(
    "/diagnostics/{diagnostic_id}",
    response_model=DiagnosticReport,
    summary="Get a diagnostic report",
    description=(
        "Returns the full report: findings, DTC interpretations, deterministic risk "
        "assessment, maintenance plan and per-agent execution ledger."
    ),
    responses={404: {"description": "Diagnostic report was not found"}},
)
async def get_diagnostic(
    diagnostic_id: str,
    service: DiagnosticsServiceDep,
) -> DiagnosticReport:
    return service.get_report(diagnostic_id)
