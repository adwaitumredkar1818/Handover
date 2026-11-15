"""Test suite for Local Inference Gateway authentication."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from infrastructure.gateway.main import app

client = TestClient(app)

from infrastructure.gateway.config import get_gateway_settings
VALID_TOKEN = get_gateway_settings().inference_gateway_api_key.get_secret_value()
VALID_HEADERS = {"Authorization": f"Bearer {VALID_TOKEN}"}


def test_minimal_health_endpoint_is_public() -> None:
    """GET /health should be accessible without credentials and return minimal status."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"status": "ok"}
    # Verify no telemetry leaks
    assert "gpu" not in data
    assert "services" not in data
    assert "host_binding" not in data


def test_detailed_health_requires_auth() -> None:
    """GET /v1/health without auth must fail with 401."""
    resp = client.get("/v1/health")
    assert resp.status_code == 401
    data = resp.json()
    assert data["error"]["code"] == "UNAUTHORIZED"


def test_detailed_health_with_valid_auth_succeeds() -> None:
    """GET /v1/health with valid Bearer token returns full telemetry."""
    resp = client.get("/v1/health", headers=VALID_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "gateway_status" in data
    assert "services" in data
    assert "host_binding" in data


def test_chat_without_auth_fails() -> None:
    """POST /v1/chat without auth header must return 401."""
    payload = {
        "model": "qwen3:8b",
        "messages": [{"role": "user", "content": "ping"}],
    }
    resp = client.post("/v1/chat", json=payload)
    assert resp.status_code == 401
    data = resp.json()
    assert data["error"]["code"] == "UNAUTHORIZED"


def test_chat_with_invalid_token_fails() -> None:
    """POST /v1/chat with invalid token must return 401."""
    payload = {
        "model": "qwen3:8b",
        "messages": [{"role": "user", "content": "ping"}],
    }
    headers = {"Authorization": "Bearer invalid-wrong-secret-token"}
    resp = client.post("/v1/chat", json=payload, headers=headers)
    assert resp.status_code == 401
    data = resp.json()
    assert data["error"]["code"] == "UNAUTHORIZED"


def test_chat_with_malformed_auth_header_fails() -> None:
    """POST /v1/chat with Basic or missing Bearer must return 401."""
    payload = {
        "model": "qwen3:8b",
        "messages": [{"role": "user", "content": "ping"}],
    }
    headers = {"Authorization": f"Basic {VALID_TOKEN}"}
    resp = client.post("/v1/chat", json=payload, headers=headers)
    assert resp.status_code == 401


def test_embed_without_auth_fails() -> None:
    """POST /v1/embed without auth must return 401."""
    payload = {
        "model": "nomic-embed-text",
        "input": ["test query"],
    }
    resp = client.post("/v1/embed", json=payload)
    assert resp.status_code == 401


def test_vector_search_without_auth_fails() -> None:
    """POST /v1/vector/search without auth must return 401."""
    payload = {
        "query_text": "test query",
        "organisation_id": "test-org",
        "project_id": "test-proj",
        "top_k": 5,
    }
    resp = client.post("/v1/vector/search", json=payload)
    assert resp.status_code == 401
