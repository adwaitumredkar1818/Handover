"""Main FastAPI entrypoint for the Local Inference Gateway."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, status
from fastapi.middleware.cors import CORSMiddleware

from infrastructure.gateway.auth import verify_gateway_api_key
from infrastructure.gateway.config import GatewaySettings, get_gateway_settings
from infrastructure.gateway.exceptions import (
    GatewayError,
    gateway_error_handler,
    generic_error_handler,
)
from infrastructure.gateway.middleware import SecurityAndCorrelationMiddleware
from infrastructure.gateway.schemas import (
    ChatRequest,
    ChatResponse,
    EmbedRequest,
    EmbedResponse,
    GatewayHealthResponse,
    VectorSearchRequest,
    VectorSearchResponse,
)
from infrastructure.gateway.services.chroma_service import ChromaService
from infrastructure.gateway.services.health_service import HealthService
from infrastructure.gateway.services.ollama_service import OllamaService

logger = logging.getLogger("gateway")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle."""
    settings = get_gateway_settings()

    # CRITICAL SECURITY ASSERTION: Loopback binding only
    if settings.inference_gateway_host not in ("127.0.0.1", "localhost"):
        msg = (
            f"FATAL SECURITY VIOLATION: Local Inference Gateway must bind strictly to 127.0.0.1! "
            f"Configured host is '{settings.inference_gateway_host}'."
        )
        logger.critical(msg)
        raise RuntimeError(msg)

    logger.info(
        "Local Inference Gateway initializing on %s:%d (concurrency=%d)",
        settings.inference_gateway_host,
        settings.inference_gateway_port,
        settings.gateway_max_concurrency,
    )
    yield
    logger.info("Local Inference Gateway shutting down.")


def create_gateway_app() -> FastAPI:
    """Create and configure the FastAPI gateway instance."""
    app = FastAPI(
        title="The Handover — Local Inference Gateway",
        description="Secure, authenticated loopback proxy for local AI infrastructure (Ollama & ChromaDB).",
        version="1.0.0",
        docs_url=None,  # Disabled for security
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    # Register error handlers
    app.add_exception_handler(GatewayError, gateway_error_handler)
    app.add_exception_handler(Exception, generic_error_handler)

    settings = get_gateway_settings()

    # Security, correlation, & rate-limiting middleware
    app.add_middleware(
        SecurityAndCorrelationMiddleware,
        max_body_bytes=settings.gateway_max_body_bytes,
        rate_limit_requests=settings.rate_limit_requests,
        rate_limit_window_seconds=settings.rate_limit_window_seconds,
    )

    # CORS strictly restricted to localhost
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1",
            "http://localhost",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # Instantiate services
    settings = get_gateway_settings()
    ollama_service = OllamaService(settings)
    chroma_service = ChromaService(settings)
    health_service = HealthService(settings)

    # --- Routes ---

    @app.get("/health", status_code=status.HTTP_200_OK)
    async def get_minimal_health() -> dict[str, str]:
        """Minimal unauthenticated health probe returning basic liveness."""
        return {"status": "ok"}

    @app.get(
        "/v1/health",
        response_model=GatewayHealthResponse,
        status_code=status.HTTP_200_OK,
        dependencies=[Depends(verify_gateway_api_key)],
    )
    async def get_health() -> GatewayHealthResponse:
        """Authenticated detailed health probe reporting service statuses and GPU telemetry."""
        return await health_service.get_full_health()

    @app.post(
        "/v1/chat",
        response_model=ChatResponse,
        status_code=status.HTTP_200_OK,
        dependencies=[Depends(verify_gateway_api_key)],
    )
    async def chat(request: ChatRequest) -> ChatResponse:
        """Authenticated chat completion endpoint routing to local Ollama (Qwen3 8B)."""
        return await ollama_service.chat(request)

    @app.post(
        "/v1/embed",
        response_model=EmbedResponse,
        status_code=status.HTTP_200_OK,
        dependencies=[Depends(verify_gateway_api_key)],
    )
    async def embed(request: EmbedRequest) -> EmbedResponse:
        """Authenticated text embedding endpoint routing to local Ollama (Nomic Embed Text)."""
        return await ollama_service.embed(request)

    @app.post(
        "/v1/vector/search",
        response_model=VectorSearchResponse,
        status_code=status.HTTP_200_OK,
        dependencies=[Depends(verify_gateway_api_key)],
    )
    async def vector_search(request: VectorSearchRequest) -> VectorSearchResponse:
        """Authenticated, multi-tenant scoped vector similarity search routing to local ChromaDB."""
        # MULTI-TENANT BOUNDARY ENFORCEMENT:
        # Organization and project scoping are mandatory to prevent unauthorized cross-tenant data exfiltration
        if not request.organisation_id or not request.project_id:
            raise GatewayError(
                message="Multi-tenant vector search requires both 'organisation_id' and 'project_id' scope.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                error_code="TENANT_SCOPE_REQUIRED",
            )

        # Enforce scoping filters directly inside ChromaDB query payload
        tenant_clauses: list[dict[str, Any]] = [
            {"organisation_id": {"$eq": request.organisation_id}},
            {"project_id": {"$eq": request.project_id}},
        ]

        if request.where:
            # If caller supplied additional where clauses, combine under $and
            combined_where = {"$and": tenant_clauses + [request.where]}
        else:
            combined_where = {"$and": tenant_clauses}

        embedding = request.query_embedding
        if embedding is None:
            if not request.query_text:
                raise GatewayError(
                    message="Either query_embedding or query_text must be provided.",
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    error_code="VALIDATION_ERROR",
                )
            # Embed query text dynamically using Nomic Embed Text
            embed_req = EmbedRequest(model=settings.default_embed_model, input=[request.query_text])
            embed_res = await ollama_service.embed(embed_req)
            embedding = embed_res.embeddings[0]

        return await chroma_service.query_vector(
            collection_name=request.collection_name,
            query_embedding=embedding,
            top_k=request.top_k,
            where=combined_where,
        )

    return app


app = create_gateway_app()
