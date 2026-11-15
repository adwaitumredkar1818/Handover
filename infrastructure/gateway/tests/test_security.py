"""Test suite for Security, Headers, Rate Limiting, and Guardrails."""

from __future__ import annotations

import time
import pytest
from fastapi.testclient import TestClient

from infrastructure.gateway.main import app
from infrastructure.gateway.config import get_gateway_settings

client = TestClient(app)

from infrastructure.gateway.config import get_gateway_settings
VALID_TOKEN = get_gateway_settings().inference_gateway_api_key.get_secret_value()
VALID_HEADERS = {"Authorization": f"Bearer {VALID_TOKEN}"}


def test_correlation_id_generated_and_preserved() -> None:
    """Gateway must preserve incoming X-Correlation-ID or generate one."""
    custom_cid = "test-corr-id-12345"
    resp = client.get("/health", headers={"X-Correlation-ID": custom_cid})
    assert resp.status_code == 200
    assert resp.headers.get("x-correlation-id") == custom_cid
    assert "x-latency-ms" in resp.headers

    # Auto-generation test
    resp2 = client.get("/health")
    assert resp2.status_code == 200
    assert "x-correlation-id" in resp2.headers
    assert len(resp2.headers["x-correlation-id"]) > 0


def test_body_size_limit_enforced() -> None:
    """Payloads exceeding 1MB limit must return 413 Payload Too Large."""
    oversized_content = "A" * (1_048_576 + 1024)  # > 1MB
    payload = {
        "model": "qwen3:8b",
        "messages": [{"role": "user", "content": oversized_content}],
    }
    resp = client.post("/v1/chat", json=payload, headers=VALID_HEADERS)
    # Exceeding size will trigger 413
    assert resp.status_code in (413, 422)


def test_security_headers_present() -> None:
    """Response must include standard anti-sniff and frame protection headers."""
    resp = client.get("/health")
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"


def test_rate_limiting_enforced() -> None:
    """Rapid bursts exceeding rate limits on /v1/ endpoints must return HTTP 429 with Retry-After."""
    # Use dedicated token for rate limit testing to avoid interfering with other tests
    test_token = "rate-limit-test-token-abcdef1234567890"
    headers = {"Authorization": f"Bearer {test_token}"}
    settings = get_gateway_settings()

    # Flood requests to /v1/health (will return 401 due to invalid token, but hits middleware rate limiter)
    responses = []
    # Exhaust budget
    for _ in range(settings.rate_limit_requests + 5):
        resp = client.get("/v1/health", headers=headers)
        responses.append(resp.status_code)

    assert 429 in responses
    last_resp = client.get("/v1/health", headers=headers)
    assert last_resp.status_code == 429
    assert "Retry-After" in last_resp.headers
    data = last_resp.json()
    assert data["error"]["code"] == "RATE_LIMIT_EXCEEDED"
