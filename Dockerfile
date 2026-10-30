# syntax=docker/dockerfile:1

# AutoGuard AI runtime image.
# The default LLM provider is `mock`, so the container runs with no API key.
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    AUTOGUARD_ENVIRONMENT=production \
    AUTOGUARD_LOG_FORMAT=json \
    AUTOGUARD_LLM_PROVIDER=mock \
    PORT=8000

WORKDIR /app

# Run as an unprivileged user.
RUN groupadd --system app \
    && useradd --system --gid app --create-home app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY simulator ./simulator

USER app

EXPOSE 8000

# Render (and docker run -e PORT=...) can override the port at runtime.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
