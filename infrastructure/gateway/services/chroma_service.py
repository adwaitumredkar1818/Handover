"""ChromaDB proxy service querying local Chroma instance."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from infrastructure.gateway.config import GatewaySettings
from infrastructure.gateway.exceptions import (
    ServiceUnavailableError,
    ValidationError,
)
from infrastructure.gateway.schemas import VectorHit, VectorSearchResponse

logger = logging.getLogger("gateway.chroma")


class ChromaService:
    """Bounded, authenticated client for querying local ChromaDB."""

    def __init__(self, settings: GatewaySettings) -> None:
        self.settings = settings
        self.base_url = settings.chroma_base_url.rstrip("/")
        self.allowed_collections = set(settings.allowed_chroma_collections)
        # Cache collection_name -> collection_id mapping
        self._collection_id_cache: dict[str, str] = {}

    async def _get_collection_id(self, client: httpx.AsyncClient, collection_name: str) -> str:
        """Resolve collection name to UUID using Chroma v2 API."""
        if collection_name in self._collection_id_cache:
            return self._collection_id_cache[collection_name]

        url = f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections"
        try:
            resp = await client.get(url, timeout=5.0)
            if resp.status_code != 200:
                raise ServiceUnavailableError("chroma", f"Failed to list collections: HTTP {resp.status_code}")
            collections = resp.json()
            for col in collections:
                c_name = col.get("name")
                c_id = col.get("id")
                if c_name and c_id:
                    self._collection_id_cache[c_name] = c_id

            if collection_name in self._collection_id_cache:
                return self._collection_id_cache[collection_name]

            raise ValidationError(
                f"Collection '{collection_name}' not found in ChromaDB.",
                details={"collection_name": collection_name},
            )
        except httpx.RequestError as exc:
            raise ServiceUnavailableError("chroma", f"Cannot connect to ChromaDB: {exc}") from exc

    async def query_vector(
        self,
        collection_name: str,
        query_embedding: list[float],
        top_k: int = 10,
        where: dict[str, Any] | None = None,
    ) -> VectorSearchResponse:
        """Query ChromaDB by embedding vector."""
        if collection_name not in self.allowed_collections:
            raise ValidationError(
                f"Collection '{collection_name}' is not in the allowed collections list.",
                details={"allowed_collections": list(self.allowed_collections)},
            )

        if len(query_embedding) != self.settings.expected_embed_dimension:
            raise ValidationError(
                f"Query embedding dimension mismatch: expected {self.settings.expected_embed_dimension}, got {len(query_embedding)}",
                details={"expected": self.settings.expected_embed_dimension, "received": len(query_embedding)},
            )

        start_time = time.perf_counter()

        async with httpx.AsyncClient() as client:
            col_id = await self._get_collection_id(client, collection_name)

            query_url = (
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{col_id}/query"
            )

            payload: dict[str, Any] = {
                "query_embeddings": [query_embedding],
                "n_results": top_k,
                "include": ["metadatas", "distances"],
            }
            if where:
                payload["where"] = where

            try:
                resp = await client.post(query_url, json=payload, timeout=self.settings.gateway_embed_timeout)
                if resp.status_code != 200:
                    raise ServiceUnavailableError(
                        "chroma",
                        f"Chroma query failed with HTTP {resp.status_code}: {resp.text[:200]}",
                    )
                data = resp.json()
            except httpx.RequestError as exc:
                raise ServiceUnavailableError("chroma", f"ChromaDB connection failed: {exc}") from exc

        duration_ms = (time.perf_counter() - start_time) * 1000.0

        # Whitelist of safe, non-sensitive metadata keys to return to callers
        safe_meta_keys = {
            "chunk_id",
            "chunk_index",
            "chunk_type",
            "category",
            "source_type",
            "project_id",
            "organisation_id",
            "evidence_id",
        }

        hits: list[VectorHit] = []
        ids_list = data.get("ids", [[]])[0]
        distances_list = data.get("distances", [[]])[0] if data.get("distances") else []
        metadatas_list = data.get("metadatas", [[]])[0] if data.get("metadatas") else []

        for idx, item_id in enumerate(ids_list):
            dist = float(distances_list[idx]) if idx < len(distances_list) else 1.0
            raw_meta = metadatas_list[idx] if idx < len(metadatas_list) and metadatas_list[idx] else {}
            # Sanitize and minimize returned metadata to prevent sensitive ACL/ownership leakage
            sanitized_meta = {k: v for k, v in raw_meta.items() if k in safe_meta_keys}
            
            # Cosine distance: similarity = 1.0 - distance
            similarity = round(max(0.0, min(1.0, 1.0 - dist)), 4)
            hits.append(
                VectorHit(
                    id=item_id,
                    distance=round(dist, 4),
                    similarity=similarity,
                    metadata=sanitized_meta,
                )
            )

        return VectorSearchResponse(
            collection_name=collection_name,
            total_hits=len(hits),
            hits=hits,
            duration_ms=round(duration_ms, 2),
        )
