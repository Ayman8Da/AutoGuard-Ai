# Deployment Guide

Status: **prepared, not deployed.** This workspace has no Render account, no GitHub
remote and no Docker installation. Nothing in this document should be read as evidence
that a deployment succeeded.

The application is a single Docker web service. It needs no database or external API key
when `AUTOGUARD_LLM_PROVIDER=mock` (the default).

## 1. Preconditions

- A GitHub repository containing this project.
- A Render account (free plan is sufficient for the demo).
- Optional: a Groq API key, only if you switch the provider to `groq`.
- Local verification (recommended):

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest --cov=app --cov=simulator --cov-fail-under=80
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

If Docker is available:

```powershell
docker build -t autoguard-ai .
docker run --rm -p 8000:8000 autoguard-ai
Invoke-RestMethod http://localhost:8000/health
```

## 2. Render Blueprint (recommended)

1. Push the repository to GitHub.
2. In Render, choose **New → Blueprint** and select the repository.
3. Render reads [`render.yaml`](render.yaml) and proposes the `autoguard-ai` web service.
4. Leave `AUTOGUARD_LLM_PROVIDER=mock` for a key-free demo, or set it to `groq` and add
   `AUTOGUARD_GROQ_API_KEY` as a secret in the dashboard.
5. Apply the Blueprint and wait for the first deploy.

Render injects `PORT`; the image's `CMD` binds uvicorn to `${PORT:-8000}`. Health checks
poll `GET /health`.

## 3. Manual Docker service (alternative)

1. **New → Web Service** → connect the repository.
2. Runtime: **Docker**. Dockerfile path: `./Dockerfile`. Context: `.`.
3. Health check path: `/health`.
4. Add the environment variables from `render.yaml` manually.
5. Deploy.

## 4. Environment variables

| Variable | Render value | Notes |
| -------- | ------------ | ----- |
| `AUTOGUARD_ENVIRONMENT` | `production` | Enables production semantics and JSON logs |
| `AUTOGUARD_LOG_LEVEL` | `INFO` | Use `WARNING` to reduce log volume |
| `AUTOGUARD_LOG_FORMAT` | `json` | Required for log aggregation |
| `AUTOGUARD_LLM_PROVIDER` | `mock` / `groq` / `ollama` | `mock` needs no key |
| `AUTOGUARD_LLM_MODEL` | `llama-3.3-70b-versatile` | Provider-specific model name |
| `AUTOGUARD_LLM_TIMEOUT_SECONDS` | `30` | Provider call timeout |
| `AUTOGUARD_AGENT_MAX_RETRIES` | `1` | Bounded retry budget (0–3) |
| `AUTOGUARD_GROQ_API_KEY` | *(secret)* | Required only for `groq`; set in dashboard |
| `AUTOGUARD_CORS_ORIGINS` | *(empty)* | Comma-separated origins if a UI is added |
| `AUTOGUARD_TELEMETRY_BUFFER_SIZE` | `1000` | In-memory records |
| `AUTOGUARD_DIAGNOSTICS_BUFFER_SIZE` | `500` | In-memory reports |
| `AUTOGUARD_INCIDENT_BUFFER_SIZE` | `500` | In-memory incidents |
| `AUTOGUARD_MONITORING_BUFFER_SIZE` | `5000` | In-memory execution observations |

Never commit a real `.env` or API key. `AUTOGUARD_GROQ_API_KEY` is stored as `SecretStr`
and is excluded from logs and API responses.

## 5. Post-deploy verification

Replace `<host>` with the Render URL.

```powershell
# 1. Health and configuration
Invoke-RestMethod https://<host>/health

# 2. Swagger / OpenAPI
Invoke-WebRequest -UseBasicParsing https://<host>/openapi.json

# 3. Ingest a critical frame and assert deterministic risk
python -m simulator.vehicle_simulator --scenario critical --vehicle VH-003 --pretty > payload.json
$report = Invoke-RestMethod -Method Post `
  -Uri https://<host>/api/v1/vehicles/telemetry `
  -ContentType "application/json" -InFile payload.json `
  -Headers @{ "X-Correlation-ID" = "CORR-20261030-DEPLOYCHECK" }
$report.risk.level          # expected: critical
$report.risk.hard_override  # expected: True
$report.agent_executions.Count  # expected: 5

# 4. Monitoring and incidents
Invoke-RestMethod https://<host>/api/v1/monitoring
Invoke-RestMethod https://<host>/api/v1/incidents?severity=critical

# 5. Report detail
Invoke-RestMethod https://<host>/api/v1/diagnostics/$($report.diagnostic_id)
```

Expected observations:

- `X-Correlation-ID` echoes `CORR-20261030-DEPLOYCHECK` on every response.
- `workflows_started` and `workflows_completed` increase by one.
- One `CRITICAL_VEHICLE_RISK` incident references the `high_risk_vehicle` runbook.
- The report's `maintenance.repair_performed` is `false`.

Record the deployed commit SHA, host, timestamp and the outputs above. Do not mark the
deployment verified without them.

## 6. Operations

- **Logs:** Render log stream; JSON fields include `correlation_id`, `agent`,
  `workflow_id`, `duration_ms` and `status_code`.
- **Health:** `/health` is the Render health check; a failing health check triggers a
  restart.
- **Scaling:** run **one** instance. All state is process-local; multiple instances would
  show inconsistent monitoring and incident lists.
- **Restart:** clears telemetry, reports, incidents and monitoring counters. This is
  expected for the demo.
- **Rollback:** redeploy a previous commit from the Render dashboard.
- **Incidents:** `/api/v1/incidents` is read-only; the demo has no acknowledge/resolve
  action. Follow the runbook referenced by the incident.

## 7. Smoke-test limitations

- All telemetry is synthetic; no real vehicle data is processed.
- No authentication or multi-tenancy. Treat the URL as a public demo, not a production
  automotive service.
- Free Render instances may sleep; the first request after idle is slower.
- LLM narration is optional. If `groq` is selected and the key/quota fails, reports degrade
  to `degraded_deterministic` and a `LLM_PROVIDER_FAILURE` incident is raised; safety
  output is unchanged.

## 8. What has and has not been verified

| Item | Status |
| ---- | ------ |
| Local lint, tests and coverage | **Verified** on Windows/Python 3.14 |
| Local live API run (uvicorn) | **Verified** on port 8777 |
| Docker image build/run | **Not verified** — Docker is not installed here |
| GitHub Actions execution | **Not verified** — no remote/`gh` CLI here |
| Render deployment | **Not performed** — no Render account/credentials here |

Update this table only with real evidence.
