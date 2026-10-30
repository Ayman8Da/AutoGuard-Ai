# Observability Guide

AutoGuard AI is built so that one correlation ID is enough to reconstruct a request from
HTTP boundary to agent attempt to incident. This guide describes the signals the service
emits and how to use them.

## 1. Signal map

| Signal | Where | Lifetime | Purpose |
| ------ | ----- | -------- | ------- |
| Correlation ID | `X-Correlation-ID` header, logs, reports, executions, incidents | Per request | End-to-end trace |
| Structured JSON logs | stdout | Process/collector | Request and agent event history |
| Agent executions | `DiagnosticReport.agent_executions[]` | Report lifetime | Per-attempt audit trail |
| Monitoring snapshot | `GET /api/v1/monitoring` | Process lifetime | Live counters and rates |
| Incidents | `GET /api/v1/incidents` | Process lifetime | Operational response records |
| Health | `GET /health` | Live | Liveness/readiness probe |

In-memory signals reset when the process restarts. Render's log stream (or any log
collector) is the only durable record in the demo deployment.

## 2. Correlation IDs

- Every request gets an ID. A valid client-supplied `X-Correlation-ID` is reused;
  otherwise one is generated (`CORR-YYYYMMDD-<12 hex>`).
- Client values are allow-listed (`^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$`) to prevent log
  injection. Invalid values are replaced.
- The ID is stored in a `ContextVar`, so it propagates through async agent calls without
  extra parameters.
- The ID is returned on every response, embedded in every error envelope, and copied to
  each `AgentExecution`, `DiagnosticReport` and `Incident`.

Example:

```powershell
$headers = @{ "X-Correlation-ID" = "CORR-20261030-DEMO0001" }
$report = Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/vehicles/telemetry `
  -ContentType "application/json" -InFile payload.json -Headers $headers
$report.correlation_id  # CORR-20261030-DEMO0001
```

## 3. Structured logs

JSON is the default (`AUTOGUARD_LOG_FORMAT=json`). One object per line:

```json
{
  "timestamp": "2026-10-30T11:08:29Z",
  "level": "INFO",
  "logger": "autoguard.orchestration.workflow",
  "message": "workflow_completed",
  "workflow_id": "WF-20261030-A8A1A8F297",
  "diagnostic_id": "DIAG-20261030-67BA72211A",
  "risk_level": "critical",
  "status": "completed",
  "analysis_mode": "deterministic",
  "agent_count": 5,
  "duration_ms": 48.13,
  "correlation_id": "CORR-20261030-297F2EBFC4DA",
  "service": "AutoGuard AI",
  "environment": "production"
}
```

Always present: `timestamp`, `level`, `logger`, `message`, `correlation_id`, `service`,
`environment`.

Key event names:

| Logger | Event | Meaning |
| ------ | ----- | ------- |
| `autoguard.http` | `http_request_completed` | Method, path, status, duration, client |
| `autoguard.orchestration.workflow` | `workflow_started` / `workflow_completed` | Workflow lifecycle (failure is logged by the runner and the monitoring agent) |
| `autoguard.orchestration.runner` | `agent_completed` / `agent_attempt_failed` | Each agent attempt |
| `autoguard.agents.diagnostic` | `llm_narrative_completed` / `llm_narrative_attempt_failed` / `llm_narrative_unavailable` | Provider attempt and fallback |
| `autoguard.incidents.manager` | `incident_created` | Incident raised |
| `autoguard.monitoring.agent` | `workflow_failed` / `monitoring_execution_record_failed` | Failure counter and defensive observer error |
| `autoguard.api.errors` | `application_error` / `unhandled_exception` | Error envelopes |

Logs never contain API keys, raw telemetry payloads or full request bodies.

## 4. Agent execution ledger

Every attempt produces an `AgentExecution`:

```json
{
  "agent_name": "DiagnosticAgent",
  "correlation_id": "CORR-20261030-DEMO0001",
  "workflow_id": "WF-20261030-4C2B...",
  "status": "failed",
  "attempt": 1,
  "started_at": "2026-10-30T11:08:29.001Z",
  "ended_at": "2026-10-30T11:08:29.018Z",
  "execution_time_ms": 17.0,
  "error_type": "TimeoutError",
  "error_message": "provider timed out"
}
```

A successful workflow reports five entries: Orchestrator, Diagnostic, Risk Assessment,
Maintenance and Reporting. Retries appear as additional attempts with increasing `attempt`
numbers. Failed attempts remain in the ledger even when a later attempt succeeds; when the
budget is exhausted no report is produced and an incident is raised instead.

## 5. Monitoring endpoint

`GET /api/v1/monitoring` returns:

| Field group | Fields | Notes |
| ----------- | ------ | ----- |
| Workflows | `workflows_started`, `workflows_completed`, `workflows_degraded`, `workflows_failed`, `workflow_success_rate_percent`, `avg_workflow_duration_ms` | Degraded reports count as successful |
| Agents | `agent_executions_total`, `agent_failures_total`, `agent_retries_total`, `agent_success_rate_percent`, `agents[]` | Retries = attempts beyond the first |
| Per agent | `executions`, `successes`, `failures`, `retries`, `success_rate_percent`, `avg_duration_ms`, `last_execution_at` | Sorted by agent name |
| Context | `uptime_seconds`, `llm_provider`, `diagnostics_stored`, `incidents_total`, `incidents_active` | Process-local |

Rates are percentages rounded to two decimals; zero denominators return `0.0`. The
execution buffer is bounded (`AUTOGUARD_MONITORING_BUFFER_SIZE`, default 5 000) and drops
the oldest observations first.

### Suggested operational thresholds

The demo does not ship an alerting backend. If wired to a real monitor:

| Signal | Warning | Critical |
| ------ | ------- | -------- |
| `workflow_success_rate_percent` | < 95% over 15 min | < 80% over 15 min |
| `agent_failures_total` rate | > 1 per 5 min | > 5 per 5 min |
| `incidents_active` | > 10 | > 50 |
| `/health` non-200 | 2 consecutive checks | 5 consecutive checks |
| LLM degraded share | > 20% over 30 min | > 50% over 30 min |

These are illustrative starting points, not validated SLOs.

## 6. Incidents and runbooks

| Incident | Severity | Runbook |
| -------- | -------- | ------- |
| `CRITICAL_VEHICLE_RISK` | critical | [high-risk-vehicle.md](../runbooks/high-risk-vehicle.md) |
| `AGENT_EXECUTION_FAILED` | high | [agent-failure.md](../runbooks/agent-failure.md) |
| `LLM_PROVIDER_FAILURE` | medium | [llm-provider-failure.md](../runbooks/llm-provider-failure.md) |

Each incident includes the correlation ID, runbook ID/title, and where available the
vehicle, diagnostic and workflow IDs plus structured metadata (risk score, hard override,
finding/DTC codes or agent error details). Incidents are created for completed workflows
too: a critical vehicle is an operational event even when diagnosis succeeded.

Invalid telemetry is **not** an incident. It is rejected with `422` and never enters the
workflow, so malformed client input does not page an operator.

## 7. Debugging a request

1. Capture the `X-Correlation-ID` from the response (or supply your own).
2. Filter logs for that ID:

```powershell
Get-Content service.log | Select-String "CORR-20261030-DEMO0001"
```

3. Fetch the report with `GET /api/v1/diagnostics/{diagnostic_id}` and inspect
   `agent_executions` for failed/retried attempts.
4. Check `GET /api/v1/incidents?vehicle_id=VH-003` for the operational record.
5. Check `GET /api/v1/monitoring` for whether the failure is isolated or systemic.
6. Follow the incident's runbook.

If the request returned `AGENT_EXECUTION_FAILED`, telemetry is still stored; re-drive the
diagnosis, do not fabricate a report.

## 8. Health and readiness

`GET /health` returns status, version, uptime and configuration checks. It is used by
Docker/Render health checks. A failing health check should trigger a restart; logs and
incidents should explain why.

## 9. Privacy and cost

- No real or personal data is processed; telemetry is synthetic.
- Secrets are `SecretStr` and never logged.
- JSON logs are verbose by design; set `AUTOGUARD_LOG_LEVEL=WARNING` to reduce volume in
  production demos.
- LLM calls are optional. With `mock`, there is no external inference cost or network
  dependency.

## 10. Known limitations

- Metrics are process-local and reset on restart; there is no Prometheus/OpenTelemetry
  exporter yet.
- Bounded buffers mean historical queries are limited to the last N observations.
- No distributed tracing backend; correlation IDs are the trace key.
- No alert delivery, dashboards or on-call integration.
- Single-instance only: multiple replicas would produce inconsistent in-memory views.
