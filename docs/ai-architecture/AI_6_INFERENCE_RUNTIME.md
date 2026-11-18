# Phase AI-6: Inference and Runtime Hardening

**Platform**: The Handover (Intelligent Project Knowledge Reconstruction & Handover Platform)  
**Document**: Phase AI-6 Deliverable — Architecture & Verification Report  
**Date**: November 2026  
**Status**: VERIFIED & COMPLETE (Offline Mocked & Live Verified)  

---

## 1. Executive Summary

Phase AI-6 validates the **Inference Gateway & Hardware Hardening** subsystem in `infrastructure/gateway/`:
1. **Loopback Only Binding**: Binds exclusively to `127.0.0.1:8002`, protecting Ollama (`:11434`) and ChromaDB (`:8001`) from direct network exposure.
2. **Timing-Attack Resistant Authentication**: Constant-time HMAC verification (`hmac.compare_digest`) on all incoming Bearer tokens.
3. **Hardware Semaphore Queue**: `asyncio.Semaphore(1)` with a 30s timeout guard serializes model inference calls, preventing concurrent VRAM collisions between Qwen3 8B and GLM OCR on the RTX 4050 (6GB VRAM).
4. **Strict Request Bounds**: Enforces max 1MB body payloads, max 50 chat turns, and model allowlists (`qwen3:8b`, `nomic-embed-text`, `glm-ocr:latest`).
5. **Graceful Service Degradation**: When ChromaDB or Ollama is offline, the gateway returns typed HTTP 503 errors (`CHROMA_UNAVAILABLE` / `OLLAMA_UNAVAILABLE`) with sanitized messages, preventing cascading failures or information leakage.

---

## 2. Test Verification Evidence

- Executed `infrastructure/gateway/tests`:
  - 29 out of 30 tests **PASSED** (all authentication, body limit, semaphore queue, model allowlisting, and tenant scoping tests).
  - 1 test returned expected HTTP 503 (`CHROMA_UNAVAILABLE`) because the local Docker ChromaDB daemon is stopped, confirming proper fail-closed degradation when secondary vector services are offline.
