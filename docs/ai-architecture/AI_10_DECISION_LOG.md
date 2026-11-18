# AI-10 Decision Log — Production Readiness & Operational Engineering

**Platform**: The Handover (Intelligent Project Knowledge Reconstruction & Handover Platform)  
**Document**: Architectural, Reliability & Operational Decision Log  
**Date**: November 2026  

---

## Record 001: Distributed Atomic Idempotency via Redis SET NX + PostgreSQL Audit
- **Date**: 2026-11-18
- **Context**: During AI-10.0 cross-process concurrency auditing, concurrent execution of consequential tools across separate operating system processes revealed that relying solely on a sequential PostgreSQL check-and-insert could permit race conditions before the first transaction commits.
- **Decision**: Update `ToolRegistry.execute_tool()` to implement a dual-gate claim:
  1. **Immediate Atomic Fast-Path**: Use Redis `r.set(f"tool:idempotency:{fingerprint}", "executing", nx=True, ex=604800)` to atomically claim execution rights across all distributed workers.
  2. **Authoritative Durable Gate**: Check and insert the lifecycle claim in PostgreSQL `audit_logs` table (`event_type = 'tool.execution.state'`).
- **Consequences**: Concurrent requests across independent processes are blocked instantly with HTTP/execution rejection; zero duplicate tool executions occur under concurrent race conditions.
