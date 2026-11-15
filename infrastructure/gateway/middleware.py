"""Middleware for request correlation, body size bounding, rate limiting, and security headers."""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from threading import Lock

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("infrastructure.gateway")


class SecurityAndCorrelationMiddleware(BaseHTTPMiddleware):
    """Enforces request correlation IDs, security headers, rate limiting, and body size limits."""

    def __init__(
        self,
        app,
        max_body_bytes: int = 1_048_576,
        rate_limit_requests: int = 60,
        rate_limit_window_seconds: float = 60.0,
    ) -> None:
        super().__init__(app)
        self.max_body_bytes = max_body_bytes
        self.rate_limit_requests = rate_limit_requests
        self.rate_limit_window_seconds = rate_limit_window_seconds

        # Bounded in-memory sliding window rate limiter
        self._rate_limit_lock = Lock()
        self._request_timestamps: dict[str, deque[float]] = defaultdict(deque)
        self._last_cleanup = time.monotonic()
        self._max_tracked_clients = 1000

    def _check_rate_limit(self, client_key: str) -> tuple[bool, int]:
        """Check sliding window rate limit for given client key. Return (allowed, retry_after)."""
        now = time.monotonic()
        with self._rate_limit_lock:
            # Periodic cleanup of idle clients to prevent unbounded memory growth
            if now - self._last_cleanup > 300.0:
                expired_keys = [
                    k for k, timestamps in self._request_timestamps.items()
                    if not timestamps or (now - timestamps[-1]) > self.rate_limit_window_seconds
                ]
                for k in expired_keys:
                    del self._request_timestamps[k]
                self._last_cleanup = now

            timestamps = self._request_timestamps[client_key]
            # Evict timestamps outside sliding window
            cutoff = now - self.rate_limit_window_seconds
            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()

            if len(timestamps) >= self.rate_limit_requests:
                earliest = timestamps[0]
                retry_after = max(1, int(self.rate_limit_window_seconds - (now - earliest)))
                return False, retry_after

            # Enforce max tracked clients limit to protect process memory
            if len(self._request_timestamps) > self._max_tracked_clients and client_key not in self._request_timestamps:
                # Evict oldest entry
                oldest_k = next(iter(self._request_timestamps))
                del self._request_timestamps[oldest_k]

            timestamps.append(now)
            return True, 0

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 1. Correlation ID
        correlation_id = (
            request.headers.get("X-Correlation-ID")
            or request.headers.get("X-Request-ID")
            or str(uuid.uuid4())
        )
        request.state.correlation_id = correlation_id

        # 2. Body size check via Content-Length header if present
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit():
            if int(content_length) > self.max_body_bytes:
                return JSONResponse(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    content={
                        "error": {
                            "code": "REQUEST_ENTITY_TOO_LARGE",
                            "message": f"Request body exceeds maximum size of {self.max_body_bytes} bytes.",
                            "correlation_id": correlation_id,
                        }
                    },
                )

        # 3. Rate limiting for API endpoints (exempting minimal /health)
        if request.url.path.startswith("/v1/"):
            # Identity key: hash of authorization header or loopback client IP
            auth_header = request.headers.get("Authorization", "").strip()
            if auth_header:
                import hashlib
                client_key = "tok:" + hashlib.sha256(auth_header.encode()).hexdigest()[:16]
            else:
                client_ip = request.client.host if request.client else "127.0.0.1"
                client_key = f"ip:{client_ip}"

            allowed, retry_after = self._check_rate_limit(client_key)
            if not allowed:
                logger.warning("Rate limit exceeded for %s [cid: %s]", client_key, correlation_id)
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    headers={"Retry-After": str(retry_after)},
                    content={
                        "error": {
                            "code": "RATE_LIMIT_EXCEEDED",
                            "message": f"Rate limit exceeded. Maximum {self.rate_limit_requests} requests per {int(self.rate_limit_window_seconds)}s window.",
                            "details": {"retry_after": retry_after},
                            "correlation_id": correlation_id,
                        }
                    },
                )

        start_time = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        # Standard tracing & latency headers
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Gateway-Latency-Ms"] = str(duration_ms)
        response.headers["X-Latency-Ms"] = str(duration_ms)

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Audit log (zero sensitive payloads)
        logger.info(
            "%s %s -> %s (%.2f ms) [cid: %s]",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            correlation_id,
        )
        return response
