"""Upstream communication service for local Ollama."""

from __future__ import annotations

import asyncio
import time
import httpx
from typing import Any

from infrastructure.gateway.config import GatewaySettings
from infrastructure.gateway.exceptions import (
    CapacityExceededError,
    ServiceUnavailableError,
    ValidationError,
)
from infrastructure.gateway.schemas import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    EmbedRequest,
    EmbedResponse,
)

# Concurrency semaphore protecting RTX 4050 6GB VRAM
_GPU_INFERENCE_SEMAPHORE = asyncio.Semaphore(1)


class OllamaService:
    """Proxies and bounds requests to local Ollama runtime."""

    def __init__(self, settings: GatewaySettings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(timeout=settings.gateway_request_timeout)

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Execute chat inference against Qwen3 8B with concurrency limiting."""
        # Validate model against allowlist
        if request.model not in self._settings.allowed_chat_models:
            raise ValidationError(
                f"Model '{request.model}' is not in approved allowlist: {self._settings.allowed_chat_models}",
                error_code="MODEL_NOT_ALLOWED",
                details={"allowed_models": self._settings.allowed_chat_models},
            )

        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [m.model_dump() for m in request.messages],
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.num_predict,
            },
        }
        if request.format:
            payload["format"] = request.format

        # Acquire GPU semaphore with timeout
        try:
            acquired = await asyncio.wait_for(
                _GPU_INFERENCE_SEMAPHORE.acquire(),
                timeout=self._settings.gateway_concurrency_timeout,
            )
        except asyncio.TimeoutError:
            raise CapacityExceededError(
                "Local GPU inference capacity busy. Request queue timed out.",
                error_code="GPU_BUSY",
            )

        t0 = time.perf_counter()
        try:
            url = f"{self._settings.ollama_base_url}/api/chat"
            resp = await self._client.post(url, json=payload, timeout=self._settings.gateway_request_timeout)
            if resp.status_code != 200:
                raise ServiceUnavailableError(
                    "ollama",
                    f"Upstream Ollama returned status {resp.status_code}: {resp.text[:200]}",
                )
            data = resp.json()
        except httpx.RequestError as exc:
            raise ServiceUnavailableError(
                "ollama",
                f"Cannot connect to local Ollama service: {type(exc).__name__}",
            ) from exc
        finally:
            _GPU_INFERENCE_SEMAPHORE.release()

        duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        msg_data = data.get("message", {})

        return ChatResponse(
            model=data.get("model", request.model),
            message=ChatMessage(
                role=msg_data.get("role", "assistant"),
                content=msg_data.get("content", ""),
                thinking=msg_data.get("thinking"),
            ),
            done=data.get("done", True),
            total_duration_ms=duration_ms,
            eval_count=data.get("eval_count"),
            prompt_eval_count=data.get("prompt_eval_count"),
        )

    async def embed(self, request: EmbedRequest) -> EmbedResponse:
        """Generate text embeddings via Nomic Embed Text."""
        if request.model not in self._settings.allowed_embed_models:
            raise ValidationError(
                f"Embedding model '{request.model}' is not in approved allowlist: {self._settings.allowed_embed_models}",
                error_code="MODEL_NOT_ALLOWED",
                details={"allowed_models": self._settings.allowed_embed_models},
            )

        payload = {
            "model": request.model,
            "input": request.input,
        }

        t0 = time.perf_counter()
        try:
            url = f"{self._settings.ollama_base_url}/api/embed"
            resp = await self._client.post(url, json=payload, timeout=self._settings.gateway_embed_timeout)
            if resp.status_code != 200:
                raise ServiceUnavailableError(
                    "ollama",
                    f"Upstream Ollama embed failed with status {resp.status_code}: {resp.text[:200]}",
                )
            data = resp.json()
        except httpx.RequestError as exc:
            raise ServiceUnavailableError(
                "ollama",
                f"Cannot connect to local Ollama embed service: {type(exc).__name__}",
            ) from exc

        duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        embeddings = data.get("embeddings", [])
        dims = len(embeddings[0]) if embeddings else self._settings.expected_embed_dimension

        if dims != self._settings.expected_embed_dimension:
            raise ValidationError(
                f"Embedding output dimensionality {dims} does not match expected {self._settings.expected_embed_dimension}.",
                error_code="EMBEDDING_DIMENSION_MISMATCH",
            )

        return EmbedResponse(
            model=data.get("model", request.model),
            embeddings=embeddings,
            dimensions=dims,
            duration_ms=duration_ms,
        )
