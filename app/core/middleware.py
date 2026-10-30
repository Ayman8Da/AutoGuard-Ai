"""HTTP middleware: correlation ID propagation and request logging."""

from __future__ import annotations

import time
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.correlation import (
    CORRELATION_HEADER,
    bind_correlation_id,
    generate_correlation_id,
    reset_correlation_id,
    sanitize_correlation_id,
)
from app.core.errors import AppError
from app.core.logging import get_logger
from app.models.common import ErrorDetail, ErrorResponse

logger = get_logger("http")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach a correlation ID to every request, response and log record.

    A client-supplied ``X-Correlation-ID`` is reused when it matches a strict
    allow-list; otherwise a new ID is generated. Unhandled exceptions are
    converted into a safe error envelope (except in debug mode, where the
    traceback is preserved for local troubleshooting).
    """

    def __init__(self, app: Any, *, catch_unhandled: bool = True) -> None:
        super().__init__(app)
        self._catch_unhandled = catch_unhandled

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        provided = request.headers.get(CORRELATION_HEADER)
        correlation_id = sanitize_correlation_id(provided) or generate_correlation_id()

        if provided and correlation_id != provided.strip():
            safe_hint = "".join(ch for ch in provided if ch.isalnum() or ch in "._:-")[:64]
            logger.warning(
                "invalid_correlation_id_ignored",
                extra={"provided_correlation_id": safe_hint, "path": request.url.path},
            )

        token = bind_correlation_id(correlation_id)
        request.state.correlation_id = correlation_id
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.exception(
                "http_request_failed",
                extra={
                    "http_method": request.method,
                    "path": request.url.path,
                    "duration_ms": elapsed_ms,
                },
            )
            if not self._catch_unhandled:
                raise
            return self._internal_error_response(correlation_id)
        else:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.info(
                "http_request_completed",
                extra={
                    "http_method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": elapsed_ms,
                    "client": request.client.host if request.client else None,
                },
            )
            response.headers[CORRELATION_HEADER] = correlation_id
            return response
        finally:
            reset_correlation_id(token)

    @staticmethod
    def _internal_error_response(correlation_id: str) -> JSONResponse:
        payload = ErrorResponse(
            error=ErrorDetail(
                code=AppError.code,
                message="An unexpected error occurred while processing the request.",
                details=None,
                correlation_id=correlation_id,
            )
        )
        return JSONResponse(
            status_code=500,
            content=payload.model_dump(mode="json"),
            headers={CORRELATION_HEADER: correlation_id},
        )
