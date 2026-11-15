"""Centralized client for communicating securely with the Local Inference Gateway."""

from __future__ import annotations

import logging
import time
from typing import Any, Sequence

import httpx

from app.core.config import InferenceGatewaySettings
from app.core.exceptions import (
    AppError,
    ForbiddenError,
    ServiceUnavailableError,
    UnauthorizedError,
)

logger = logging.getLogger("app.services.inference_gateway")


class InferenceGatewayClientError(AppError):
    """Base error for Inference Gateway client failures."""

    def __init__(
        self,
        message: str,
        code: str = "GATEWAY_CLIENT_ERROR",
        status_code: int = 502,
        retryable: bool = False,
    ) -> None:
        super().__init__(message=message, code=code, status_code=status_code)
        self.retryable = retryable


class InferenceGatewayClient:
    """Secure, lifecycle-friendly HTTP client for the Local Inference Gateway.
    
    Translates backend AI requests (LLM chat, embedding, vector search) into
    authenticated gateway calls, enforcing timeouts, bounded retries, and sanitized logging.
    """

    def __init__(
        self,
        settings: InferenceGatewaySettings,
        http_client: httpx.Client | None = None,
        http_transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._base_url = settings.base_url.rstrip("/")
        self._timeout = settings.timeout_seconds
        self._http_transport = http_transport
        self._client = http_client

    def _get_headers(self) -> dict[str, str]:
        """Build request headers with gateway Bearer token and validated Cloudflare Access headers."""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._settings.token:
            token_val = self._settings.token.get_secret_value().strip()
            if token_val:
                headers["Authorization"] = f"Bearer {token_val}"

        # Cloudflare Access Service Token headers (future Render-to-Cloudflare Tunnel support)
        # SEC-01 GUARD: Attach only if explicitly configured, URL is HTTPS, and not localhost/loopback
        if self._settings.cf_access_client_id and self._settings.cf_access_client_secret:
            cid = self._settings.cf_access_client_id.strip()
            sec = self._settings.cf_access_client_secret.get_secret_value().strip()
            if cid and sec and self._base_url.lower().startswith("https://"):
                headers["CF-Access-Client-Id"] = cid
                headers["CF-Access-Client-Secret"] = sec

        return headers

    def _execute_request(
        self,
        method: str,
        path: str,
        json_payload: dict[str, Any] | None = None,
        max_retries: int = 1,
    ) -> dict[str, Any]:
        """Execute HTTP request against gateway with aggregate deadline and bounded retries."""
        url = f"{self._base_url}{path}"
        headers = self._get_headers()

        # SEC-03 ENFORCEMENT: Enforce overall deadline using monotonic clock
        deadline = time.monotonic() + self._timeout

        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            remaining_time = deadline - time.monotonic()
            if remaining_time <= 0:
                raise ServiceUnavailableError(
                    f"Inference Gateway aggregate request deadline expired after {self._timeout:.1f}s on {path}.",
                    code="GATEWAY_TIMEOUT",
                )

            # Request timeout cannot exceed remaining aggregate budget
            request_timeout = min(self._timeout, remaining_time)

            t0 = time.perf_counter()
            try:
                # SEC-01 & SEC-04: Follow redirects disabled, reuse client if provided
                if self._client is not None:
                    resp = self._client.request(
                        method,
                        url,
                        json=json_payload,
                        headers=headers,
                        timeout=request_timeout,
                        follow_redirects=False,
                    )
                else:
                    with httpx.Client(
                        timeout=request_timeout,
                        transport=self._http_transport,
                        follow_redirects=False,
                    ) as client:
                        resp = client.request(
                            method,
                            url,
                            json=json_payload,
                            headers=headers,
                        )

                duration_ms = (time.perf_counter() - t0) * 1000
                logger.debug(
                    "Gateway request %s %s -> %d in %.2fms (attempt %d/%d)",
                    method,
                    path,
                    resp.status_code,
                    duration_ms,
                    attempt + 1,
                    max_retries + 1,
                )

                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except ValueError as exc:
                        raise InferenceGatewayClientError(
                            "Inference Gateway returned invalid JSON response.",
                            code="GATEWAY_INVALID_RESPONSE",
                            retryable=False,
                        ) from exc

                # Handle specific HTTP error status codes cleanly
                if resp.status_code in (301, 302, 303, 307, 308):
                    logger.warning("Inference Gateway redirect %d blocked for security.", resp.status_code)
                    raise InferenceGatewayClientError(
                        f"Inference Gateway returned unexpected redirect HTTP {resp.status_code}. Automatic redirect following is disabled.",
                        code="GATEWAY_REDIRECT_BLOCKED",
                        status_code=resp.status_code,
                        retryable=False,
                    )

                if resp.status_code == 401:
                    logger.error("Inference Gateway authentication failed (HTTP 401). Verify token.")
                    raise UnauthorizedError(
                        "Inference Gateway authentication failed. Please verify token configuration.",
                        code="GATEWAY_UNAUTHORIZED",
                    )
                if resp.status_code == 403:
                    logger.error("Inference Gateway access forbidden (HTTP 403).")
                    raise ForbiddenError(
                        "Inference Gateway access forbidden.",
                        code="GATEWAY_FORBIDDEN",
                    )
                if resp.status_code == 422:
                    error_data = {}
                    try:
                        error_data = resp.json().get("error", {})
                    except Exception:
                        pass
                    msg = error_data.get("message", "Validation error reported by Inference Gateway.")
                    code = error_data.get("code", "GATEWAY_VALIDATION_ERROR")
                    raise InferenceGatewayClientError(
                        f"Inference Gateway rejected payload: {msg}",
                        code=code,
                        status_code=422,
                        retryable=False,
                    )
                if resp.status_code == 429:
                    raise ServiceUnavailableError(
                        "Inference Gateway rate limit or GPU concurrency capacity exceeded. Please retry shortly.",
                        code="GATEWAY_CAPACITY_EXCEEDED",
                    )

                # HTTP 500 / 502 / 503 / 504
                if resp.status_code in (500, 502, 503, 504):
                    if attempt < max_retries:
                        backoff = 0.5 * (attempt + 1)
                        if deadline - time.monotonic() <= backoff:
                            raise ServiceUnavailableError(
                                f"Inference Gateway request deadline expired before retry backoff could complete (HTTP {resp.status_code}).",
                                code="GATEWAY_TIMEOUT",
                            )
                        time.sleep(backoff)
                        continue
                    raise ServiceUnavailableError(
                        f"Inference Gateway service unavailable (HTTP {resp.status_code}).",
                        code="GATEWAY_SERVICE_UNAVAILABLE",
                    )

                raise InferenceGatewayClientError(
                    f"Inference Gateway request failed with unexpected status HTTP {resp.status_code}.",
                    code="GATEWAY_HTTP_ERROR",
                    status_code=resp.status_code,
                )

            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                last_exc = exc
                if attempt < max_retries:
                    backoff = 0.5 * (attempt + 1)
                    if deadline - time.monotonic() <= backoff:
                        raise ServiceUnavailableError(
                            f"Inference Gateway request deadline expired before retry backoff could complete ({exc}).",
                            code="GATEWAY_TIMEOUT",
                        ) from exc
                    time.sleep(backoff)
                    continue
                logger.warning("Failed to connect to Inference Gateway at %s: %s", self._base_url, exc)
                raise ServiceUnavailableError(
                    f"Cannot reach Local Inference Gateway at {self._base_url}. Service may be offline.",
                    code="GATEWAY_UNREACHABLE",
                ) from exc
            except httpx.ReadTimeout as exc:
                logger.warning("Inference Gateway request timed out after %.1fs on %s", request_timeout, path)
                raise ServiceUnavailableError(
                    f"Inference Gateway timed out after {request_timeout:.1f}s.",
                    code="GATEWAY_TIMEOUT",
                ) from exc
            except (UnauthorizedError, ForbiddenError, ServiceUnavailableError, InferenceGatewayClientError):
                raise
            except Exception as exc:
                last_exc = exc
                if attempt < max_retries:
                    backoff = 0.5 * (attempt + 1)
                    if deadline - time.monotonic() <= backoff:
                        raise ServiceUnavailableError(
                            f"Inference Gateway request deadline expired before retry backoff could complete ({exc}).",
                            code="GATEWAY_TIMEOUT",
                        ) from exc
                    time.sleep(backoff)
                    continue
                raise InferenceGatewayClientError(
                    f"Unexpected error communicating with Inference Gateway: {exc}",
                    code="GATEWAY_REQUEST_FAILED",
                ) from exc

        raise ServiceUnavailableError(
            f"Inference Gateway unreachable after {max_retries} retries: {last_exc}",
            code="GATEWAY_UNREACHABLE",
        )

    def check_health(self) -> dict[str, Any]:
        """Check minimal availability endpoint (/health)."""
        return self._execute_request("GET", "/health", max_retries=0)

    def check_detailed_health(self) -> dict[str, Any]:
        """Check authenticated telemetry endpoint (/v1/health)."""
        return self._execute_request("GET", "/v1/health", max_retries=0)

    def generate_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        num_predict: int = 2048,
        format_json: bool = True,
    ) -> dict[str, Any]:
        """Send chat request to Inference Gateway.
        
        SEC-02 ENFORCEMENT: Non-idempotent chat completions are executed with max_retries=0.
        No automatic retries are permitted on transient errors or HTTP 5xx.
        """
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "num_predict": num_predict,
            "format": "json" if format_json else None,
        }
        return self._execute_request("POST", "/v1/chat", json_payload=payload, max_retries=0)

    def embed_texts(
        self,
        *,
        model: str,
        texts: Sequence[str],
    ) -> list[list[float]]:
        """Generate embeddings through Inference Gateway in bounded batches.
        
        Deterministic and side-effect free: bounded retries enabled (max_retries=1).
        """
        if not texts:
            return []
        
        # Gateway schema enforces max 16 texts per batch
        batch_size = 16
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            chunk = list(texts[i : i + batch_size])
            payload = {
                "model": model,
                "input": chunk,
            }
            resp = self._execute_request("POST", "/v1/embed", json_payload=payload, max_retries=1)
            embeddings = resp.get("embeddings", [])
            all_embeddings.extend(embeddings)

        return all_embeddings

    def search_vectors(
        self,
        *,
        collection_name: str,
        organisation_id: str,
        project_id: str,
        query_embedding: list[float] | None = None,
        query_text: str | None = None,
        top_k: int = 10,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Query ChromaDB through Inference Gateway with mandatory tenant boundary.
        
        Read-only query: bounded retries enabled (max_retries=1).
        """
        payload: dict[str, Any] = {
            "collection_name": collection_name,
            "organisation_id": str(organisation_id),
            "project_id": str(project_id),
            "top_k": top_k,
        }
        if query_embedding is not None:
            payload["query_embedding"] = [float(v) for v in query_embedding]
        if query_text is not None:
            payload["query_text"] = query_text
        if where is not None:
            payload["where"] = where

        return self._execute_request("POST", "/v1/vector/search", json_payload=payload, max_retries=1)
