# Agent Governance

Status: applies to Phases 1–4 of AutoGuard AI. This is an engineering demonstration;
it is **not** a certified automotive safety process (ISO 26262 or equivalent).

## 1. Principles

1. **Deterministic safety.** Risk levels, hard overrides and maintenance priority are
   produced by code, never by an LLM.
2. **Least autonomy.** Agents receive only what they need, return typed objects and cannot
   invoke each other outside the Orchestrator's graph.
3. **No fabricated success.** A failed agent produces an incident and an error envelope,
   never a partial or invented report.
4. **Traceability by default.** Every request, agent attempt and incident carries the same
   correlation ID; reports also carry workflow, telemetry and diagnostic IDs.
5. **Fail visibly.** LLM outages degrade the report and are recorded in `warnings[]`; they
   are never silently hidden.
6. **Advisory output.** Maintenance advice is not a repair. `repair_performed` is always
   `false` and the disclaimer is always attached.
7. **Offline testability.** The default `mock` provider means CI needs no API key and no
   external service.

## 2. Agent inventory and ownership

| Agent | Owner | Autonomy | LLM access | Card |
| ----- | ----- | -------- | ---------- | ---- |
| Orchestrator | Platform Engineering | Supervised | No | [orchestrator.md](../agent_cards/orchestrator.md) |
| Diagnostic | Vehicle Diagnostics | Supervised | Narrative only | [diagnostic.md](../agent_cards/diagnostic.md) |
| Risk Assessment | Safety & Reliability | None | **Forbidden** | [risk-assessment.md](../agent_cards/risk-assessment.md) |
| Maintenance | Fleet Maintenance | Advisory | No | [maintenance.md](../agent_cards/maintenance.md) |
| Reporting | Compliance & Documentation | Assembly | No | [reporting.md](../agent_cards/reporting.md) |
| Monitoring | Platform Engineering / SRE | Passive | No | [monitoring.md](../agent_cards/monitoring.md) |

## 3. Change control

| Change | Required approval | Required evidence |
| ------ | ----------------- | ----------------- |
| Sensor thresholds, DTC weights, risk bands, hard overrides | Safety Reviewer + owner | Updated `threshold_version`, unit tests at every boundary, changelog entry |
| Agent topology, retry budget, failure semantics | Platform Engineering + Safety Reviewer | Integration + failure tests, updated agent cards |
| LLM prompt or response schema | Diagnostics owner + Platform Engineering | Parsing tests, degraded-path test, no new fields accepted |
| New incident trigger or runbook | SRE + Platform Engineering | Incident test, runbook link, monitoring assertion |
| New endpoint or contract change | API owner | OpenAPI diff, API tests, README update |
| Dependency upgrade | Platform Engineering | Green CI, lockfile/requirements diff |

Threshold or topology changes must not be merged with unrelated feature work.

## 4. Prompt and model governance

- The LLM receives **only** already-computed findings; it never sees raw telemetry as the
  source of truth for a decision.
- The response schema is strict: exactly one `summary` key. Extra keys, empty output and
  non-JSON are rejected (`InvalidLLMResponseError`).
- The prompt is versioned in source (`app/agents/llm.py`) and reviewed like code.
- Provider selection is configuration, not code: `mock`, `groq` or `ollama`.
- API keys are `SecretStr`, never logged, never returned and never committed.
- A provider failure degrades narration; it never changes findings, risk or maintenance.
- Model or prompt changes must be evaluated against the four simulator scenarios before
  merge: `normal`, `warning`, `critical`, `sensor_failure`.

## 5. Incident policy

| Incident | Trigger | Severity | Runbook |
| -------- | ------- | -------- | ------- |
| `CRITICAL_VEHICLE_RISK` | Risk level `critical` | critical | `high_risk_vehicle` |
| `AGENT_EXECUTION_FAILED` | Retry budget exhausted | high | `agent_failure` |
| `LLM_PROVIDER_FAILURE` | `LLM_NARRATIVE_UNAVAILABLE` warning | medium | `llm_provider_failure` |

- Incidents are immutable evidence; the demo does not implement status transitions. All
  incidents start as `open`.
- Invalid telemetry is a `422` boundary error, not an incident: malformed client input
  must not page an operator.
- Every incident links to the correlation ID and, where available, vehicle, diagnostic and
  workflow IDs.
- Runbooks are advisory operational procedures, not manufacturer service manuals.

## 6. Data handling

- All telemetry is synthetic. No real vehicle, customer or personal data is processed.
- Reports contain vehicle IDs from the five-vehicle simulated fleet only.
- Structured logs intentionally exclude raw telemetry payloads and secrets.
- In-memory stores reset on restart; this is a documented demo limitation.
- MongoDB Atlas or another durable store would require a data-retention review before use.

## 7. Quality gates

A change is mergeable only when all of the following pass locally and in CI:

1. `ruff check .` — no lint findings.
2. `pytest` — all tests pass.
3. Coverage ≥ 80% for `app` and `simulator` (current: 97% branch coverage).
4. Failure paths are tested: exhausted retries, provider outage, invalid telemetry.
5. API contract tests cover new or changed endpoints.
6. Documentation (README, architecture, agent cards) is updated in the same change.

## 8. Review and audit trail

- Git history is the audit trail; each phase lands as one reviewable commit.
- Agent executions in a report are the runtime audit trail for one workflow.
- Incidents are the operational audit trail for degraded or failed workflows.
- The Monitoring endpoint is the live operational view; it is not a durable audit log.

## 9. Known limitations

- No authentication or multi-tenancy; the demo is intended for local/Render demo use.
- In-memory state is process-local and lost on restart.
- No automated incident acknowledgement/resolution workflow.
- No real vehicle integration, safety certification or validated diagnosis.
- Docker and deployment verification depend on external tooling/accounts; see
  `DEPLOYMENT.md` when it lands in Phase 9.
