# Phase AI-3: Permanent Agent Registry & Dynamic Worker Factory (Option C)

**Platform**: The Handover (Intelligent Project Knowledge Reconstruction & Handover Platform)  
**Document**: Phase AI-3 Deliverable — Architecture & Verification Report  
**Date**: November 2026  
**Status**: VERIFIED & COMPLETE  

---

## 1. Executive Summary

Phase AI-3 implements **Option C: Permanent Agent Registry + Dynamic Agent Instantiation**. Rather than running permanent unmonitored model processes, the platform maintains immutable, versioned agent specifications and dynamically instantiates temporary, scoped worker agents bound strictly to the caller's verified `ProjectContext`.

### Key Deliverables Implemented & Verified:
1. **Permanent Agent Registry (`AgentRegistry`)**: Implemented in `backend/app/services/ai/agent_registry.py` with the 10 approved logical agent blueprints:
   - `knowledge_agent`: Domain Knowledge & Provenance Specialist.
   - `engineering_agent`: Software Architecture & Codebase Specialist.
   - `project_agent`: Work Progress & Tasks Specialist.
   - `decision_agent`: Architectural Decision Record (ADR) & Rationale Specialist.
   - `security_agent`: Application Security & Permission Auditor (requires `assistant.admin`).
   - `database_agent`: Data Model & PostgreSQL Schema Specialist.
   - `api_agent`: API Contracts & Integration Boundary Specialist.
   - `infrastructure_agent`: DevOps, Docker & Runtime Gateway Specialist.
   - `analysis_agent`: Cross-Source Evidence Corroboration Specialist.
   - `planning_agent`: Handover & Transition Plan Architect.
2. **Dynamic Worker Factory (`DynamicAgentFactory`)**: Implemented in `backend/app/services/ai/agent_factory.py`. Validates task compatibility and permission requirements (`has_permission`) before instantiating temporary `DynamicAgentWorker` instances.
3. **Structured Agent Findings (`AgentFinding`)**: Dynamic workers capture typed, verifiable observations with explicit supporting citation tags (`[S#]`) and confidence ratings, avoiding raw chain-of-thought exposure.

---

## 2. Test Verification Evidence

- Executed `backend/tests/test_ai_agent_registry.py`:
  - `test_agent_registry_contains_approved_library`: **PASSED** (all 10 canonical agents registered with system instructions and allowed tools).
  - `test_dynamic_agent_factory_permission_boundary`: **PASSED** (verified fail-closed behavior: regular contributors can instantiate `knowledge_agent`, while `security_agent` requiring `assistant.admin` raises `ForbiddenError`).
