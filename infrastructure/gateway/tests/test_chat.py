"""Test suite for Chat endpoint validation and bounds."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from infrastructure.gateway.main import app

client = TestClient(app)

from infrastructure.gateway.config import get_gateway_settings
VALID_TOKEN = get_gateway_settings().inference_gateway_api_key.get_secret_value()
VALID_HEADERS = {"Authorization": f"Bearer {VALID_TOKEN}"}


def test_disallowed_model_rejected() -> None:
    """Requesting an unapproved model (e.g. llama3) must return 422 validation error."""
    payload = {
        "model": "unapproved-model:70b",
        "messages": [{"role": "user", "content": "hello"}],
    }
    resp = client.post("/v1/chat", json=payload, headers=VALID_HEADERS)
    assert resp.status_code == 422
    data = resp.json()
    assert "not in approved allowlist" in data["error"]["message"].lower() or "not_allowed" in data["error"]["code"].lower()


def test_empty_messages_rejected() -> None:
    """Empty messages list must fail Pydantic validation."""
    payload = {
        "model": "qwen3:8b",
        "messages": [],
    }
    resp = client.post("/v1/chat", json=payload, headers=VALID_HEADERS)
    assert resp.status_code == 422


def test_invalid_message_role_rejected() -> None:
    """Invalid role like 'admin' must fail schema validation."""
    payload = {
        "model": "qwen3:8b",
        "messages": [{"role": "admin", "content": "hello"}],
    }
    resp = client.post("/v1/chat", json=payload, headers=VALID_HEADERS)
    assert resp.status_code == 422


def test_excessive_temperature_rejected() -> None:
    """Temperature > 1.0 must fail validation."""
    payload = {
        "model": "qwen3:8b",
        "messages": [{"role": "user", "content": "hello"}],
        "temperature": 1.5,
    }
    resp = client.post("/v1/chat", json=payload, headers=VALID_HEADERS)
    assert resp.status_code == 422
