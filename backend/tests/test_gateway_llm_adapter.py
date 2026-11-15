"""Tests for GatewayLLMClient adapter and dependency injection integration (Phase M3.3.5)."""

from __future__ import annotations

import time
import uuid
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from pydantic import SecretStr

from app.api.deps import get_llm_client
from app.core.config import Settings
from app.models.enums import AssistantAnswerStatus
from app.schemas.assistant import AssistantAnswerPayload
from app.services.assistant_llm import AssistantLLMReasoner
from app.services.inference_gateway import (
    InferenceGatewayClient,
    InferenceGatewayClientError,
    InferenceGatewaySettings,
)
from app.services.llm import (
    GatewayLLMClient,
    LLMExecutionError,
    LLMGenerationRequest,
    LLMGenerationResult,
    OllamaLLMClient,
    StructuredLLMClient,
)


def _make_dummy_request(system_prompt: str = "sys", user_prompt: str = "usr") -> LLMGenerationRequest:
    return LLMGenerationRequest(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        num_ctx=4096,
        num_predict=1024,
        temperature=0.1,
    )


# ---------------------------------------------------------------------------
# Test 1 & 2: Dependency Injection Mode Selection
# ---------------------------------------------------------------------------

def test_1_local_mode_returns_ollama_llm_client() -> None:
    """When gateway is disabled, get_llm_client returns OllamaLLMClient."""
    settings = Settings(
        inference_gateway_enabled=False,
        jwt_secret_key=SecretStr("test-secret-at-least-32-chars-long-xxx"),
        file_encryption_key=SecretStr("fernet-key-min-32-chars-length!!"),
        token_encryption_key=SecretStr("token-key-min-32-chars-length!!"),
    )
    req = MagicMock()
    req.app.state = MagicMock(spec=[])  # No state overrides
    client = get_llm_client(request=req, settings=settings, gateway_client=None)
    assert isinstance(client, OllamaLLMClient)
    assert isinstance(client, StructuredLLMClient)
    assert client.model_name == settings.ollama.llm_model


def test_2_gateway_mode_returns_gateway_llm_client() -> None:
    """When gateway is enabled, get_llm_client returns GatewayLLMClient wrapping InferenceGatewayClient."""
    settings = Settings(
        inference_gateway_enabled=True,
        inference_gateway_base_url="http://127.0.0.1:8002",
        inference_gateway_token=SecretStr("test-gateway-token-min-32-chars"),
        jwt_secret_key=SecretStr("test-secret-at-least-32-chars-long-xxx"),
        file_encryption_key=SecretStr("fernet-key-min-32-chars-length!!"),
        token_encryption_key=SecretStr("token-key-min-32-chars-length!!"),
    )
    gw_settings = InferenceGatewaySettings(
        enabled=True,
        base_url="http://127.0.0.1:8002",
        token=SecretStr("test-gateway-token-min-32-chars"),
    )
    gw_client = InferenceGatewayClient(settings=gw_settings)
    req = MagicMock()
    req.app.state = MagicMock(spec=[])
    client = get_llm_client(request=req, settings=settings, gateway_client=gw_client)
    assert isinstance(client, GatewayLLMClient)
    assert isinstance(client, StructuredLLMClient)
    assert client.model_name == settings.ollama.llm_model


# ---------------------------------------------------------------------------
# Test 3: StructuredLLMClient Protocol Compliance
# ---------------------------------------------------------------------------

def test_3_protocol_compliance() -> None:
    """Both OllamaLLMClient and GatewayLLMClient satisfy StructuredLLMClient protocol."""
    ollama_c = OllamaLLMClient(base_url="http://127.0.0.1:11434")
    assert isinstance(ollama_c, StructuredLLMClient)

    gw_c = GatewayLLMClient(gateway_client=MagicMock(), model="qwen3:8b")
    assert isinstance(gw_c, StructuredLLMClient)
    assert hasattr(gw_c, "model_name")
    assert hasattr(gw_c, "generate_json")


# ---------------------------------------------------------------------------
# Test 4: Structured JSON Response Parsing
# ---------------------------------------------------------------------------

def test_4_structured_json_response_parsing() -> None:
    """GatewayLLMClient accurately extracts and parses JSON content from gateway envelope."""
    mock_gw = MagicMock()
    mock_gw.generate_chat.return_value = {
        "message": {"role": "assistant", "content": '{"answer": "PostgreSQL is canonical.", "answer_status": "answered"}'},
        "prompt_eval_count": 150,
        "eval_count": 45,
        "done_reason": "stop",
    }
    client = GatewayLLMClient(gateway_client=mock_gw, model="qwen3:8b")
    res = client.generate_json(_make_dummy_request())

    assert isinstance(res, LLMGenerationResult)
    assert res.parsed_json == {"answer": "PostgreSQL is canonical.", "answer_status": "answered"}
    assert res.model_name == "qwen3:8b"
    assert res.truncated is False
    assert res.done_reason == "stop"


# ---------------------------------------------------------------------------
# Test 5: Token Telemetry Preservation
# ---------------------------------------------------------------------------

def test_5_token_telemetry_preserved() -> None:
    """GatewayLLMClient preserves prompt_tokens, completion_tokens, and duration_ms."""
    mock_gw = MagicMock()
    mock_gw.generate_chat.return_value = {
        "message": {"role": "assistant", "content": '{"status": "ok"}'},
        "prompt_eval_count": 512,
        "eval_count": 128,
        "done_reason": "stop",
    }
    client = GatewayLLMClient(gateway_client=mock_gw, model="qwen3:8b")
    res = client.generate_json(_make_dummy_request())
    assert res.prompt_tokens == 512
    assert res.completion_tokens == 128
    assert res.duration_ms >= 0


# ---------------------------------------------------------------------------
# Test 6: Truncation and Completion Handling
# ---------------------------------------------------------------------------

def test_6_truncation_handling() -> None:
    """When gateway returns done_reason='length' with incomplete JSON, LLM_TRUNCATED is raised."""
    mock_gw = MagicMock()
    mock_gw.generate_chat.return_value = {
        "message": {"role": "assistant", "content": '{"answer": "Incomplete text without closing brace'},
        "prompt_eval_count": 100,
        "eval_count": 2048,
        "done_reason": "length",
    }
    client = GatewayLLMClient(gateway_client=mock_gw, model="qwen3:8b")
    with pytest.raises(LLMExecutionError) as exc_info:
        client.generate_json(_make_dummy_request())
    assert exc_info.value.code == "LLM_TRUNCATED"
    assert exc_info.value.retryable is True


# ---------------------------------------------------------------------------
# Test 7: Gateway Authentication Failure Propagation
# ---------------------------------------------------------------------------

def test_7_gateway_auth_failure_propagates() -> None:
    """Gateway HTTP 401/403 translates cleanly to typed LLMExecutionError without leaking secret."""
    mock_gw = MagicMock()
    mock_gw.generate_chat.side_effect = InferenceGatewayClientError(
        message="Invalid Bearer Token for Gateway",
        code="GATEWAY_UNAUTHORIZED",
        status_code=401,
        retryable=False,
    )
    client = GatewayLLMClient(gateway_client=mock_gw, model="qwen3:8b")
    with pytest.raises(LLMExecutionError) as exc_info:
        client.generate_json(_make_dummy_request())
    assert exc_info.value.code == "GATEWAY_UNAUTHORIZED"
    assert exc_info.value.retryable is False
    assert "Invalid Bearer Token" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test 8: Gateway Timeout Propagation
# ---------------------------------------------------------------------------

def test_8_gateway_timeout_propagates() -> None:
    """Gateway client timeout translates cleanly to retryable LLMExecutionError."""
    mock_gw = MagicMock()
    mock_gw.generate_chat.side_effect = InferenceGatewayClientError(
        message="Request to gateway timed out after 120s",
        code="GATEWAY_TIMEOUT",
        status_code=504,
        retryable=True,
    )
    client = GatewayLLMClient(gateway_client=mock_gw, model="qwen3:8b")
    with pytest.raises(LLMExecutionError) as exc_info:
        client.generate_json(_make_dummy_request())
    assert exc_info.value.code == "GATEWAY_TIMEOUT"
    assert exc_info.value.retryable is True


# ---------------------------------------------------------------------------
# Test 9: Missing Gateway Initialization Fails Closed
# ---------------------------------------------------------------------------

def test_9_missing_gateway_fails_closed() -> None:
    """When gateway mode is enabled but gateway_client is None, get_llm_client fails closed."""
    settings = Settings(
        inference_gateway_enabled=True,
        jwt_secret_key=SecretStr("test-secret-at-least-32-chars-long-xxx"),
        file_encryption_key=SecretStr("fernet-key-min-32-chars-length!!"),
        token_encryption_key=SecretStr("token-key-min-32-chars-length!!"),
    )
    req = MagicMock()
    req.app.state = MagicMock(spec=[])
    with pytest.raises(InferenceGatewayClientError) as exc_info:
        get_llm_client(request=req, settings=settings, gateway_client=None)
    assert exc_info.value.code == "GATEWAY_NOT_INITIALIZED"


# ---------------------------------------------------------------------------
# Test 10: Gateway Outage Never Falls Back to Direct Ollama
# ---------------------------------------------------------------------------

def test_10_no_silent_fallback_to_ollama() -> None:
    """When gateway fails, it raises LLMExecutionError and NEVER returns direct Ollama results."""
    mock_gw = MagicMock()
    mock_gw.generate_chat.side_effect = InferenceGatewayClientError(
        message="Gateway connection refused on 8002",
        code="GATEWAY_UNAVAILABLE",
        status_code=503,
        retryable=True,
    )
    client = GatewayLLMClient(gateway_client=mock_gw, model="qwen3:8b")
    with pytest.raises(LLMExecutionError) as exc_info:
        client.generate_json(_make_dummy_request())
    assert exc_info.value.code == "GATEWAY_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Test 11: AssistantLLMReasoner Compatibility with GatewayLLMClient
# ---------------------------------------------------------------------------

def test_11_assistant_reasoner_compatibility() -> None:
    """AssistantLLMReasoner functions identically with GatewayLLMClient."""
    settings = Settings(
        jwt_secret_key=SecretStr("test-secret-at-least-32-chars-long-xxx"),
        file_encryption_key=SecretStr("fernet-key-min-32-chars-length!!"),
        token_encryption_key=SecretStr("token-key-min-32-chars-length!!"),
    )
    mock_gw = MagicMock()
    mock_payload = {
        "answer": "According to [S1], the database failover runbook requires replica promotion.",
        "answer_status": "answered",
        "claims": [{"claim_text": "Replica promotion required", "citation_labels": ["S1"], "confidence": 0.95}],
        "uncertainty": None,
        "conflicts": [],
        "missing_information": [],
        "suggested_followup_questions": ["What is the estimated recovery time?"],
    }
    import json
    mock_gw.generate_chat.return_value = {
        "message": {"role": "assistant", "content": json.dumps(mock_payload)},
        "prompt_eval_count": 220,
        "eval_count": 65,
        "done_reason": "stop",
    }
    gw_llm = GatewayLLMClient(gateway_client=mock_gw, model="qwen3:8b")
    reasoner = AssistantLLMReasoner(settings=settings, llm_client=gw_llm)

    payload, telemetry = reasoner.generate_answer(
        question="How does database failover work?",
        evidence_prompt='<project_evidence id="S1">Replica promotion runbook.</project_evidence>',
        available_citation_labels=["S1"],
    )

    assert isinstance(payload, AssistantAnswerPayload)
    assert payload.answer_status == AssistantAnswerStatus.ANSWERED
    assert len(payload.claims) == 1
    assert payload.claims[0].citation_labels == ["S1"]
    assert telemetry["model_name"] == "qwen3:8b"
    assert telemetry["prompt_tokens"] == 220


# ---------------------------------------------------------------------------
# Test 12: KnowledgeReconstructionService Protocol Compatibility
# ---------------------------------------------------------------------------

def test_12_knowledge_reconstruction_compatibility() -> None:
    """GatewayLLMClient satisfies the StructuredLLMClient contract required by KnowledgeReconstructionService."""
    mock_gw = MagicMock()
    mock_gw.generate_chat.return_value = {
        "message": {"role": "assistant", "content": '{"decisions": [{"title": "Adopt PostgreSQL"}], "items": []}'},
        "prompt_eval_count": 300,
        "eval_count": 40,
        "done_reason": "stop",
    }
    client = GatewayLLMClient(gateway_client=mock_gw, model="qwen3:8b")
    # Verify that calling generate_json on the client returns expected LLMGenerationResult
    req = LLMGenerationRequest(
        system_prompt="Extract project decisions",
        user_prompt="We chose PostgreSQL over MongoDB because of ACID requirements.",
    )
    result = client.generate_json(req)
    assert isinstance(result, LLMGenerationResult)
    assert "decisions" in result.parsed_json
    assert result.parsed_json["decisions"][0]["title"] == "Adopt PostgreSQL"
