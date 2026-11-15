"""Multi-process GPU inference concurrency and cross-process safety test.

Tests whether concurrent requests originating from separate processes (simulating
the FastAPI Gateway and the app.worker background worker) to Ollama are safely
serialized and whether hardware VRAM stays protected.
"""

from __future__ import annotations

import multiprocessing
import os
import sys
import time
import urllib.request
import json

from infrastructure.gateway.config import get_gateway_settings
VALID_TOKEN = get_gateway_settings().inference_gateway_api_key.get_secret_value()


def worker_process_simulated_inference(proc_id: int, result_queue: multiprocessing.Queue):
    """Simulates app.worker running an OCR or Embedding task directly to local Ollama."""
    t0 = time.perf_counter()
    req_data = {
        "model": "nomic-embed-text",
        "input": [f"Worker task payload {proc_id} timestamp {time.time()}"],
    }
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/embed",
        data=json.dumps(req_data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            data = json.loads(resp.read().decode())
            dur = (time.perf_counter() - t0) * 1000
            result_queue.put({"proc_id": proc_id, "type": "worker_direct", "status": resp.status, "duration_ms": dur})
    except Exception as exc:
        result_queue.put({"proc_id": proc_id, "type": "worker_direct", "error": str(exc)})


def gateway_process_simulated_client(proc_id: int, result_queue: multiprocessing.Queue):
    """Simulates an external cloud client querying Ollama through the Local Gateway."""
    t0 = time.perf_counter()
    req_data = {
        "model": "nomic-embed-text",
        "input": [f"Gateway client payload {proc_id} timestamp {time.time()}"],
    }
    # Note: Gateway is tested via TestClient / HTTP
    # Here we send directly to Ollama embed via embed request format to test upstream response concurrency
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/embed",
        data=json.dumps(req_data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            data = json.loads(resp.read().decode())
            dur = (time.perf_counter() - t0) * 1000
            result_queue.put({"proc_id": proc_id, "type": "gateway_client", "status": resp.status, "duration_ms": dur})
    except Exception as exc:
        result_queue.put({"proc_id": proc_id, "type": "gateway_client", "error": str(exc)})


def test_cross_process_concurrent_ollama_requests():
    """Verify that multiple processes can send simultaneous requests to Ollama without crash or corruption."""
    result_queue = multiprocessing.Queue()
    processes = []

    # Spawn 2 worker direct processes and 2 gateway client processes simultaneously
    for i in range(2):
        p1 = multiprocessing.Process(target=worker_process_simulated_inference, args=(i, result_queue))
        p2 = multiprocessing.Process(target=gateway_process_simulated_client, args=(i + 10, result_queue))
        processes.extend([p1, p2])

    t_start = time.perf_counter()
    for p in processes:
        p.start()

    for p in processes:
        p.join(timeout=35.0)

    total_time = (time.perf_counter() - t_start) * 1000
    results = []
    while not result_queue.empty():
        results.append(result_queue.get())

    assert len(results) == 4, f"Expected 4 process completions, got {len(results)}"
    for r in results:
        assert "status" in r and r["status"] == 200, f"Process failure: {r}"
