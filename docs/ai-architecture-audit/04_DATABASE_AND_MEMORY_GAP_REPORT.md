# Database & Memory Gap Report — Phase AI-0

**Platform**: The Handover (Intelligent Project Knowledge Reconstruction & Handover Platform)  
**Document**: Document 4 of 7 — Comprehensive AI Architecture & Existing-System Audit  
**Phase**: Phase AI-0 (Audit & Integration Feasibility)  
**Date**: November 2026  

---

## 1. Existing Database Schema & Migration Baseline

The platform's canonical database is **PostgreSQL 16** managed via Alembic. The repository contains 20 sequential migrations:

```text
20261111_0001_initial_baseline.py
20261111_0002_auth_identity_rbac.py
20261111_0003_org_project_workspaces.py
20261111_0004_evidence_ingestion.py
20261111_0005_source_integrations.py
20261112_0006_evidence_chunks_and_fts.py
20261112_0007_knowledge_reconstruction.py
20261112_0008_project_transitions_and_workspace_rbac.py
20261113_0009_supabase_auth_and_vector_indexes.py
20261113_0010_knowledge_domains.py
20261113_0011_relationship_explorer.py
20261113_0012_verification_center.py
20261113_0013_handover_workspace.py
20261113_0014_handover_rbac.py
20261113_0015_assistant_workspace.py            <-- Core Assistant Tables Created Here
20261113_0016_rls_hardening.py                  <-- Comprehensive RLS Policies
20261115_0017_password_reset_tokens.py
20261115_0018_project_invitations.py
20261116_0019_connected_sources_and_evidence.py
20261116_0020_knowledge_graphs_and_contributor_review.py
```

### Existing Assistant Tables (Migration `0015`)

1. **`assistant_conversations`**:
   - `id` (UUID PK), `organisation_id` (FK), `project_id` (FK), `created_by_user_id` (FK)
   - `title` (VARCHAR 255), `status` (VARCHAR 32, e.g. 'active', 'archived')
   - `created_at`, `updated_at`, `last_message_at`
   - Indexes on `(project_id, created_by_user_id)`, `(project_id, status)`, `(project_id, last_message_at)`.
2. **`assistant_messages`**:
   - `id` (UUID PK), `conversation_id` (FK CASCADE), `organisation_id` (FK), `project_id` (FK)
   - `sender_type` (VARCHAR 32: 'user' / 'assistant' / 'system')
   - `content` (TEXT), `answer_status` (VARCHAR 32: 'answered', 'partially_answered', etc.)
   - `structured_payload_json` (JSONB: claims, uncertainty, conflicts, research_report, deep_think, deep_extract)
   - `model_name`, `prompt_tokens`, `completion_tokens`, `duration_ms`
   - `retrieval_run_id` (FK SET NULL), `created_at`
3. **`assistant_citations`**:
   - `id` (UUID PK), `message_id` (FK CASCADE), `organisation_id` (FK), `project_id` (FK)
   - `citation_label` (VARCHAR 16: 'S1', 'S2'), `citation_order` (INTEGER)
   - `evidence_id` (FK), `chunk_id` (FK), `knowledge_item_id` (FK)
   - `source_title`, `source_provider`, `source_url`, `section_title`, `page_number`, `excerpt`, `is_verified`
4. **`assistant_retrieval_runs`**:
   - Diagnostic audit log tracking `query_text`, `query_type`, `retrieval_mode`, `candidates_found`, `candidates_authorized`, `duration_ms`, `diagnostics_json`
5. **`assistant_feedback`**:
   - User feedback tracking `helpful` / `unhelpful` ratings and comments per message turn.

---

## 2. Proposed Entity Mapping & Gap Analysis

The table below maps the entities required by the **Project Intelligence Engine** against existing database structures:

| Proposed Architectural Entity | Existing Table / Model | Status | Required Change / Recommendation |
|---|---|---|---|
| **Conversation Threads** | `assistant_conversations` | **Existing & Reusable** | Fully adequate. Add `active_mode` and `pinned` flag if desired. |
| **Message Turns** | `assistant_messages` | **Existing & Reusable** | Fully adequate. `structured_payload_json` easily holds agent traces and plan trees. |
| **Source Citations** | `assistant_citations` | **Existing & Reusable** | Fully adequate. Preserves full provenance and external URLs. |
| **Retrieval Diagnostics** | `assistant_retrieval_runs` | **Existing & Reusable** | Fully adequate for RAG telemetry and latency auditing. |
| **Investigation State & Checkpoints** | None | **Missing** | **New Table Needed**: `assistant_investigations` to save multi-step graph state, active agent, pending approval, and pause/resume checkpoints. |
| **Dynamic Agent Execution Runs** | None | **Missing** | **New Table Needed**: `assistant_agent_runs` to log individual dynamic agent execution turns, scratchpads, and token usage. |
| **Tool Execution Audits** | None | **Missing** | **New Table Needed**: `assistant_tool_executions` to track tool name, parameters, execution outcome, user approval, and authorization checks. |
| **Persistent Working Memory** | `knowledge_items` (8 domains) | **Existing but Requires Improvement** | Current items are static extractions. Propose `assistant_project_memories` for evolving project insights synthesized by AI. |
| **Approval Requests** | Handover signoffs (`handover_signoffs`) | **Existing but Requires Improvement** | Reuse approval workflow concepts to create `assistant_tool_approvals` for conversational actions. |

---

## 3. Proposed Schema Additions (Future Migration `0021`)

To support multi-step graph orchestration and interactive tool approvals without bloating existing tables, the following relational structures are recommended for the next database migration:

```sql
-- 1. Multi-Step Investigation Checkpoints
CREATE TABLE assistant_investigations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES assistant_conversations(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    created_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(32) NOT NULL DEFAULT 'running', -- 'running', 'waiting_approval', 'completed', 'failed', 'cancelled'
    investigation_goal TEXT NOT NULL,
    current_step VARCHAR(64) NOT NULL,
    graph_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Dynamic Agent Execution Traces
CREATE TABLE assistant_agent_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id UUID NOT NULL REFERENCES assistant_investigations(id) ON DELETE CASCADE,
    agent_name VARCHAR(64) NOT NULL, -- e.g. 'EngineeringAgent', 'DecisionAgent'
    agent_role VARCHAR(128) NOT NULL,
    input_scratchpad JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_findings JSONB NOT NULL DEFAULT '{}'::jsonb,
    prompt_tokens INT,
    completion_tokens INT,
    duration_ms INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Tool Execution & Human Approval Records
CREATE TABLE assistant_tool_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id UUID REFERENCES assistant_investigations(id) ON DELETE SET NULL,
    message_id UUID REFERENCES assistant_messages(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tool_name VARCHAR(64) NOT NULL,
    arguments_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    execution_result_json JSONB,
    is_consequential BOOLEAN NOT NULL DEFAULT FALSE,
    approval_status VARCHAR(32) NOT NULL DEFAULT 'not_required', -- 'not_required', 'pending', 'approved', 'rejected'
    approved_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    approved_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 4. Row-Level Security (RLS) Requirements

In accordance with Migration `20261113_0016_rls_hardening.py`, any new tables added to PostgreSQL **must** enforce strict tenant and project isolation:

1. **`ALTER TABLE <new_table> ENABLE ROW LEVEL SECURITY;`**
2. **Force RLS for all table owners and roles**: `ALTER TABLE <new_table> FORCE ROW LEVEL SECURITY;`
3. **Project Membership Policy**: Access restricted strictly to users where:
   ```sql
   project_id IN (
       SELECT project_id FROM project_members WHERE user_id = auth.uid()
   )
   ```
4. **Conversation Creator Isolation**: Investigations and agent runs must only be visible to the user who created the conversation, unless the user holds `assistant.admin` / `project.manage` permissions.

---

## 5. Migration Execution Gate (Read-Only Enforcement)

> [!CAUTION]
> **Database Security Gate Active**: As per the rules of this audit, **NO MIGRATIONS WILL BE EXECUTED**.
> The database schema remains unchanged. The proposed schemas above represent the integration roadmap for Phase AI-1/AI-2 after technical review and explicit approval.
