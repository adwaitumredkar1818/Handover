"""Configuration settings for the Local Inference Gateway."""

from __future__ import annotations

import os
from functools import lru_cache
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    """Local Inference Gateway runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Network binding - strictly loopback only
    inference_gateway_host: str = Field(default="127.0.0.1")
    inference_gateway_port: int = Field(default=8002, ge=1024, le=65535)

    # Gateway shared authentication secret - mandatory, no insecure default fallback
    inference_gateway_api_key: SecretStr = Field(
        ...,
        description="Mandatory shared secret token for gateway authentication (min 32 chars).",
    )

    @field_validator("inference_gateway_api_key")
    @classmethod
    def validate_api_key(cls, v: SecretStr) -> SecretStr:
        val = v.get_secret_value().strip()
        if not val or len(val) < 32:
            raise ValueError(
                "Gateway API key must be configured with a non-empty string of at least 32 characters."
            )
        return v

    # Upstream local service endpoints
    ollama_base_url: str = Field(default="http://127.0.0.1:11434")
    chroma_base_url: str = Field(default="http://127.0.0.1:8001")
    redis_base_url: str = Field(default="redis://127.0.0.1:6379/0")

    # Allowed models and collections
    allowed_chat_models: list[str] = Field(default_factory=lambda: ["qwen3:8b", "qwen3:latest"])
    default_chat_model: str = Field(default="qwen3:8b")
    allowed_embed_models: list[str] = Field(default_factory=lambda: ["nomic-embed-text", "nomic-embed-text:latest"])
    default_embed_model: str = Field(default="nomic-embed-text")
    expected_embed_dimension: int = Field(default=768)

    allowed_chroma_collections: list[str] = Field(
        default_factory=lambda: ["ipkrh_evidence_chunks_nomic-embed-text_v1"]
    )
    default_chroma_collection: str = Field(default="ipkrh_evidence_chunks_nomic-embed-text_v1")

    # Operational constraints
    gateway_request_timeout: float = Field(default=120.0, ge=1.0, le=300.0)
    gateway_embed_timeout: float = Field(default=30.0, ge=1.0, le=120.0)
    gateway_max_body_bytes: int = Field(default=1_048_576, ge=1024, le=10_485_760)  # 1 MB
    gateway_max_concurrency: int = Field(default=1, ge=1, le=4)  # 1 concurrent request for RTX 4050 6GB
    gateway_concurrency_timeout: float = Field(default=30.0, ge=1.0, le=120.0)

    # In-memory rate limiting (per-instance gateway guardrail)
    rate_limit_requests: int = Field(default=60, ge=1, le=1000)  # max requests per window
    rate_limit_window_seconds: float = Field(default=60.0, ge=1.0, le=3600.0)  # window in seconds


@lru_cache
def get_gateway_settings() -> GatewaySettings:
    """Return cached gateway settings loaded from environment."""
    return GatewaySettings()
