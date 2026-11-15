"""Custom exceptions and sanitized error handling for the Local Inference Gateway."""

from __future__ import annotations

import logging
from typing import Any
from fastapi import Request, status
from fastapi.responses import JSONResponse

logger = logging.getLogger("gateway.exceptions")


class GatewayError(Exception):
    """Base exception for all gateway-specific errors."""

    def __init__(
        self,
        message: str,
        error_code: str = "GATEWAY_ERROR",
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}


class AuthenticationError(GatewayError):
    """Raised when request authorization fails."""

    def __init__(
        self,
        message: str = "Invalid or missing authorization credentials.",
        error_code: str = "UNAUTHORIZED",
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class ServiceUnavailableError(GatewayError):
    """Raised when an upstream local service (Ollama, ChromaDB) is unreachable."""

    def __init__(
        self,
        service: str,
        message: str = "Upstream service unavailable.",
    ) -> None:
        super().__init__(
            message=f"{service.capitalize()} error: {message}",
            error_code=f"{service.upper()}_UNAVAILABLE",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details={"service": service},
        )


class CapacityExceededError(GatewayError):
    """Raised when GPU inference queue is full or concurrency timeout triggers."""

    def __init__(
        self,
        message: str = "Inference capacity busy. Please retry shortly.",
        error_code: str = "GPU_BUSY",
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )


class RateLimitExceededError(GatewayError):
    """Raised when request rate exceeds configured limit."""

    def __init__(
        self,
        retry_after_seconds: int = 60,
        message: str = "Rate limit exceeded. Please retry later.",
        error_code: str = "RATE_LIMIT_EXCEEDED",
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"retry_after": retry_after_seconds},
        )
        self.retry_after_seconds = retry_after_seconds


class ValidationError(GatewayError):
    """Raised when payload bounds, models, or collections violate constraints."""

    def __init__(
        self,
        message: str,
        error_code: str = "VALIDATION_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


async def gateway_error_handler(request: Request, exc: GatewayError) -> JSONResponse:
    """Format sanitized JSON responses for gateway exceptions."""
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    logger.warning("Gateway error [%s]: %s (status %d)", exc.error_code, exc.message, exc.status_code)
    headers: dict[str, str] = {}
    if isinstance(exc, RateLimitExceededError):
        headers["Retry-After"] = str(exc.retry_after_seconds)

    return JSONResponse(
        status_code=exc.status_code,
        headers=headers if headers else None,
        content={
            "error": {
                "code": exc.error_code,
                "message": exc.message,
                "details": exc.details,
                "correlation_id": correlation_id,
            }
        },
    )


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Sanitized fallback for unhandled exceptions."""
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    logger.error("Unhandled gateway error: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred inside the Local Inference Gateway.",
                "correlation_id": correlation_id,
            }
        },
    )
