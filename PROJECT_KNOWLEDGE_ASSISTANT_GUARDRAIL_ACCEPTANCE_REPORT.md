# Project Knowledge Assistant Guardrail Acceptance Report
## Intelligent Project Knowledge Reconstruction & Handover Platform ("The Handover")
### Formal Governance & Security Guardrail Sign-Off

---

## 1. Compliance Assessment Matrix

| Standard / Requirement | Specification Criterion | Implementation Evidence | Verification Status |
| :--- | :--- | :--- | :--- |
| **Strict Single Active Project Scope** | Assistant is bounded to the active project; never retrieves from other projects or global memory. | Path parameter binding + `require_project_permission`, PostgreSQL project scoping, ChromaDB metadata filter. | **COMPLIANT** |
| **Personal Hardware Protection** | Must never disclose RTX 4050, 6GB VRAM, Victus, laptop specs, local file paths. | Pre-flight classifier refusal (`personal_device`) + post-generation output regex sanitizer. | **COMPLIANT** |
| **Cross-Project Inquiries Refusal** | "What architecture did we use in my other project?" refused with project-switch guidance. | `AssistantQueryClassifier.classify_scope` returns canonical project switch prompt. | **COMPLIANT** |
| **Secret Information Redaction** | Passwords, JWT keys, API tokens (`sk-`, `ghp_`, `xoxb-`), private keys masked. | `AssistantAnswerValidator._redact_secrets` replaces tokens with `[REDACTED_SECRET]`. | **COMPLIANT** |
| **Prompt Injection Defense** | System prompts cannot be extracted; override commands in documents are treated as untrusted data. | Pre-flight jailbreak filter + `<project_evidence>` untrusted XML boundaries + prompt marker sanitizer. | **COMPLIANT** |
| **Agent & Worker Isolation** | Dynamic workers inherit immutable ProjectContext; cannot target foreign projects. | `DynamicAgentWorker._project_ctx` is read-only; cross-project execution raises `ForbiddenError`. | **COMPLIANT** |
| **Tool Execution Boundaries** | ToolRegistry rejects foreign project arguments, host paths, or unapproved actions. | `ToolRegistry.execute_tool` validates project argument and blocks host filesystem traversal. | **COMPLIANT** |
| **SSE & Investigation Isolation** | Investigation streams and checkpoints cannot be accessed across project boundaries. | Routes `/investigations/{id}/events` and `/investigations/{id}` verify `state.project_id == project_id`. | **COMPLIANT** |
| **Honest Epistemic Disclosure** | Missing or unsupported facts are acknowledged without fabricating contributors or approvals. | Status set to `insufficient_evidence` with explicit uncertainty statement. | **COMPLIANT** |

---

## 2. Modified & Verified Files Summary

1. `backend/app/schemas/assistant.py`:
   - Added `project_id: uuid.UUID | None` to `AssistantCitationResponse` for provenance verification.
2. `backend/app/services/assistant_query.py`:
   - Added `is_out_of_scope`, `out_of_scope_category`, `refusal_reason` to `ClassifiedQuery`.
   - Implemented `AssistantQueryClassifier.classify_scope()` detecting personal device, cross-project, personal background, platform secret, and prompt injection queries.
3. `backend/app/services/assistant.py`:
   - Added pre-retrieval guardrail gate in `ask_question()`: short-circuits out-of-scope inquiries immediately with `UNSUPPORTED_QUERY` and canonical compliant text.
   - Passed `active_project_id=project_ctx.project.id` to `self.validator.validate()`.
4. `backend/app/services/assistant_llm.py`:
   - Enhanced `_BASE_SAFEGUARDS` with Section 5 (Strict Project Boundary & Personal Data Non-Disclosure).
   - Cleaned deterministic fallbacks for empty citations and standard mode.
5. `backend/app/services/assistant_validation.py`:
   - Implemented `_redact_secrets()`, `_sanitize_prompt_injections()`, `_sanitize_personal_hardware_leakage()`.
   - Added active project ID provenance filter dropping foreign citations.
   - Enforced sanitization on all exit paths.
6. `backend/app/services/ai/agent_factory.py`:
   - Enforced immutable `_project_ctx` and cross-project task rejection (`CROSS_PROJECT_AGENT_FORBIDDEN`).
7. `backend/app/services/ai/tools.py`:
   - Added `PROJECT_CONTEXT_REQUIRED`, `CROSS_PROJECT_TOOL_FORBIDDEN`, and `ENV_INSPECTION_FORBIDDEN` checks.
8. `backend/app/services/ai/memory.py`:
   - Added `clear_project_memory()` and workstation hardware sanitization in `record_derived_insight()`.
9. `backend/app/services/ai/orchestrator.py`:
   - Added short-circuit completion for out-of-scope queries in `run_investigation()`.
   - Passed `active_project_id` to validator.
10. `backend/app/api/routes/assistant.py`:
    - Added project identity check in `stream_investigation_events()` preventing cross-project SSE eavesdropping.
11. `frontend/src/components/assistant/AssistantWorkspaceView.tsx`:
    - Updated quick questions to general project questions; preserved in-memory messages during message loads.
12. `frontend/src/__tests__/AssistantWorkspaceRedesign.test.tsx`:
    - Updated test expectations to match general quick questions; verified all 6 UI tests pass.
13. `backend/tests/test_assistant_project_guardrails.py`:
    - Authoritative 15-test security suite covering all test groups A through G.

---

## 3. Final Acceptance Verdict

**PASS — PROJECT SCOPE AND DISCLOSURE GUARDRAILS VERIFIED.**
