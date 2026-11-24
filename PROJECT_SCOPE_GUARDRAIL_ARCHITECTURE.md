# Project Scope Guardrail Architecture
## Intelligent Project Knowledge Reconstruction & Handover Platform ("The Handover")
### Module 5: Project Knowledge Assistant — Security & Scope Boundaries

---

## 1. Executive Summary & Core Identity

The **Project Knowledge Assistant** is an intelligent reasoning agent strictly limited to assisting authorized team members, successors, and reviewers with the **currently selected, active project** inside **The Handover**.

### Absolute System Boundaries:
- **Project-Bound Only**: The assistant's epistemic horizon is strictly bounded to authorized project records, documents, code, issues, and decisions belonging to the active project.
- **Not a Personal Assistant**: It does not answer questions regarding the user's personal life, device specifications, hardware environment, or private background.
- **Not a Cross-Project Search Engine**: It cannot access, combine, or disclose records from other projects owned by the same user or within the organization without an explicit project switch and re-authorization.
- **Not an Infrastructure Oracle**: Platform secrets, internal infrastructure configurations, and confidential credentials cannot be disclosed.

This architecture applies universally to every execution mode: **Standard**, **Deep Research**, **Deep Think**, **Deep Extract**, specialized workers, tools, retrieval, and background orchestrations.

---

## 2. Multi-Layer Defense-in-Depth Architecture

```text
 ┌────────────────────────────────────────────────────────────────────────┐
 │                           USER QUERY INGESTION                         │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │ LAYER 1: Pre-Flight Scope & Guardrail Classifier                       │
 │  - Detects personal device queries ("What GPU does my laptop have?")   │
 │  - Detects cross-project inquiries ("What did we use in other proj?")  │
 │  - Detects personal background ("What course am I studying?")          │
 │  - Detects prompt injections ("Ignore previous instructions...")       │
 │  - Detects platform secrets probing ("What is the JWT secret?")        │
 │  ==> SHORT-CIRCUITS IMMEDIATELY with canonical compliant refusal       │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │ (If In-Scope)
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │ LAYER 2: Backend-Authorized Immutable ProjectContext                   │
 │  - Principal authentication (FastAPI-managed Argon2id / JWT)           │
 │  - Active project membership & RBAC permission verification            │
 │  - Immutable context passing: (organisation_id, project_id, user_id)   │
 │  - Rejects foreign project IDs & untrusted client parameters           │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │ LAYER 3: Strict Project-Scoped Retrieval & Source ACL Filtering        │
 │  - PostgreSQL: WHERE project_id = :active_project_id                   │
 │  - ChromaDB: where={"project_id": str(active_project_id)}              │
 │  - Hybrid fusion: Re-validates every semantic hit against PostgreSQL   │
 │  - SourceAccessPolicyService: Enforces delegated repository/Jira ACLs  │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │ LAYER 4: Model System Instructions & Untrusted Data Boundaries         │
 │  - Treats all <project_evidence> as untrusted historical data          │
 │  - Anti-injection directive: Disregards embedded override instructions │
 │  - Anti-leakage directive: Forbids workstation hardware disclosure     │
 │  - Epistemic disclosure: Expresses uncertainty if records lack answers │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │ LAYER 5: Post-Generation Output Validation & Redaction Pipeline        │
 │  - Active Project ID Provenance: Filters out foreign citations         │
 │  - Workstation Hardware Leakage Detector: Scrubs RTX 4050, RAM, paths  │
 │  - Secret Information Redactor: Masks API keys, JWTs, private keys     │
 │  - Epistemic Status Validator: Downgrades ungrounded claims            │
 └────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Epistemic Classification & Information Taxonomy

All information processed or emitted by the Project Knowledge Assistant is classified under five strict data classifications:

| Classification | Definition | Allowed Access | Assistant Disclosure Rule |
| :--- | :--- | :--- | :--- |
| **PUBLIC_PROJECT_INFORMATION** | Non-sensitive project overviews, public repos, general architectural patterns. | Project members | Allowed with supporting evidence attribution. |
| **INTERNAL_PROJECT_INFORMATION** | Internal sprint tasks, ADRs, contributor ownership, risk registers. | Active project members | Allowed with source citation verification. |
| **RESTRICTED_PROJECT_INFORMATION** | Restricted documents, private repository code, protected Jira tickets. | Members with delegated source authorization | Filtered at retrieval time; blocked if unpermitted. |
| **PERSONAL_INFORMATION** | Developer workstation hardware, personal history, device specifications, IP/location. | Disallowed | **Strictly prohibited**. Replaced by guardrail refusal. |
| **SECRET_INFORMATION** | JWT secrets, database passwords, API tokens (`sk-`, `ghp_`, `xoxb-`), private keys. | Platform administration | **Strictly prohibited**. Redacted to `[REDACTED_SECRET]`. |

---

## 4. Architectural Guarantees

1. **Zero Cross-Project Information Contamination**:
   - Every database query in `AssistantRetrievalService` explicitly filters by `project_id`.
   - ChromaDB HTTP queries enforce isolated collection namespaces and explicit metadata filtering by `project_id`.
   - All vector search candidates are re-verified against PostgreSQL canonical records before inclusion in prompt context.
2. **Workstation Hardware Independence**:
   - The platform never exposes local workstation specs (e.g., NVIDIA GeForce RTX 4050, 6GB VRAM, HP Victus, local disk paths) as project architecture facts.
   - Legitimate deployment hardware (e.g. cloud inference clusters) must be explicitly documented in verified project records to be discussed.
3. **Fail-Closed Execution**:
   - In any scenario where project context cannot be established, permissions are missing, or credentials are unverified, the system fails closed with `403 Forbidden` or `UNSUPPORTED_QUERY`.
