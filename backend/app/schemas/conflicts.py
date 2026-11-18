"""Pydantic v2 schemas for the Conflict Management Workspace."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import BaseSchema


# ---------------------------------------------------------------------------
# Dashboard Summary & Metrics
# ---------------------------------------------------------------------------


class ConflictDashboardMetrics(BaseSchema):
    """Aggregated metrics for the Conflict Management Dashboard."""

    project_id: uuid.UUID
    total_conflicts: int = 0
    open_conflicts: int = 0
    under_investigation: int = 0
    awaiting_context: int = 0
    resolved: int = 0
    reopened: int = 0
    critical_priority: int = 0
    high_priority: int = 0
    medium_priority: int = 0
    low_priority: int = 0
    category_counts: dict[str, int] = Field(default_factory=dict)
    attention_required_count: int = 0


# ---------------------------------------------------------------------------
# Queue Listing & Filtering
# ---------------------------------------------------------------------------


class ConflictQueueItem(BaseSchema):
    """Compact conflict representation for the Left Investigation Queue."""

    id: uuid.UUID
    project_id: uuid.UUID
    case_id: uuid.UUID
    conflict_type: str
    priority: str
    resolution_state: str
    explanation: str
    temporal_comparison: str
    side_a_title: str | None = None
    side_a_provider: str | None = None
    side_b_title: str | None = None
    side_b_provider: str | None = None
    assigned_reviewer_id: uuid.UUID | None = None
    assigned_reviewer_name: str | None = None
    related_finding_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class ConflictListResponse(BaseSchema):
    """Paginated list of conflicts with filter counters."""

    items: list[ConflictQueueItem]
    total_count: int
    offset: int
    limit: int


# ---------------------------------------------------------------------------
# Side-by-Side Detailed Comparison
# ---------------------------------------------------------------------------


class ConflictEvidenceSide(BaseSchema):
    """Structured details for one side of the contradiction."""

    title: str
    provider: str | None = None
    claim_text: str
    evidence_item_id: uuid.UUID | None = None
    chunk_id: uuid.UUID | None = None
    source_timestamp: datetime | None = None
    source_url: str | None = None
    author: str | None = None
    acl_scope: str = "project_members"
    is_accessible: bool = True
    redaction_reason: str | None = None


class ConflictAuditHistoryItem(BaseSchema):
    """Historical timeline event for an investigated conflict."""

    id: uuid.UUID
    action: str
    actor_id: uuid.UUID | None = None
    actor_name: str | None = None
    notes: str | None = None
    created_at: datetime


class ConflictDetailResponse(BaseSchema):
    """Deep investigative view for a single contradiction."""

    id: uuid.UUID
    project_id: uuid.UUID
    case_id: uuid.UUID
    conflict_type: str
    priority: str
    resolution_state: str
    explanation: str
    temporal_comparison: str

    side_a: ConflictEvidenceSide
    side_b: ConflictEvidenceSide

    assigned_reviewer_id: uuid.UUID | None = None
    assigned_reviewer_name: str | None = None
    investigation_notes: str | None = None

    resolution_strategy: str | None = None
    authoritative_claim_text: str | None = None
    resolution_notes: str | None = None
    resolved_by_user_id: uuid.UUID | None = None
    resolved_by_user_name: str | None = None
    resolved_at: datetime | None = None

    related_finding_id: uuid.UUID | None = None
    related_finding_title: str | None = None
    finding_domain: str | None = None

    created_at: datetime
    updated_at: datetime
    audit_history: list[ConflictAuditHistoryItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Human Reviewer Action Requests
# ---------------------------------------------------------------------------


class AssignConflictReviewerRequest(BaseSchema):
    """Assign or unassign an investigator to a conflict."""

    reviewer_id: uuid.UUID | None = None
    notes: str | None = None


class StartInvestigationRequest(BaseSchema):
    """Move conflict to under_investigation state."""

    notes: str | None = None


class RequestConflictContextRequest(BaseSchema):
    """Request additional context or evidence from project members."""

    context_queries: list[str] = Field(default_factory=list)
    notes: str | None = None


class AddInvestigationNotesRequest(BaseSchema):
    """Record an internal investigator note."""

    notes: str


class ResolveConflictRequest(BaseSchema):
    """Formally resolve a contradiction with an authoritative determination."""

    resolution_strategy: str
    resolution_notes: str
    authoritative_claim_text: str | None = None
    sync_finding: bool = True


class ReopenConflictRequest(BaseSchema):
    """Reopen a previously resolved contradiction upon new contradictory findings."""

    reason: str
