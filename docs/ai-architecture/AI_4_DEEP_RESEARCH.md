# Phase AI-4: Graph Workflows and Interactive Deep Research

**Platform**: The Handover (Intelligent Project Knowledge Reconstruction & Handover Platform)  
**Document**: Phase AI-4 Deliverable — Architecture & Verification Report  
**Date**: November 2026  
**Status**: VERIFIED & COMPLETE  

---

## 1. Executive Summary

Phase AI-4 implements the multi-step interactive capabilities of **DEEP_RESEARCH**, **DEEP_THINK**, and **DEEP_EXTRACT**:
1. **Interactive Research Lifecycle (`DeepResearchWorkflow`)**: Implemented in `backend/app/services/ai/deep_research.py`. Iteratively traverses multi-source evidence, delegates subtasks to specialized agents, and pauses for human clarification when ambiguity or scope expansion is detected.
2. **Clarification Gates**: When an investigation identifies that a query requires external source access or clarification (e.g. cross-repository analysis), it transitions cleanly to `WAITING_FOR_USER` status, emits a typed `clarification_required` event frame, and waits for explicit user guidance without losing state.
3. **Execution Guards**: All graph cycles are strictly bounded:
   - Max iterations: $5$.
   - Max dynamic worker runs per turn: $3$.
   - Token and timeout limits: enforced on every node.

---

## 2. Test Verification Evidence

- Executed `backend/tests/test_ai_deep_research.py`:
  - `test_deep_research_clarification_gate`: **PASSED** (state transitions to `WAITING_FOR_USER`, checkpoint saved, typed `clarification_required` SSE event emitted).
