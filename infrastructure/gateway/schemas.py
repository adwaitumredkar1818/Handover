"""Pydantic request and response schemas for the Local Inference Gateway."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class BaseGatewayModel(BaseModel):
    """Base schema config."""

    model_config = ConfigDict(extra="forbid")


# --- Chat schemas ---

class ChatMessage(BaseGatewayModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(default="", max_length=32_768)
    thinking: str | None = Field(default=None)


class ChatRequest(BaseGatewayModel):
    """Restricted chat request matching Ollama /api/chat contract."""

    model: str = Field(default="qwen3:8b", min_length=1, max_length=64)
    messages: list[ChatMessage] = Field(min_length=1, max_length=50)
    temperature: float = Field(default=0.1, ge=0.0, le=1.0)
    num_predict: int = Field(default=1024, ge=1, le=4096)
    stream: bool = Field(default=False)
    format: Literal["json"] | None = Field(default=None)


class ChatResponse(BaseGatewayModel):
    model: str
    message: ChatMessage
    done: bool
    total_duration_ms: float
    eval_count: int | None = None
    prompt_eval_count: int | None = None


# --- Embedding schemas ---

class EmbedRequest(BaseGatewayModel):
    """Restricted embedding request matching Ollama /api/embed contract."""

    model: str = Field(default="nomic-embed-text", min_length=1, max_length=64)
    input: list[str] = Field(min_length=1, max_length=16)  # Bounded batch


class EmbedResponse(BaseGatewayModel):
    model: str
    embeddings: list[list[float]]
    dimensions: int
    duration_ms: float


# --- Vector search schemas ---

class VectorSearchRequest(BaseGatewayModel):
    """Restricted vector search request querying local ChromaDB."""

    collection_name: str = Field(default="ipkrh_evidence_chunks_nomic-embed-text_v1", min_length=1, max_length=128)
    query_text: str | None = Field(default=None, min_length=1, max_length=4096)
    query_embedding: list[float] | None = Field(default=None)
    top_k: int = Field(default=10, ge=1, le=50)
    # Multi-tenant scoping parameters: mandatory organization & project boundary
    organisation_id: str | None = Field(default=None, min_length=1, max_length=64)
    project_id: str | None = Field(default=None, min_length=1, max_length=64)
    where: dict[str, Any] | None = Field(default=None)


class VectorHit(BaseGatewayModel):
    id: str
    distance: float
    similarity: float
    metadata: dict[str, Any]


class VectorSearchResponse(BaseGatewayModel):
    collection_name: str
    total_hits: int
    hits: list[VectorHit]
    duration_ms: float


# --- Health & telemetry schemas ---

class ServiceHealthStatus(BaseGatewayModel):
    status: Literal["ok", "degraded", "unavailable"]
    latency_ms: float | None = None
    details: str | None = None


class GatewayHealthResponse(BaseGatewayModel):
    gateway_status: Literal["healthy", "degraded", "unhealthy"]
    host_binding: str
    concurrency_limit: int
    services: dict[str, ServiceHealthStatus]
    gpu: dict[str, Any] | None = None
    loaded_models: list[str] = Field(default_factory=list)
