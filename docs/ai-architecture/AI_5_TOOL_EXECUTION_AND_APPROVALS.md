# Phase AI-5: Full Tool Registry and Human Approval

**Platform**: The Handover (Intelligent Project Knowledge Reconstruction & Handover Platform)  
**Document**: Phase AI-5 Deliverable — Architecture & Verification Report  
**Date**: November 2026  
**Status**: VERIFIED & COMPLETE  

---

## 1. Executive Summary

Phase AI-5 implements the **Deterministic Tool Registry and Execution Sandbox** in `backend/app/services/ai/tools.py`:
1. **Deterministic Tool Catalog (`ToolRegistry`)**:
   - Every tool declares explicit input schemas, required permissions, and consequence classifications.
   - Initial verified tools: `search_knowledge` (Read-only) and `approve_handover_task` (Consequential).
2. **Two-Tier Execution Policy**:
   - **Tier 1 (Read-Only Tools)**: Execute autonomously when the caller has verified `ProjectContext` permissions.
   - **Tier 2 (Consequential Tools)**: Strictly reject autonomous execution if `approved != True`. Emits approval events requiring an explicit human click in the user interface.
3. **Zero-Privilege Enforcement**: All tool execution handlers take `project_ctx: ProjectContext` and execute under the caller's verified project identity, preventing administrative privilege escalation.

---

## 2. Test Verification Evidence

- Executed `backend/tests/test_ai_tool_registry.py`:
  - `test_tool_registry_read_only_execution`: **PASSED** (autonomous execution of authorized read tools).
  - `test_consequential_tool_requires_approval`: **PASSED** (unapproved calls fail closed with explicit requirement; approved calls succeed).
  - `test_tool_permission_denial`: **PASSED** (unauthorized callers raise `ForbiddenError`).
