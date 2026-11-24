# Project Context Isolation Implementation
## Intelligent Project Knowledge Reconstruction & Handover Platform ("The Handover")
### Technical Enforcement of Single Active Project Context

---

## 1. Project Context Invariant

Every assistant operation must have an explicitly resolved, trusted `ProjectContext`. The platform never relies on client-supplied claims or LLM-generated project identifiers.

### Data Model & Invariant:
```python
class ProjectContext:
    principal: AuthenticatedPrincipal      # User identity, session family, system roles
    organisation: Organisation              # Verified parent tenant
    organisation_membership: OrganisationMembership
    organisation_role: Role
    project: Project                        # The single active authorized project
    project_membership: ProjectMembership   # Active membership verification
    project_role: Role
    permissions: frozenset[str]             # Explicitly calculated project permission set
```

---

## 2. Request Lifecycle & Project Binding

1. **Path Parameter Binding & Authentication**:
   - HTTP routes follow `/api/v1/projects/{project_id}/assistant/...`.
   - The FastAPI dependency `require_project_permission("assistant.chat")` intercepts the request:
     - Verifies JWT access token and session validity.
     - Fetches active project by `project_id`.
     - Validates that the caller is an active member of `project_id`.
     - Computes the user's role and granular permissions.
     - If the user is not a project member, raises `403 Forbidden` (`PROJECT_ACCESS_DENIED`).
2. **Short-Circuit Query Scope Evaluation**:
   - In `AssistantQueryClassifier.classify_scope()`, incoming questions are inspected before any database or vector store operations:
     - Questions asking about other projects (e.g., *"What architecture did we use in my other project?"*) trigger immediate compliant refusal:
       > *"I can only access information from the currently selected project. Please switch to the relevant project if you have permission to access it."*
     - Questions asking about personal devices, hardware, or workstation specifications trigger immediate refusal:
       > *"I'm here to assist with the currently selected Handover project. I don't provide personal device or environment information through the Project Knowledge Assistant."*
     - No retrieval is executed; zero token consumption; zero leakage surface.
3. **Multi-Source Retrieval Scoping**:
   - In `AssistantRetrievalService.retrieve()`:
     - PostgreSQL Full-Text Search: `KnowledgeItem.project_id == project_ctx.project.id`
     - Evidence Chunks: `EvidenceChunk.project_id == project_ctx.project.id`
     - ChromaDB Vector Store: `where={"project_id": str(project_ctx.project.id)}`
     - Post-retrieval revalidation: Ensures every hit's `project_id` matches `project_ctx.project.id`.
     - Delegated Source Permissions: `SourceAccessPolicyService` filters out repositories or Jira boards the user does not have personal authorization to view.
4. **Investigation Runtime & SSE Stream Isolation**:
   - In `/projects/{project_id}/assistant/investigations/{investigation_id}/events`:
     - Verifies that `state.project_id == project_id`.
     - If an investigation belongs to another project, immediately raises `ForbiddenError("Investigation belongs to another project.", code="FORBIDDEN_INVESTIGATION")`.
     - Reconnection cursors (`Last-Event-ID`) cannot be used to bridge across projects.

---

## 3. Frontend Project Switch Workflow

In `frontend/src/components/assistant/AssistantWorkspaceView.tsx`:
```typescript
useEffect(() => {
  setActiveConversationId(null);
  setMessages([]);
  setLiveInvestigationStage(null);
  setLiveInvestigationEvents([]);
  setLiveStreamingAnswer("");
  loadConversations(true);
}, [activeProject?.id]);
```
When the user switches the active project in the workspace header:
- Active conversation ID is immediately cleared.
- In-memory messages and citations are purged.
- Ephemeral SSE investigation streams are closed.
- Conversations are re-queried strictly for the new `activeProject.id`.
- Stale conversation IDs from the previous project fail closed with 404/reset.
