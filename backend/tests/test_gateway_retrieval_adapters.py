"""Unit and integration tests for GatewayEmbeddingService and GatewayVectorStore adapters."""

import pytest
from unittest.mock import MagicMock

from app.services.embedding import GatewayEmbeddingService, EmbeddingExecutionError
from app.services.vector_store import (
    GatewayVectorStore,
    VectorStoreError,
    VectorQueryHit,
)


def test_gateway_embedding_service_success():
    mock_client = MagicMock()
    mock_client.embed_texts.return_value = [[0.1] * 768, [0.2] * 768]

    svc = GatewayEmbeddingService(
        gateway_client=mock_client,
        model="nomic-embed-text",
        batch_size=8,
        expected_dimensions=768,
    )

    assert svc.model_name == "nomic-embed-text"
    assert svc.expected_dimensions == 768

    result = svc.embed_documents(["doc1", "doc2"])
    assert len(result) == 2
    assert len(result[0]) == 768
    mock_client.embed_texts.assert_called_once_with(
        model="nomic-embed-text",
        texts=["doc1", "doc2"],
    )


def test_gateway_embedding_service_dimension_mismatch():
    mock_client = MagicMock()
    mock_client.embed_texts.return_value = [[0.1] * 512]  # Wrong dim

    svc = GatewayEmbeddingService(
        gateway_client=mock_client,
        model="nomic-embed-text",
        expected_dimensions=768,
    )

    with pytest.raises(EmbeddingExecutionError) as exc_info:
        svc.embed_documents(["doc1"])
    assert exc_info.value.code == "EMBEDDING_DIMENSION_MISMATCH"


def test_gateway_vector_store_query_success():
    mock_client = MagicMock()
    mock_client.search_vectors.return_value = {
        "hits": [
            {
                "id": "ev1:0",
                "distance": 0.15,
                "similarity": 0.85,
                "metadata": {"chunk_id": "00000000-0000-0000-0000-000000000001"},
            }
        ]
    }

    store = GatewayVectorStore(
        gateway_client=mock_client,
        collection_name="test_col",
        embedding_model="nomic-embed-text",
        expected_dimensions=768,
    )

    hits = store.query_vectors(
        query_embedding=[0.1] * 768,
        top_k=5,
        where={"organisation_id": "org1", "project_id": "proj1"},
    )

    assert len(hits) == 1
    assert hits[0].vector_id == "ev1:0"
    assert hits[0].similarity == 0.85
    mock_client.search_vectors.assert_called_once()


def test_gateway_vector_store_missing_tenant_scope():
    mock_client = MagicMock()
    store = GatewayVectorStore(
        gateway_client=mock_client,
        collection_name="test_col",
    )

    with pytest.raises(VectorStoreError) as exc_info:
        store.query_vectors(
            query_embedding=[0.1] * 768,
            top_k=5,
            where={"some_other_key": "val"},
        )
    assert exc_info.value.code == "TENANT_SCOPE_MISSING"


def test_gateway_vector_store_mutation_forbidden():
    mock_client = MagicMock()
    store = GatewayVectorStore(
        gateway_client=mock_client,
        collection_name="test_col",
    )

    with pytest.raises(VectorStoreError) as exc_info:
        store.ensure_collection()
    assert exc_info.value.code == "CLOUD_MUTATION_FORBIDDEN"

    with pytest.raises(VectorStoreError) as exc_info:
        store.upsert_records([])
    assert exc_info.value.code == "CLOUD_MUTATION_FORBIDDEN"

    with pytest.raises(VectorStoreError) as exc_info:
        store.delete_records()
    assert exc_info.value.code == "CLOUD_MUTATION_FORBIDDEN"


def test_disabled_inference_mode_adapters():
    from app.services.embedding import DisabledEmbeddingService
    from app.services.vector_store import DisabledVectorStore
    from app.services.llm import DisabledLLMClient, LLMGenerationRequest

    disabled_emb = DisabledEmbeddingService()
    with pytest.raises(EmbeddingExecutionError) as exc_emb:
        disabled_emb.embed_documents(["test"])
    assert exc_emb.value.code == "INFERENCE_DISABLED"

    with pytest.raises(EmbeddingExecutionError) as exc_query:
        disabled_emb.embed_query("query")
    assert exc_query.value.code == "INFERENCE_DISABLED"

    disabled_vs = DisabledVectorStore()
    with pytest.raises(VectorStoreError) as exc_vs:
        disabled_vs.query_vectors(query_embedding=[0.1] * 768, top_k=5)
    assert exc_vs.value.code == "INFERENCE_DISABLED"

    disabled_llm = DisabledLLMClient()
    with pytest.raises(Exception) as exc_llm:
        disabled_llm.generate_json(LLMGenerationRequest(system_prompt="s", user_prompt="u"))
    assert getattr(exc_llm.value, "code", "") == "INFERENCE_DISABLED"


def test_deps_resolution_in_cloud_mode(monkeypatch):
    from fastapi import Request
    from app.core.config import Settings
    from app.api.deps import get_embedding_service, get_vector_store_client, get_llm_client
    from app.services.embedding import DisabledEmbeddingService, OllamaEmbeddingService
    from app.services.vector_store import DisabledVectorStore, ChromaV2HttpVectorStore
    from app.services.llm import DisabledLLMClient, OllamaLLMClient

    mock_req = MagicMock(spec=Request)
    mock_req.app.state = MagicMock()
    mock_req.app.state.embedding_service = None
    mock_req.app.state.vector_store_client = None
    mock_req.app.state.llm_client = None
    mock_req.app.state.inference_gateway_client = None
    mock_req.app.state.chroma_collection_name = None

    # Test cloud disabled mode: APP_ENV=production, INFERENCE_GATEWAY_ENABLED=false
    settings_cloud = Settings(
        app_env="production",
        cookie_secure=True,
        cookie_samesite="none",
        inference_gateway_enabled=False,
        database_url="postgresql+psycopg://postgres:secret@localhost:5432/postgres",
        postgres_password="secret",
    )
    assert settings_cloud.resolved_inference_mode == "disabled"

    emb_cloud = get_embedding_service(request=mock_req, settings=settings_cloud, gateway_client=None)
    assert isinstance(emb_cloud, DisabledEmbeddingService)
    assert not isinstance(emb_cloud, OllamaEmbeddingService)

    vs_cloud = get_vector_store_client(request=mock_req, settings=settings_cloud, gateway_client=None)
    assert isinstance(vs_cloud, DisabledVectorStore)
    assert not isinstance(vs_cloud, ChromaV2HttpVectorStore)

    llm_cloud = get_llm_client(request=mock_req, settings=settings_cloud, gateway_client=None)
    assert isinstance(llm_cloud, DisabledLLMClient)
    assert not isinstance(llm_cloud, OllamaLLMClient)

    # Test local mode: APP_ENV=development, INFERENCE_GATEWAY_ENABLED=false
    settings_local = Settings(
        app_env="development",
        inference_gateway_enabled=False,
        database_url="postgresql+psycopg://postgres:secret@localhost:5432/postgres",
        postgres_password="secret",
    )
    assert settings_local.resolved_inference_mode == "local"

    emb_local = get_embedding_service(request=mock_req, settings=settings_local, gateway_client=None)
    assert isinstance(emb_local, OllamaEmbeddingService)

    vs_local = get_vector_store_client(request=mock_req, settings=settings_local, gateway_client=None)
    assert isinstance(vs_local, ChromaV2HttpVectorStore)

    llm_local = get_llm_client(request=mock_req, settings=settings_local, gateway_client=None)
    assert isinstance(llm_local, OllamaLLMClient)

