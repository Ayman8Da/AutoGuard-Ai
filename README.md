# AutoGuard AI

**Agentic Predictive Maintenance & Intelligent Vehicle Fault Diagnosis**

AutoGuard AI ingests simulated vehicle telemetry, detects abnormal conditions, runs a
supervised multi-agent diagnostic workflow, classifies risk with deterministic rules,
recommends maintenance actions and produces traceable diagnostic reports.

> **Data disclaimer:** all telemetry is synthetic. AutoGuard AI is an engineering
> demonstration of agentic AI, observability and CI/CD — it is **not** a validated
> real-world automotive diagnostic or safety system.

---

## Project status

| Phase | Scope | Status |
| ----- | ----- | ------ |
| 1 | Foundation: config, structured logging, correlation IDs, error contract, health API | **Complete — verified** |
| 2 | Vehicle simulator + telemetry API + repositories | Pending approval |
| 3 | Multi-agent architecture (LangGraph) + LLM provider abstraction | Pending |
| 4 | Monitoring, incidents, runbooks | Pending |
| 5 | Agent Cards & governance documentation | Pending |
| 6 | Full automated test suite (≥80% core coverage) | Pending |
| 7 | GitHub Actions CI | Pending |
| 8 | Docker & local container validation | Pending |
| 9 | Render deployment | Pending |
| 10 | Documentation & final demonstration | Pending |

Phase 1 verification (actual, local): **57 tests passing, 95% branch coverage, `ruff` clean**.

---

## Quickstart (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env          # mock LLM by default: no API key needed
uvicorn app.main:app --reload --port 8000
```

| URL | Purpose |
| --- | ------- |
| http://localhost:8000/health | Health probe |
| http://localhost:8000/docs | Swagger UI |
| http://localhost:8000/redoc | ReDoc |
| http://localhost:8000/openapi.json | OpenAPI schema |

```powershell
# Smoke test
Invoke-RestMethod http://localhost:8000/health
```

No external API key is required. `AUTOGUARD_LLM_PROVIDER=mock` is the default so the
application, agents and test suite run fully offline.

---

## API

### Implemented in Phase 1

| Method | Path | Description |
| ------ | ---- | ----------- |
| `GET` | `/` | Service metadata (not shown in Swagger) |
| `GET` | `/health` | Health probe with uptime, version, configuration checks |
| `GET` | `/docs` | Swagger UI |
| `GET` | `/openapi.json` | OpenAPI 3 schema |

### Planned (subsequent phases)

| Method | Path | Phase |
| ------ | ---- | ----- |
| `POST` | `/api/v1/vehicles/telemetry` | 2–3 |
| `GET` | `/api/v1/vehicles` | 2 |
| `GET` | `/api/v1/diagnostics` | 3 |
| `GET` | `/api/v1/diagnostics/{diagnostic_id}` | 3 |
| `GET` | `/api/v1/monitoring` | 4 |
| `GET` | `/api/v1/incidents` | 4 |

Every response carries an `X-Correlation-ID` header. Errors use one envelope:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request payload validation failed.",
    "details": [{ "loc": ["body", "vehicle_id"], "msg": "Field required", "type": "missing" }],
    "correlation_id": "CORR-20261030-9F1C2A7B44DE"
  }
}
```

---

## Configuration

All variables use the `AUTOGUARD_` prefix and can be set in `.env`.

| Variable | Default | Purpose |
| -------- | ------- | ------- |
| `AUTOGUARD_ENVIRONMENT` | `local` | `local`/`test`/`development`/`staging`/`production` |
| `AUTOGUARD_DEBUG` | `false` | Debug mode (keeps tracebacks; do not use in production) |
| `AUTOGUARD_LOG_LEVEL` | `INFO` | Standard Python log levels |
| `AUTOGUARD_LOG_FORMAT` | `json` | `json` or `console` |
| `AUTOGUARD_CORS_ORIGINS` | *(empty)* | Comma-separated allowed origins |
| `AUTOGUARD_LLM_PROVIDER` | `mock` | `mock`, `groq` or `ollama` |
| `AUTOGUARD_LLM_MODEL` | `llama-3.3-70b-versatile` | Model name for the active provider |
| `AUTOGUARD_GROQ_API_KEY` | *(empty)* | Required only for `groq`; stored as `SecretStr` |
| `AUTOGUARD_OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama endpoint |
| `AUTOGUARD_AGENT_MAX_RETRIES` | `1` | Safe retry budget per agent |

Startup fails fast if `AUTOGUARD_LLM_PROVIDER=groq` is set without an API key. Secrets are
never logged or returned by the API.

---

## Testing & quality

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest --cov=app --cov-report=term-missing
```

---

## Project layout (Phase 1)

```text
AutoGuard-AI/
├── app/
│   ├── main.py                 # App factory, lifespan, middleware wiring
│   ├── api/
│   │   ├── system.py           # / and /health
│   │   ├── exception_handlers.py
│   │   └── v1/router.py        # Versioned router (domain routes land here)
│   ├── core/
│   │   ├── config.py           # Pydantic settings (typed, validated)
│   │   ├── correlation.py      # Correlation ID generation/sanitisation
│   │   ├── errors.py           # Domain error hierarchy
│   │   ├── logging.py          # JSON logging + context filter
│   │   └── middleware.py       # Request tracing
│   ├── models/common.py        # Shared response schemas
│   ├── agents/                 # Phase 3
│   ├── orchestration/          # Phase 3
│   ├── monitoring/             # Phase 4
│   ├── incidents/              # Phase 4
│   ├── services/               # Phase 2+
│   └── utils/
├── tests/
│   ├── unit/
│   └── api/
├── docs/ARCHITECTURE.md
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
├── .env.example
└── README.md
```

Planned additions: `simulator/`, `agent_cards/`, `runbooks/`, `tests/integration/`,
`tests/failure/`, `.github/workflows/`, `Dockerfile`, `docker-compose.yml`,
`DEPLOYMENT.md`.

---

## Engineering decisions (Phase 1)

- **Modular monolith, not microservices.** One FastAPI process keeps the multi-agent
  workflow debuggable while preserving clean package boundaries.
- **Correlation IDs live in a `ContextVar`.** This propagates automatically through async
  agent calls without threading an extra argument through every function.
- **Client-supplied correlation IDs are allow-listed.** Prevents log injection while
  still supporting distributed tracing from a frontend or gateway.
- **One error envelope.** Validation errors, 404s, domain errors and unexpected
  exceptions all return the same shape plus the correlation ID.
- **Structured JSON logs by default.** Log line fields (`correlation_id`, `agent`,
  `duration_ms`, `status`) map directly to the Phase 4 monitoring model.
- **LLM provider is pluggable and `mock`-first.** The full stack is testable without an
  API key; Groq is opt-in via environment configuration.
- **Configuration is validated at startup.** Invalid log levels, API prefixes or a
  missing Groq key fail fast rather than at the first request.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full target architecture.
