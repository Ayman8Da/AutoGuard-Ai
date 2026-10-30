"""Exception handlers translating domain errors into a single envelope."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.correlation import (
    CORRELATION_HEADER,
    UNBOUND_CORRELATION_ID,
    generate_correlation_id,
    get_correlation_id,
)
from app.core.errors import AppError
from app.core.logging import get_logger
from app.models.common import ErrorDetail, ErrorResponse

logger = get_logger("api.errors")

_HTTP_ERROR_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
}


def _resolve_correlation_id(request: Request) -> str:
    correlation_id = getattr(request.state, "correlation_id", None)
    if correlation_id:
        return correlation_id
    correlation_id = get_correlation_id()
    if correlation_id == UNBOUND_CORRELATION_ID:
        correlation_id = generate_correlation_id()
    return correlation_id


def _render_error(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | list[Any] | None = None,
) -> JSONResponse:
    correlation_id = _resolve_correlation_id(request)
    payload = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            details=details,
            correlation_id=correlation_id,
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
        headers={CORRELATION_HEADER: correlation_id},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register handlers so every failure uses the same JSON envelope."""

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.warning(
            "application_error",
            extra={
                "error_code": exc.code,
                "status_code": exc.status_code,
                "path": request.url.path,
            },
        )
        return _render_error(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = jsonable_encoder(exc.errors())
        logger.info(
            "request_validation_failed",
            extra={"path": request.url.path, "error_count": len(details)},
        )
        return _render_error(
            request,
            status_code=422,
            code="VALIDATION_ERROR",
            message="Request payload validation failed.",
            details=details,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return _render_error(
            request,
            status_code=exc.status_code,
            code=_HTTP_ERROR_CODES.get(exc.status_code, "HTTP_ERROR"),
            message=message,
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled_exception",
            extra={"path": request.url.path, "error_type": type(exc).__name__},
        )
        return _render_error(
            request,
            status_code=500,
            code="INTERNAL_ERROR",
            message="An unexpected error occurred while processing the request.",
        )
