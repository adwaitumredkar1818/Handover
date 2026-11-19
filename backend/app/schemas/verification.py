"""Pydantic v2 schemas for the Verification Center (Phase 1 Rebuild)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from app.schemas.common import BaseSchema


# ---------------------------------------------------------------------------
# Summary & Queue
# ---------------------------------------------------------------------------


class VerificationSummaryResponse(BaseSchema):
    """Project-wide verification status counts and review metrics."""

    project_id: uuid.UUID
    total_cases: int = 0
    candidate_count: int = 0
    pending_review_count: int = 0
    conflicted_count: int = 0
    unresolved_count: int = 0
    verified_count: int = 0
    rejected_count: int = 0
    open_issues_count: int = 0
    open_conflicts_count: int = 0
    pending_context_requests_count: int = 0


class VerificationQueueItem(BaseSchema):
    """Compact queue entry displayed in the Left Panel (Findings Queue)."""

    id: uuid.UUID
    project_id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    title: str
    domain: str
    current_claim: str
    original_ai_claim: str
    case_status: str
    priority: str
    person_name: str | None = None
    source_provider: str | None = None
    assigned_reviewer_id: uuid.UUID | None = None
    assigned_reviewer_name: str | None = None
    evidence_count: int = 0
    open_issues_count: int = 0
    verification_categories: list[str] = Field(default_factory=list)
    model_confidence: float | None = None
    uncertainty_note: str | None = None
    evidence_completeness: str | None = None
    priority_reason: str | None = None
    recommendation_action: str | None = None
    corroboration_level: str | None = None
    freshness_status: str | None = None
    version: int = 1
    last_reviewed_at: datetime | None = None
    updated_at: datetime
    created_at: datetime


class VerificationQueueResponse(BaseSchema):
    """Paginated findings queue with filter metadata."""

    items: list[VerificationQueueItem] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0
    available_domains: list[str] = Field(default_factory=list)
    available_sources: list[str] = Field(default_factory=list)
    available_people: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Centre Panel: Evidence, Issues, Conflicts, Revisions, History
# ---------------------------------------------------------------------------


class EvidenceReferenceDetail(BaseSchema):
    """ACL-checked source evidence reference displayed in Panel B."""

    id: uuid.UUID
    evidence_item_id: uuid.UUID
    evidence_chunk_id: uuid.UUID | None = None
    source_provider: str
    source_name: str
    original_title: str
    author: str | None = None
    timestamp: datetime | None = None
    original_source_url: str | None = None
    excerpt: str | None = None
    location_label: str | None = None
    relationship_to_finding: str
    acl_scope: str = "project_members"


class VerificationIssueDetail(BaseSchema):
    """Automated verification issue across the 6 canonical review categories."""

    id: uuid.UUID
    verification_category: str
    issue_type: str
    severity: str
    description: str
    detection_method: str
    resolution_state: str
    details: dict[str, Any] = Field(default_factory=dict)
    conflicting_evidence_id: uuid.UUID | None = None
    created_at: datetime
    resolved_at: datetime | None = None


class ConflictClaimSide(BaseSchema):
    """One side of a side-by-side opposing source comparison."""

    evidence_item_id: uuid.UUID
    source_provider: str
    original_title: str
    author: str | None = None
    timestamp: datetime | None = None
    original_source_url: str | None = None
    claim_text: str


class VerificationConflictPreview(BaseSchema):
    """Side-by-side opposing source claims rendered inside Panel B."""

    id: uuid.UUID
    conflict_type: str
    explanation: str
    temporal_comparison: str
    resolution_state: str
    side_a: ConflictClaimSide | None = None
    side_b: ConflictClaimSide | None = None
    restricted_by_acl: bool = False
    created_at: datetime


class VerificationRevisionDetail(BaseSchema):
    """Immutable revision record preserving AI original and human edits."""

    id: uuid.UUID
    revision_number: int
    claim_text: str
    domain: str
    is_ai_original: bool
    edited_by_user_id: uuid.UUID | None = None
    edited_by_name: str | None = None
    edit_reason: str | None = None
    created_at: datetime


class VerificationReviewEventDetail(BaseSchema):
    """Immutable human review action record."""

    id: uuid.UUID
    reviewer_user_id: uuid.UUID
    reviewer_name: str | None = None
    action: str
    previous_status: str
    new_status: str
    case_version: int
    decision_reason: str | None = None
    review_notes: str | None = None
    created_at: datetime


class VerificationContextRequestDetail(BaseSchema):
    """Clarification request sent to a project member / knowledge owner."""

    id: uuid.UUID
    case_id: uuid.UUID
    requested_by_user_id: uuid.UUID
    requested_by_name: str | None = None
    requested_from_user_id: uuid.UUID
    requested_from_name: str | None = None
    question: str
    requested_information_type: str
    status: str
    response_text: str | None = None
    response_evidence_id: uuid.UUID | None = None
    responded_at: datetime | None = None
    created_at: datetime


class VerificationCaseDetailResponse(BaseSchema):
    """Complete Centre + Right panel payload for a selected finding."""

    id: uuid.UUID
    project_id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    title: str
    domain: str
    original_ai_claim: str
    current_claim: str
    case_status: str
    priority: str
    person_name: str | None = None
    source_provider: str | None = None
    assigned_reviewer_id: uuid.UUID | None = None
    assigned_reviewer_name: str | None = None
    model_confidence: float | None = None
    uncertainty_note: str | None = None
    evidence_completeness: str | None = None
    version: int
    handover_eligible: bool
    handover_eligibility_reason: str
    restricted_evidence_count: int = 0
    evidence_references: list[EvidenceReferenceDetail] = Field(default_factory=list)
    issues: list[VerificationIssueDetail] = Field(default_factory=list)
    conflicts: list[VerificationConflictPreview] = Field(default_factory=list)
    revisions: list[VerificationRevisionDetail] = Field(default_factory=list)
    review_events: list[VerificationReviewEventDetail] = Field(default_factory=list)
    context_requests: list[VerificationContextRequestDetail] = Field(default_factory=list)
    machine_assessment: dict[str, Any] = Field(default_factory=dict)
    priority_reason: str | None = None
    recommendation: dict[str, Any] | None = None
    completeness_assessment: dict[str, Any] | None = None
    reliability_assessment: dict[str, Any] | None = None
    freshness_assessment: dict[str, Any] | None = None
    corroboration_assessment: dict[str, Any] | None = None
    contradiction_analysis: dict[str, Any] | None = None
    monitoring_status: dict[str, Any] | None = None
    last_assessed_at: datetime | None = None
    last_reviewed_at: datetime | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Action Payloads (Right Panel)
# ---------------------------------------------------------------------------


def _require_non_empty(value: str, field_label: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_label} is required and cannot be empty.")
    return cleaned


class ApproveFindingRequest(BaseSchema):
    reviewer_note: str | None = None
    decision_reason: str | None = None


class RejectFindingRequest(BaseSchema):
    decision_reason: str = Field(..., min_length=3, max_length=4000)
    reviewer_note: str | None = None

    @field_validator("decision_reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        return _require_non_empty(v, "Rejection reason")


class EditFindingRequest(BaseSchema):
    current_claim: str = Field(..., min_length=3, max_length=8000)
    domain: str | None = None
    edit_reason: str = Field(..., min_length=3, max_length=4000)
    reviewer_note: str | None = None

    @field_validator("current_claim")
    @classmethod
    def validate_claim(cls, v: str) -> str:
        return _require_non_empty(v, "Structured claim")

    @field_validator("edit_reason")
    @classmethod
    def validate_edit_reason(cls, v: str) -> str:
        return _require_non_empty(v, "Correction reason")


class RequestContextRequest(BaseSchema):
    question: str = Field(..., min_length=3, max_length=4000)
    requested_from_user_id: uuid.UUID
    requested_information_type: str = Field(default="clarification", max_length=64)
    reviewer_note: str | None = None

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        return _require_non_empty(v, "Clarification question")


class RespondContextRequest(BaseSchema):
    response_text: str = Field(..., min_length=2, max_length=8000)
    response_evidence_id: uuid.UUID | None = None
    excerpt: str | None = None

    @field_validator("response_text")
    @classmethod
    def validate_response(cls, v: str) -> str:
        return _require_non_empty(v, "Context response")


class MarkUnresolvedRequest(BaseSchema):
    decision_reason: str = Field(..., min_length=3, max_length=4000)
    reviewer_note: str | None = None

    @field_validator("decision_reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        return _require_non_empty(v, "Unresolved explanation")


class AssignReviewerRequest(BaseSchema):
    assigned_reviewer_id: uuid.UUID | None = None


class SyncAndAssessResponse(BaseSchema):
    project_id: uuid.UUID
    cases_created: int = 0
    cases_updated: int = 0
    issues_detected: int = 0
    cases_assessed: int = 0


class MonitorSourceChangeRequest(BaseSchema):
    evidence_id: uuid.UUID
    change_type: str = "modified"


class MonitorSourceChangeResponse(BaseSchema):
    evidence_id: uuid.UUID
    change_type: str
    affected_case_ids: list[uuid.UUID] = Field(default_factory=list)
    reverification_triggered: bool = False
    summary: str


class ChangeImpactEventItem(BaseSchema):
    case_id: uuid.UUID
    finding_title: str
    domain: str
    current_claim: str
    case_status: str
    priority: str
    evidence_id: uuid.UUID | None = None
    evidence_title: str
    evidence_source_type: str
    evidence_url: str | None = None
    change_type: str
    reverification_triggered: bool = False
    reverification_reason: str | None = None
    impact_summary: str
    impact_nature: str = "confirmed"
    timestamp: str | None = None


class ChangeImpactFeedResponse(BaseSchema):
    project_id: uuid.UUID
    total: int = 0
    items: list[ChangeImpactEventItem] = Field(default_factory=list)
