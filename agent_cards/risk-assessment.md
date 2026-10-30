# Agent Card — Risk Assessment Agent

| Field | Value |
| ----- | ----- |
| Agent ID | `risk_assessment` |
| Class | `RiskAssessmentAgent` (`app/agents/risk.py`) |
| Owner | Safety & Reliability |
| Autonomy | **None** — deterministic scoring only |
| Determinism | **Fully deterministic** |
| LLM use | **Forbidden** |
| Status | Implemented (Phase 3) |

## Purpose

Converts findings, DTCs and raw sensor values into an explainable risk score and level.
This is the safety-critical decision point of AutoGuard AI.

## Inputs

- `VehicleTelemetry` (raw values, used for hard safety overrides).
- `DiagnosticResult` (findings and DTC interpretations).

## Outputs

`RiskAssessment`:

- `score` — integer sum of weighted reasons.
- `level` — `low` / `medium` / `high` / `critical`.
- `reasons[]` — code, description and score contribution.
- `hard_override` — true when a safety threshold forced CRITICAL.
- `threshold_version` — currently `1.0`.

## Bands

| Score | Level |
| ----- | ----- |
| 0–1 | LOW |
| 2–5 | MEDIUM |
| 6–8 | HIGH |
| ≥ 9 | CRITICAL |

## Hard safety overrides

Any one of the following forces `CRITICAL` regardless of the numeric score:

| Sensor | Threshold |
| ------ | --------- |
| Engine temperature | > 118 °C |
| Battery voltage | < 11.5 V |
| Engine vibration | > 9.0 mm/s |

Every override adds a zero-point `SAFETY_OVERRIDE` reason so the report explains *why*
the level was raised.

## Rules

- Identical telemetry must always produce the same score and level.
- Unknown DTCs contribute 1 point; known DTCs contribute their catalogue weight.
- A clean frame gets an explicit `NO_ANOMALIES` reason rather than an empty list.
- The LLM has no access to this agent and cannot influence its output.

## Failure handling

The agent is pure and synchronous. A raised exception is treated as an agent failure,
retried by the Orchestrator, and then surfaced as `AGENT_EXECUTION_FAILED`. It never
returns a partial or guessed assessment.

## Safety constraints

- Never accept an LLM-provided risk level.
- Never remove a hard override to reduce the score.
- Threshold changes require Safety Reviewer approval and a threshold version bump.

## Verification

- `tests/unit/test_rules.py`
- `tests/unit/test_agents.py`
- `tests/api/test_diagnostics_api.py`
- `tests/api/test_observability_api.py`
