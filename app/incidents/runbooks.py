"""Operational runbooks referenced by incidents.

Three runbooks cover the incident types AutoGuard AI can raise:

* ``high_risk_vehicle`` — a deterministic CRITICAL risk classification;
* ``agent_failure`` — an agent exhausted its retry budget;
* ``llm_provider_failure`` — the narrative provider failed and the report was degraded.

They are advisory operational procedures for this demonstration, not
manufacturer service manuals.
"""

from __future__ import annotations

from app.incidents.models import Runbook, RunbookStep

HIGH_RISK_VEHICLE = Runbook(
    runbook_id="high_risk_vehicle",
    title="High-risk vehicle response",
    trigger="CRITICAL_VEHICLE_RISK incident (deterministic risk level CRITICAL)",
    summary=(
        "A telemetry frame breached a safety-critical threshold or accumulated a "
        "critical risk score. Treat the vehicle as unsafe until inspected."
    ),
    owner="Fleet Operations",
    steps=[
        RunbookStep(
            order=1,
            title="Acknowledge the incident",
            detail=(
                "Claim the incident and confirm the vehicle, risk score and triggering "
                "findings in the diagnostic report."
            ),
        ),
        RunbookStep(
            order=2,
            title="Restrict vehicle use",
            detail=(
                "If the vehicle is in service, instruct the driver to stop safely and "
                "arrange recovery. Do not clear trouble codes to continue driving."
            ),
        ),
        RunbookStep(
            order=3,
            title="Inspect the reported systems",
            detail=(
                "Follow the maintenance actions in priority order (cooling, electrical, "
                "mechanical). Verify sensor values with an independent diagnostic tool."
            ),
        ),
        RunbookStep(
            order=4,
            title="Record the resolution",
            detail=(
                "Document inspection findings and repairs performed by the workshop. "
                "No repair is performed or claimed by AutoGuard AI."
            ),
        ),
    ],
    verification=(
        "A subsequent telemetry frame must return risk LOW/MEDIUM with no hard override "
        "before the vehicle is released."
    ),
)

AGENT_FAILURE = Runbook(
    runbook_id="agent_failure",
    title="Agent execution failure response",
    trigger="AGENT_EXECUTION_FAILED incident (retry budget exhausted)",
    summary=(
        "A diagnostic agent failed on every allowed attempt, so no report was produced. "
        "The telemetry frame is stored but undiagnosed."
    ),
    owner="Platform Engineering",
    steps=[
        RunbookStep(
            order=1,
            title="Correlate the failure",
            detail=(
                "Use the correlation ID and workflow ID to collect the structured JSON "
                "logs for every attempt, including error type and duration."
            ),
        ),
        RunbookStep(
            order=2,
            title="Check recent changes",
            detail=(
                "Compare the deployment version and rule/threshold changes with the first "
                "observed failure time. Roll back if a regression is suspected."
            ),
        ),
        RunbookStep(
            order=3,
            title="Reproduce safely",
            detail=(
                "Replay the stored telemetry frame against a non-production instance and "
                "inspect the failing agent input/output."
            ),
        ),
        RunbookStep(
            order=4,
            title="Re-drive diagnosis",
            detail=(
                "After the fix, re-ingest or replay the frame and confirm a completed "
                "report is stored under a new workflow ID."
            ),
        ),
    ],
    verification=(
        "The monitoring endpoint shows the agent's failure rate returning to zero and a "
        "completed report exists for the replayed telemetry."
    ),
)

LLM_PROVIDER_FAILURE = Runbook(
    runbook_id="llm_provider_failure",
    title="LLM narrative provider failure response",
    trigger="LLM_PROVIDER_FAILURE incident (LLM_NARRATIVE_UNAVAILABLE warning)",
    summary=(
        "The narrative provider was unavailable or returned invalid structured output. "
        "The diagnostic findings, deterministic risk level and maintenance plan remain valid."
    ),
    owner="Platform Engineering",
    steps=[
        RunbookStep(
            order=1,
            title="Confirm the degradation scope",
            detail=(
                "Check the report's analysis_mode=degraded_deterministic and the llm_error "
                "field. No safety decision depends on the narrative."
            ),
        ),
        RunbookStep(
            order=2,
            title="Check provider health",
            detail=(
                "Verify API key validity, quota, model name and provider status. For Ollama, "
                "confirm the endpoint and model are reachable from the service."
            ),
        ),
        RunbookStep(
            order=3,
            title="Decide whether to switch provider",
            detail=(
                "Either keep the deterministic fallback, switch to configured Ollama, or "
                "rotate the Groq key. Never put secrets in logs or tickets."
            ),
        ),
        RunbookStep(
            order=4,
            title="Re-run narration",
            detail=(
                "Ingest a fresh frame and confirm analysis_mode returns to llm_assisted. "
                "Do not edit historical reports."
            ),
        ),
    ],
    verification=(
        "A new report shows analysis_mode=llm_assisted with no LLM_NARRATIVE_UNAVAILABLE "
        "warning and a provider response time within the configured timeout."
    ),
)

RUNBOOKS: dict[str, Runbook] = {
    runbook.runbook_id: runbook
    for runbook in (HIGH_RISK_VEHICLE, AGENT_FAILURE, LLM_PROVIDER_FAILURE)
}


def get_runbook(runbook_id: str) -> Runbook:
    """Return a runbook by ID."""
    try:
        return RUNBOOKS[runbook_id]
    except KeyError as exc:
        raise KeyError(f"unknown runbook {runbook_id!r}") from exc
