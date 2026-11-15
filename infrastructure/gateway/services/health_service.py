"""Health service for probing upstream local services (Ollama, Chroma, Redis) and GPU."""

from __future__ import annotations

import logging
import subprocess
import time
from typing import Any

import httpx

from infrastructure.gateway.config import GatewaySettings
from infrastructure.gateway.schemas import (
    GatewayHealthResponse,
    ServiceHealthStatus,
)

logger = logging.getLogger("gateway.health")


class HealthService:
    """Service health and telemetry aggregator for local AI infrastructure."""

    def __init__(self, settings: GatewaySettings) -> None:
        self.settings = settings

    async def check_ollama(self, client: httpx.AsyncClient) -> tuple[ServiceHealthStatus, list[str]]:
        """Probe Ollama for version and active running models."""
        start = time.perf_counter()
        loaded_models: list[str] = []
        try:
            ver_resp = await client.get(f"{self.settings.ollama_base_url}/api/version", timeout=3.0)
            if ver_resp.status_code != 200:
                return (
                    ServiceHealthStatus(
                        status="degraded",
                        latency_ms=round((time.perf_counter() - start) * 1000, 2),
                        details=f"Ollama returned HTTP {ver_resp.status_code}",
                    ),
                    [],
                )
            ver_data = ver_resp.json()

            ps_resp = await client.get(f"{self.settings.ollama_base_url}/api/ps", timeout=3.0)
            if ps_resp.status_code == 200:
                ps_data = ps_resp.json()
                models = ps_data.get("models", [])
                loaded_models = [m.get("name", "unknown") for m in models]

            latency = round((time.perf_counter() - start) * 1000, 2)
            version = ver_data.get("version", "unknown")
            return (
                ServiceHealthStatus(
                    status="ok",
                    latency_ms=latency,
                    details=f"Ollama v{version} ready",
                ),
                loaded_models,
            )
        except Exception as exc:
            logger.warning("Ollama health check failed: %s", exc)
            return (
                ServiceHealthStatus(
                    status="unavailable",
                    latency_ms=round((time.perf_counter() - start) * 1000, 2),
                    details=str(exc)[:100],
                ),
                [],
            )

    async def check_chroma(self, client: httpx.AsyncClient) -> ServiceHealthStatus:
        """Probe ChromaDB heartbeat."""
        start = time.perf_counter()
        try:
            resp = await client.get(f"{self.settings.chroma_base_url}/api/v2/heartbeat", timeout=3.0)
            latency = round((time.perf_counter() - start) * 1000, 2)
            if resp.status_code == 200:
                return ServiceHealthStatus(
                    status="ok",
                    latency_ms=latency,
                    details="ChromaDB v2 heartbeat ok",
                )
            return ServiceHealthStatus(
                status="degraded",
                latency_ms=latency,
                details=f"ChromaDB returned HTTP {resp.status_code}",
            )
        except Exception as exc:
            logger.warning("ChromaDB health check failed: %s", exc)
            return ServiceHealthStatus(
                status="unavailable",
                latency_ms=round((time.perf_counter() - start) * 1000, 2),
                details=str(exc)[:100],
            )

    async def check_redis(self) -> ServiceHealthStatus:
        """Probe local Redis server."""
        start = time.perf_counter()
        try:
            import redis.asyncio as aioredis  # type: ignore

            r = aioredis.from_url(self.settings.redis_base_url, socket_connect_timeout=2.0)
            ping_res = await r.ping()
            await r.aclose()
            latency = round((time.perf_counter() - start) * 1000, 2)
            if ping_res:
                return ServiceHealthStatus(
                    status="ok",
                    latency_ms=latency,
                    details="Redis ping successful",
                )
            return ServiceHealthStatus(status="degraded", latency_ms=latency, details="Ping failed")
        except Exception as exc:
            # Redis is an optional local cache in M3.1
            return ServiceHealthStatus(
                status="unavailable",
                latency_ms=round((time.perf_counter() - start) * 1000, 2),
                details=f"Redis unavailable: {exc}"[:100],
            )

    def get_gpu_telemetry(self) -> dict[str, Any] | None:
        """Retrieve NVIDIA GPU stats safely via nvidia-smi."""
        try:
            res = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=3.0,
            )
            parts = [p.strip() for p in res.stdout.strip().split(",")]
            if len(parts) >= 6:
                return {
                    "name": parts[0],
                    "memory_total_mb": int(parts[1]),
                    "memory_used_mb": int(parts[2]),
                    "memory_free_mb": int(parts[3]),
                    "gpu_utilization_pct": int(parts[4]),
                    "temperature_c": int(parts[5]),
                }
        except Exception as exc:
            logger.debug("nvidia-smi telemetry unavailable: %s", exc)
        return None

    async def get_full_health(self) -> GatewayHealthResponse:
        """Aggregate health status of all local AI infrastructure components."""
        async with httpx.AsyncClient() as client:
            ollama_status, loaded_models = await self.check_ollama(client)
            chroma_status = await self.check_chroma(client)
            redis_status = await self.check_redis()

        gpu_data = self.get_gpu_telemetry()

        services = {
            "ollama": ollama_status,
            "chroma": chroma_status,
            "redis": redis_status,
        }

        # Determine overall gateway status
        if ollama_status.status == "ok" and chroma_status.status == "ok":
            gateway_status = "healthy"
        elif ollama_status.status == "ok" or chroma_status.status == "ok":
            gateway_status = "degraded"
        else:
            gateway_status = "unhealthy"

        return GatewayHealthResponse(
            gateway_status=gateway_status,
            host_binding=f"{self.settings.inference_gateway_host}:{self.settings.inference_gateway_port}",
            concurrency_limit=self.settings.gateway_max_concurrency,
            services=services,
            gpu=gpu_data,
            loaded_models=loaded_models,
        )
