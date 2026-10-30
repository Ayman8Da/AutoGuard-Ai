# Runbook — Agent Execution Failure

| Field | Value |
| ----- | ----- |
| Runbook ID | `agent_failure` |
| Incident | `AGENT_EXECUTION_FAILED` |
| Severity | high |
| Owner | Platform Engineering |
| Applies to | A workflow that aborted after exhausting the retry budget |

## Trigger

An agent raised on every allowed attempt (`AUTOGUARD_AGENT_MAX_RETRIES + 1`, default 2).
The API returns HTTP 500 with `AGENT_EXECUTION_FAILED`; no diagnostic report is created.
Telemetry is stored, so the frame remains auditable.

## Immediate actions

1. **Correlate the failure.** Use the correlation ID and workflow ID to collect logs for
   every attempt. Look for `agent_attempt_failed` with `agent`, `attempt`, `error_type`.
2. **Check recent changes.** Compare the deployment version, rule/threshold edits and
   dependency changes with the first failure time. Roll back if a regression is suspected.
3. **Reproduce safely.** Replay the stored telemetry against a non-production instance and
   inspect the failing agent's input/output. Do not replay against production while the
   cause is unknown.
4. **Re-drive diagnosis** after the fix. A new workflow ID and completed report must be
   produced.

## Triage queries

```powershell
Invoke-RestMethod "https://<host>/api/v1/incidents?severity=high&status=open"
Invoke-RestMethod "https://<host>/api/v1/monitoring"
# Inspect the agent's failure rate and last execution
(Invoke-RestMethod "https://<host>/api/v1/monitoring").agents |
  Where-Object agent_name -eq "DiagnosticAgent"
```

Log filter examples: `workflow_failed`, `agent_attempt_failed`,
`agent_execution_observer_failed` (the last is monitoring-only and does **not** fail a
diagnosis).

## Do not

- Do not fabricate or hand-edit a report.
- Do not increase the retry budget as a permanent fix; it is bounded for safety.
- Do not disable the incident path to make the monitoring counters look green.

## Escalation

- If the failure is reproducible with the `mock` provider and no recent change: escalate
  to Platform Engineering immediately.
- If telemetry is implicated, involve Vehicle Diagnostics.
- If only one vehicle/scenario fails, capture the exact payload as a regression fixture.

## Verification / closure

The monitoring endpoint shows the agent's failure rate returning to zero, and a replayed
frame produces a completed report with five successful executions. Record the new
`workflow_id` and `diagnostic_id`.
