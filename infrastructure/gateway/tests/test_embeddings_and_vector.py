"""Test suite for Embedding and Multi-Tenant Vector Search validation."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from infrastructure.gateway.main import app

client = TestClient(app)

from infrastructure.gateway.config import get_gateway_settings
VALID_TOKEN = get_gateway_settings().inference_gateway_api_key.get_secret_value()
VALID_HEADERS = {"Authorization": f"Bearer {VALID_TOKEN}"}


def test_embed_disallowed_model_rejected() -> None:
    """Requesting unapproved embedding model must return 422."""
    payload = {
        "model": "unapproved-embedder",
        "input": ["test sentence"],
    }
    resp = client.post("/v1/embed", json=payload, headers=VALID_HEADERS)
    assert resp.status_code == 422
    data = resp.json()
    assert "not in approved allowlist" in data["error"]["message"].lower() or "not_allowed" in data["error"]["code"].lower()


def test_embed_oversized_batch_rejected() -> None:
    """Input batch > 16 must fail schema validation."""
    payload = {
        "model": "nomic-embed-text",
        "input": [f"test sentence {i}" for i in range(25)],
    }
    resp = client.post("/v1/embed", json=payload, headers=VALID_HEADERS)
    assert resp.status_code == 422


def test_vector_search_missing_tenant_scope_fails() -> None:
    """Vector search without organisation_id and project_id must return 422 TENANT_SCOPE_REQUIRED."""
    payload = {
        "query_embedding": [0.1] * 768,
        "top_k": 5,
    }
    resp = client.post("/v1/vector/search", json=payload, headers=VALID_HEADERS)
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "TENANT_SCOPE_REQUIRED"


def test_vector_search_missing_project_id_fails() -> None:
    """Vector search with only organisation_id must fail closed."""
    payload = {
        "organisation_id": "test-org-1",
        "query_embedding": [0.1] * 768,
        "top_k": 5,
    }
    resp = client.post("/v1/vector/search", json=payload, headers=VALID_HEADERS)
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "TENANT_SCOPE_REQUIRED"


def test_vector_search_disallowed_collection_rejected() -> None:
    """Querying unapproved Chroma collection must return 422."""
    payload = {
        "collection_name": "malicious_unapproved_collection",
        "organisation_id": "test-org-1",
        "project_id": "test-proj-1",
        "query_embedding": [0.1] * 768,
        "top_k": 5,
    }
    resp = client.post("/v1/vector/search", json=payload, headers=VALID_HEADERS)
    assert resp.status_code == 422
    data = resp.json()
    assert "not in the allowed collections" in data["error"]["message"].lower() or "validation_error" in data["error"]["code"].lower()


def test_vector_search_invalid_embedding_dimension() -> None:
    """Querying with wrong vector dimension (e.g. 512 instead of 768) must return 422."""
    payload = {
        "collection_name": "ipkrh_evidence_chunks_nomic-embed-text_v1",
        "organisation_id": "test-org-1",
        "project_id": "test-proj-1",
        "query_embedding": [0.1] * 512,
        "top_k": 5,
    }
    resp = client.post("/v1/vector/search", json=payload, headers=VALID_HEADERS)
    assert resp.status_code == 422
    data = resp.json()
    assert "dimension mismatch" in data["error"]["message"].lower()


def test_vector_search_top_k_bounds() -> None:
    """top_k > 50 must fail schema validation."""
    payload = {
        "organisation_id": "test-org-1",
        "project_id": "test-proj-1",
        "query_embedding": [0.1] * 768,
        "top_k": 100,
    }
    resp = client.post("/v1/vector/search", json=payload, headers=VALID_HEADERS)
    assert resp.status_code == 422
