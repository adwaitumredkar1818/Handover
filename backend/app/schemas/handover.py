"""Pydantic v2 schemas for Handover Workspace APIs.

Platform: The Handover
Module: Handover Workspace (Module 4 / Knowledge Transfer Area)
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class HandoverCaseCreateRequest(BaseModel):
    """Create a new handover case for a project."""

    title: str = Field(..., min_length=3, max_length=300)
    description: str | None = Field(None, max_length=5000)
    departing_member_id: uuid.UUID
    successor_id: uuid.UUID | None = None
    handover_type: str = Field(
        default="developer",
        pattern="^(developer|project_manager|technical_lead)$",
    )
    target_handover_date: date | None = None
    metadata_json: dict[str, Any] | None = None


class HandoverCaseUpdateRequest(BaseModel):
    """Update mutable fields of a handover case."""

    title: str | None = Field(None, min_length=3, max_length=300)
    description: str | None = Field(None, max_length=5000)
    successor_id: uuid.UUID | None = None
    handover_type: str | None = Field(
        default=None,
        pattern="^(developer|project_manager|technical_lead)$",
    )
    target_handover_date: date | None = None
    metadata_json: dict[str, Any] | None = None


class HandoverContextContributionRequest(BaseModel):
    """Departing member or team member contributes missing context as unverified candidate evidence."""

    title: str = Field(..., min_length=3, max_length=300)
    content: str = Field(..., min_length=5, max_length=10000)
    category: str = Field(default="decisions_rationale", max_length=64)
    rationale: str | None = Field(None, max_length=4000)


class PackageAssemblyRequest(BaseModel):
    """Request assembly of a new package version."""

    assembly_notes: str | None = Field(None, max_length=2000)
    include_domains: list[str] | None = None
    exclude_knowledge_item_ids: list[uuid.UUID] | None = None
    exclude_relationship_ids: list[uuid.UUID] | None = None


class ReadinessAssessmentRequest(BaseModel):
    """Request a readiness assessment for a package version."""

    version_id: uuid.UUID
    notes: str | None = Field(None, max_length=2000)


class ChecklistItemCreateRequest(BaseModel):
    """Create a custom transition checklist item within an existing checklist."""

    item_text: str = Field(..., min_length=3, max_length=1000)
    description: str | None = Field(None, max_length=2000)
    completion_criteria: str | None = Field(None, max_length=2000)
    category: str = Field("general", max_length=64)
    blocking: bool = False
    assigned_to_user_id: uuid.UUID | None = None
    due_date: datetime | None = None
    evidence_item_id: uuid.UUID | None = None


class ChecklistItemUpdateRequest(BaseModel):
    """Update status, assignment, due date, notes, evidence, or reopen a checklist item."""

    status: str | None = None
    notes: str | None = Field(None, max_length=2000)
    description: str | None = Field(None, max_length=2000)
    completion_criteria: str | None = Field(None, max_length=2000)
    assigned_to_user_id: uuid.UUID | None = None
    clear_assignee: bool = False
    due_date: datetime | None = None
    clear_due_date: bool = False
    evidence_item_id: uuid.UUID | None = None
    clear_evidence: bool = False
    blocking: bool | None = None
    reopen_reason: str | None = Field(None, max_length=2000)
    expected_version: int | None = None


class ChecklistItemReviewRequest(BaseModel):
    """Independent reviewer verification or reopening of a completed checklist item."""

    approved: bool = True
    review_notes: str | None = Field(None, max_length=2000)
    expected_version: int | None = None


class SignoffRequest(BaseModel):
    """Submit a sign-off decision tied to an exact package version and optional SHA-256 hash."""

    version_id: uuid.UUID
    signoff_type: str
    decision: str
    comments: str | None = Field(None, max_length=5000)
    conditions: str | None = Field(None, max_length=2000)
    affected_sections: list[str] = Field(default_factory=list)
    expected_content_hash: str | None = Field(None, max_length=64)
    expected_case_version: int | None = None


class ReviewerAssignRequest(BaseModel):
    """Assign or reassign an eligible independent reviewer to a handover case."""

    reviewer_user_id: uuid.UUID
    reason: str | None = Field(None, max_length=2000)
    expected_case_version: int | None = None


class SignoffPhaseReopenRequest(BaseModel):
    """Explicitly reopen an approved/decided signoff phase with mandatory audit rationale."""

    signoff_type: str
    reason: str = Field(..., min_length=5, max_length=2000)
    expected_case_version: int | None = None


class DeliveryRequest(BaseModel):
    """Publish and deliver an approved package version to eligible recipients."""

    version_id: uuid.UUID
    deliver_to_user_ids: list[uuid.UUID] = Field(..., min_length=1)
    delivery_method: str = "internal_download"
    message: str | None = Field(None, max_length=2000)
    expires_in_days: int | None = Field(None, ge=1, le=365)
    expected_content_hash: str | None = Field(None, max_length=64)
    expected_case_version: int | None = None


class AcknowledgementRequest(BaseModel):
    """Submit formal recipient acknowledgement for a published handover package delivery."""

    acknowledgement_notes: str | None = Field(None, max_length=5000)
    confirmations: dict[str, bool] = Field(default_factory=dict)
    expected_content_hash: str | None = Field(None, max_length=64)


class DeliveryClarificationRequest(BaseModel):
    """Recipient clarification request or outgoing/manager response on a published handover."""

    notes: str = Field(..., min_length=3, max_length=2000)
    mode: str = Field("request", pattern="^(request|response)$")


class ResponsibilityTransferRequest(BaseModel):
    """Define a responsibility transfer mapping grounded in real project context."""

    title: str | None = Field(None, min_length=3, max_length=255)
    responsibility_description: str = Field(..., min_length=5, max_length=2000)
    knowledge_domain: str | None = None
    component_name: str | None = Field(None, max_length=255)
    priority: str = Field("medium", max_length=16)
    ownership_certainty: str = Field("proposed", max_length=32)
    operational_context: str | None = Field(None, max_length=4000)
    required_access: str | None = Field(None, max_length=2000)
    effective_transfer_date: date | None = None
    current_owner_id: uuid.UUID | None = None
    proposed_successor_id: uuid.UUID | None = None
    transfer_notes: str | None = Field(None, max_length=2000)
    related_entity_id: uuid.UUID | None = None
    related_knowledge_item_id: uuid.UUID | None = None


class ResponsibilityTransferBulkRequest(BaseModel):
    """Bulk create responsibility transfer mappings."""

    transfers: list[ResponsibilityTransferRequest] = Field(..., min_length=1)


class ResponsibilityTransferUpdateRequest(BaseModel):
    """Update details, successor assignment, certainty, status, or blocker for a responsibility transfer."""

    title: str | None = Field(None, max_length=255)
    responsibility_description: str | None = Field(None, min_length=5, max_length=2000)
    knowledge_domain: str | None = Field(None, max_length=64)
    component_name: str | None = Field(None, max_length=255)
    priority: str | None = Field(None, max_length=16)
    ownership_certainty: str | None = Field(None, max_length=32)
    operational_context: str | None = Field(None, max_length=4000)
    required_access: str | None = Field(None, max_length=2000)
    effective_transfer_date: date | None = None
    clear_effective_date: bool = False
    proposed_successor_id: uuid.UUID | None = None
    clear_successor: bool = False
    transfer_status: str | None = Field(None, max_length=32)
    transfer_notes: str | None = Field(None, max_length=2000)
    blocker_reason: str | None = Field(None, max_length=2000)
    related_entity_id: uuid.UUID | None = None
    related_knowledge_item_id: uuid.UUID | None = None
    expected_version: int | None = None


class ResponsibilityOutgoingConfirmRequest(BaseModel):
    """Explicit outgoing-owner confirmation that a responsibility is prepared for transfer."""

    confirmation_notes: str | None = Field(None, max_length=2000)
    expected_version: int | None = None


class ResponsibilitySuccessorAckRequest(BaseModel):
    """Explicit receiving-successor acknowledgement of transferred context & evidence."""

    acknowledgement_notes: str | None = Field(None, max_length=2000)
    expected_version: int | None = None


class ResponsibilityClarificationRequest(BaseModel):
    """Clarification request (by successor) or clarification response (by outgoing owner)."""

    notes: str = Field(..., min_length=3, max_length=2000)
    mode: str = Field("request", pattern="^(request|response)$")
    expected_version: int | None = None


class ResponsibilityReopenRequest(BaseModel):
    """Reopen an acknowledged/completed responsibility transfer with mandatory rationale."""

    reason: str = Field(..., min_length=5, max_length=2000)
    expected_version: int | None = None


class OwnershipTransferRequest(BaseModel):
    """Execute an ownership transfer."""

    version_id: uuid.UUID
    transfer_type: str
    to_user_id: uuid.UUID
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    transfer_reason: str | None = Field(None, max_length=2000)


class OwnershipTransferRollbackRequest(BaseModel):
    """Rollback a previous ownership transfer."""

    rollback_reason: str = Field(..., min_length=5, max_length=2000)


class NarrativeDraftRequest(BaseModel):
    """Request AI-generated narrative draft for a section."""

    version_id: uuid.UUID
    section_type: str
    additional_context: str | None = Field(None, max_length=2000)


class SectionEditRequest(BaseModel):
    """Edit section content (narrative text only)."""

    section_content: str | None = None
    content_summary: str | None = Field(None, max_length=1000)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class HandoverCaseResponse(BaseModel):
    """Full handover case details."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organisation_id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str | None = None
    status: str
    version: int = 1
    departing_member_id: uuid.UUID
    successor_id: uuid.UUID | None = None
    assigned_reviewer_id: uuid.UUID | None = None
    target_handover_date: date | None = None
    handover_type: str = "developer"
    created_by_user_id: uuid.UUID
    metadata_json: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _derive_handover_type(self) -> Self:
        if self.metadata_json and isinstance(self.metadata_json, dict):
            ht = self.metadata_json.get("handover_type")
            if isinstance(ht, str) and ht in ("developer", "project_manager", "technical_lead"):
                self.handover_type = ht
        return self


class HandoverCaseListItem(BaseModel):
    """Compact handover case summary for listing."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    status: str
    version: int = 1
    departing_member_id: uuid.UUID
    successor_id: uuid.UUID | None = None
    assigned_reviewer_id: uuid.UUID | None = None
    target_handover_date: date | None = None
    handover_type: str = "developer"
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _derive_handover_type(self) -> Self:
        if self.metadata_json and isinstance(self.metadata_json, dict):
            ht = self.metadata_json.get("handover_type")
            if isinstance(ht, str) and ht in ("developer", "project_manager", "technical_lead"):
                self.handover_type = ht
        return self


class HandoverContextContributionResponse(BaseModel):
    """Result of contributing missing handover context as an unverified candidate record."""

    evidence_id: uuid.UUID
    knowledge_item_id: uuid.UUID
    verification_case_id: uuid.UUID
    epistemic_status: str
    review_status: str
    category: str
    title: str
    created_at: datetime


class HandoverPackageResponse(BaseModel):
    """Package metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class HandoverPackageVersionResponse(BaseModel):
    """Immutable package version snapshot."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    package_id: uuid.UUID
    version_number: int
    assembly_status: str | None = None
    assembly_notes: str | None = None
    notes: str | None = None
    content_hash: str | None = None
    assembly_snapshot_json: dict[str, Any] | None = None
    assembled_by_user_id: uuid.UUID | None = None
    assembled_at: datetime | None = None
    is_current: bool = False
    created_at: datetime


class HandoverSectionResponse(BaseModel):
    """Per-domain section content."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_id: uuid.UUID
    section_type: str
    section_title: str
    section_content: str | None = None
    content_summary: str | None = None
    section_order: int
    knowledge_item_count: int = 0
    relationship_count: int = 0
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class HandoverContentLinkResponse(BaseModel):
    """Link between section content and knowledge/evidence."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    section_id: uuid.UUID
    knowledge_item_id: uuid.UUID | None = None
    relationship_id: uuid.UUID | None = None
    evidence_id: uuid.UUID | None = None
    link_type: str
    eligibility_status_json: dict[str, Any] | None = None
    created_at: datetime


class HandoverEvidenceProvenanceResponse(BaseModel):
    """ACL-checked evidence provenance reference for a handover finding or relationship."""

    evidence_id: uuid.UUID
    source_type: str
    source_provider: str | None = None
    source_name: str
    source_reference: str | None = None
    source_url: str | None = None
    author: str | None = None
    source_timestamp: datetime | None = None
    extracted_at: datetime | None = None
    support_type: str = "direct"
    supporting_excerpt: str | None = None
    acl_restricted: bool = False


class HandoverVerificationSummaryResponse(BaseModel):
    """Human verification attribution for a handover knowledge item."""

    verification_case_id: uuid.UUID | None = None
    case_status: str | None = None
    reviewer_decision: str | None = None
    reviewed_by_user_id: uuid.UUID | None = None
    reviewed_by_name: str | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None


class HandoverSectionKnowledgeItemResponse(BaseModel):
    """Hydrated human-verified knowledge item linked to a handover package section."""

    id: uuid.UUID
    content_link_id: uuid.UUID
    title: str
    content: str
    category: str
    epistemic_status: str
    review_status: str
    support_classification: str
    normalised_status: str | None = None
    owner_label: str | None = None
    structured_payload: dict[str, Any] = Field(default_factory=dict)
    confidence_score: float | None = None
    is_stale: bool = False
    created_at: datetime
    updated_at: datetime
    source_observed_at: datetime | None = None
    eligibility: dict[str, Any] = Field(default_factory=dict)
    verification: HandoverVerificationSummaryResponse
    provenance: list[HandoverEvidenceProvenanceResponse] = Field(default_factory=list)
    provenance_available: bool = False


class HandoverSectionRelationshipResponse(BaseModel):
    """Hydrated verified knowledge relationship linked to a handover package section."""

    id: uuid.UUID
    content_link_id: uuid.UUID
    relationship_type: str
    source_entity_id: uuid.UUID
    source_entity_name: str
    source_entity_type: str
    target_entity_id: uuid.UUID
    target_entity_name: str
    target_entity_type: str
    verification_status: str
    confidence_score: float = 1.0
    is_stale: bool = False
    reviewed_at: datetime | None = None
    eligibility: dict[str, Any] = Field(default_factory=dict)
    provenance: list[HandoverEvidenceProvenanceResponse] = Field(default_factory=list)
    provenance_available: bool = False


class HandoverSectionConflictItemResponse(BaseModel):
    """Canonical verification conflict reference surfaced separately from verified facts."""

    id: uuid.UUID
    verification_case_id: uuid.UUID
    conflict_type: str
    priority: str
    resolution_state: str
    explanation: str
    claim_a_text: str
    claim_b_text: str
    side_a_source_title: str | None = None
    side_b_source_title: str | None = None
    authoritative_claim_text: str | None = None
    resolution_notes: str | None = None
    resolved_at: datetime | None = None
    updated_at: datetime


class HandoverDomainEpistemicBreakdown(BaseModel):
    """Transparent epistemic breakdown for a domain or package version."""

    human_verified_included: int = 0
    pending_verification: int = 0
    rejected: int = 0
    unresolved_conflicts: int = 0
    resolved_conflicts: int = 0
    outdated: int = 0


class HandoverSectionDetailResponse(HandoverSectionResponse):
    """Canonical persisted section enriched with hydrated content links and provenance."""

    content_links: list[HandoverContentLinkResponse] = Field(default_factory=list)
    knowledge_items: list[HandoverSectionKnowledgeItemResponse] = Field(default_factory=list)
    relationships: list[HandoverSectionRelationshipResponse] = Field(default_factory=list)
    unresolved_conflicts: list[HandoverSectionConflictItemResponse] = Field(default_factory=list)
    resolved_conflicts: list[HandoverSectionConflictItemResponse] = Field(default_factory=list)
    epistemic_breakdown: HandoverDomainEpistemicBreakdown = Field(
        default_factory=HandoverDomainEpistemicBreakdown
    )
    domain_context: dict[str, Any] = Field(default_factory=dict)


class HandoverMandatorySectionResponse(BaseModel):
    """Canonical 10-section role-prioritised handover structure derived from approved evidence."""

    section_number: int
    section_key: str
    section_title: str
    source_domains: list[str] = Field(default_factory=list)
    role_priority_rank: int
    is_role_priority: bool = False
    role_emphasis_note: str = ""
    readiness_status: str = "ready"
    insufficient_info_message: str | None = None
    content_markdown: str = ""
    knowledge_items: list[HandoverSectionKnowledgeItemResponse] = Field(default_factory=list)
    relationships: list[HandoverSectionRelationshipResponse] = Field(default_factory=list)
    unresolved_conflicts: list[HandoverSectionConflictItemResponse] = Field(default_factory=list)
    evidence_references: list[HandoverEvidenceProvenanceResponse] = Field(default_factory=list)
    recommended_steps: list[dict[str, Any]] = Field(default_factory=list)
    responsibilities_summary: list[dict[str, Any]] = Field(default_factory=list)
    pending_verification_count: int = 0


class HandoverVersionSectionsResponse(BaseModel):
    """Canonical response for GET /cases/{case_id}/versions/{version_id}/sections."""

    case_id: uuid.UUID
    project_id: uuid.UUID
    version: HandoverPackageVersionResponse
    sections: list[HandoverSectionDetailResponse] = Field(default_factory=list)
    missing_section_types: list[str] = Field(default_factory=list)
    epistemic_summary: HandoverDomainEpistemicBreakdown = Field(
        default_factory=HandoverDomainEpistemicBreakdown
    )
    handover_type: str = "developer"
    handover_type_label: str = "Developer Handover"
    role_focus_summary: str = ""
    mandatory_sections: list[HandoverMandatorySectionResponse] = Field(default_factory=list)


class HandoverReadinessAssessmentResponse(BaseModel):
    """Readiness assessment for a category."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_id: uuid.UUID
    category: str
    label: str | None = None
    score: int
    max_score: int = 100
    weight: float | None = None
    level: str
    blockers_json: list[str] = Field(default_factory=list)
    warnings_json: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    related_section_tab: str | None = None
    supporting_metrics: dict[str, Any] = Field(default_factory=dict)
    details_json: dict[str, Any] = Field(default_factory=dict)
    assessed_by_user_id: uuid.UUID | None = None
    assessed_at: datetime
    created_at: datetime


class ReadinessStructuredBlockerResponse(BaseModel):
    """Actionable grouped readiness blocker with navigation metadata."""

    id: str
    group: str
    severity: str
    description: str
    originating_subsystem: str
    related_section_tab: str | None = None
    related_record_id: str | None = None
    recommended_action: str
    target_url: str


class ReadinessReviewEventItem(BaseModel):
    """Recent human verification review event."""

    id: uuid.UUID
    verification_case_id: uuid.UUID
    action: str
    new_status: str
    reviewer_name: str | None = None
    review_notes: str | None = None
    created_at: datetime


class ReadinessVerificationSummary(BaseModel):
    """Live Verification Center integration summary."""

    total_knowledge_items: int = 0
    eligible_human_verified: int = 0
    pending_verification: int = 0
    rejected_items: int = 0
    verification_coverage_pct: int = 0
    case_counts: dict[str, int] = Field(default_factory=dict)
    outstanding_blockers: list[str] = Field(default_factory=list)
    recent_reviews: list[ReadinessReviewEventItem] = Field(default_factory=list)


class ReadinessConflictItem(BaseModel):
    """Canonical Conflict Management record integrated into readiness."""

    id: uuid.UUID
    verification_case_id: uuid.UUID
    conflict_type: str
    priority: str
    resolution_state: str
    is_blocking: bool = False
    explanation: str
    affected_section_tab: str = "risks"
    side_a_source_title: str | None = None
    side_b_source_title: str | None = None
    acl_restricted: bool = False
    resolution_notes: str | None = None
    resolved_at: datetime | None = None
    updated_at: datetime
    conflict_url: str


class ReadinessConflictSummary(BaseModel):
    """Aggregated Conflict Management intelligence for readiness."""

    total_conflicts: int = 0
    open_conflicts: int = 0
    under_investigation: int = 0
    awaiting_context: int = 0
    resolved_conflicts: int = 0
    critical_and_high_count: int = 0
    blocking_approval_count: int = 0
    items: list[ReadinessConflictItem] = Field(default_factory=list)


class ReadinessEvidenceQualitySummary(BaseModel):
    """Evidence completeness, corroboration, freshness, and ACL visibility summary."""

    total_knowledge_items: int = 0
    items_with_evidence: int = 0
    items_missing_evidence: int = 0
    evidence_coverage_pct: int = 100
    corroborated_items: int = 0
    uncertain_items: int = 0
    stale_items: int = 0
    superseded_items: int = 0
    total_evidence_sources: int = 0
    accessible_evidence_count: int = 0
    restricted_evidence_count: int = 0


class ReadinessChecklistGroupSummary(BaseModel):
    """Persisted checklist group state linked to readiness."""

    id: uuid.UUID
    checklist_type: str
    title: str
    total_items: int = 0
    completed_items: int = 0
    mandatory_total: int = 0
    mandatory_completed: int = 0
    mandatory_outstanding: int = 0
    is_completed: bool = False
    items: list[dict[str, Any]] = Field(default_factory=list)


class ReadinessChecklistSummary(BaseModel):
    """Aggregated checklist completion metrics for readiness."""

    total_groups: int = 0
    total_items: int = 0
    completed_items: int = 0
    completion_pct: int = 0
    mandatory_total: int = 0
    mandatory_completed: int = 0
    mandatory_outstanding: int = 0
    groups: list[ReadinessChecklistGroupSummary] = Field(default_factory=list)


class ReadinessAssessmentHistoryItem(BaseModel):
    """Historical readiness assessment snapshot for auditability."""

    id: uuid.UUID
    assessed_at: datetime
    overall_score: int
    overall_level: str
    blocker_count: int
    warning_count: int
    assessed_by_name: str | None = None
    notes: str | None = None


class ReadinessApprovalEligibility(BaseModel):
    """Authoritative backend approval & lifecycle eligibility status."""

    current_case_status: str
    next_lifecycle_state: str | None = None
    is_eligible_for_approval: bool = False
    score_gate_passed: bool = False
    verification_gate_passed: bool = False
    conflict_gate_passed: bool = False
    checklist_gate_passed: bool = False
    blocking_requirements: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    required_signoffs: list[dict[str, Any]] = Field(default_factory=list)


class HandoverReadinessSummaryResponse(BaseModel):
    """Aggregated readiness intelligence summary across all nine canonical categories."""

    version_id: uuid.UUID
    case_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    version_number: int | None = None
    content_hash: str | None = None
    assessed_at: datetime | None = None
    overall_score: int
    overall_level: str
    categories: list[HandoverReadinessAssessmentResponse]
    is_ready_for_signoff: bool
    blocker_count: int
    warning_count: int
    structured_blockers: list[ReadinessStructuredBlockerResponse] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    verification_summary: ReadinessVerificationSummary | None = None
    conflict_summary: ReadinessConflictSummary | None = None
    evidence_quality: ReadinessEvidenceQualitySummary | None = None
    checklist_summary: ReadinessChecklistSummary | None = None
    approval_eligibility: ReadinessApprovalEligibility | None = None
    assessment_history: list[ReadinessAssessmentHistoryItem] = Field(default_factory=list)


class HandoverStage5ActivityItem(BaseModel):
    """Immutable audit activity item for Stage 5 checklist and responsibility transitions."""

    id: uuid.UUID
    event_type: str
    resource_type: str
    resource_id: str | None = None
    actor_user_id: uuid.UUID | None = None
    actor_name: str | None = None
    outcome: str
    summary: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ChecklistEvidenceSummary(BaseModel):
    """ACL-checked supporting evidence reference attached to a checklist item."""

    evidence_id: uuid.UUID
    title: str
    source_type: str | None = None
    source_url: str | None = None
    acl_restricted: bool = False


class HandoverChecklistItemResponse(BaseModel):
    """Individual checklist item with Stage 5 completion, review, and reopening metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    checklist_id: uuid.UUID
    item_text: str
    description: str | None = None
    completion_criteria: str | None = None
    status: str
    blocking: bool = False
    category: str | None = None
    assigned_to_user_id: uuid.UUID | None = None
    assigned_to_name: str | None = None
    due_date: datetime | None = None
    is_overdue: bool = False
    notes: str | None = None
    evidence_item_id: uuid.UUID | None = None
    evidence_summary: ChecklistEvidenceSummary | None = None
    completed_by_user_id: uuid.UUID | None = None
    completed_by_name: str | None = None
    completed_at: datetime | None = None
    reviewed_by_user_id: uuid.UUID | None = None
    reviewed_by_name: str | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None
    reopened_count: int = 0
    reopened_by_user_id: uuid.UUID | None = None
    reopened_by_name: str | None = None
    reopened_at: datetime | None = None
    reopened_reason: str | None = None
    version: int = 1
    created_at: datetime
    updated_at: datetime


class HandoverChecklistResponse(BaseModel):
    """Checklist container with category-level counts."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    generated_for_version_id: uuid.UUID | None = None
    checklist_type: str
    title: str | None = None
    description: str | None = None
    total_items: int = 0
    completed_items: int = 0
    mandatory_total: int = 0
    mandatory_completed: int = 0
    mandatory_outstanding: int = 0
    blocked_items: int = 0
    overdue_items: int = 0
    is_completed: bool = False
    created_at: datetime
    items: list[HandoverChecklistItemResponse] = Field(default_factory=list)


class HandoverChecklistWorkspaceResponse(BaseModel):
    """Aggregated Stage 5 transition checklist workspace summary."""

    case_id: uuid.UUID
    project_id: uuid.UUID
    total_checklists: int = 0
    total_items: int = 0
    completed_items: int = 0
    outstanding_items: int = 0
    blocked_items: int = 0
    overdue_items: int = 0
    mandatory_total: int = 0
    mandatory_completed: int = 0
    mandatory_outstanding: int = 0
    optional_total: int = 0
    optional_completed: int = 0
    completion_pct: int = 0
    checklists: list[HandoverChecklistResponse] = Field(default_factory=list)
    activity_history: list[HandoverStage5ActivityItem] = Field(default_factory=list)


class DeliveryClarificationEntry(BaseModel):
    """Persisted clarification request or response on a published handover delivery."""

    id: str
    mode: str  # request | response
    author_user_id: uuid.UUID
    author_name: str | None = None
    notes: str
    created_at: datetime


class HandoverSignoffResponse(BaseModel):
    """Immutable human sign-off decision bound to a specific package version & hash."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    version_id: uuid.UUID
    signoff_type: str
    signer_user_id: uuid.UUID
    signer_name: str | None = None
    decision: str
    comments: str | None = None
    conditions: str | None = None
    package_content_hash: str | None = None
    affected_sections_json: list[str] = Field(default_factory=list)
    is_superseded: bool = False
    signature_hash: str | None = None
    signed_at: datetime
    created_at: datetime


class HandoverAcknowledgementResponse(BaseModel):
    """Formal recipient acknowledgement for a published handover package."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    delivery_id: uuid.UUID
    acknowledged_by_user_id: uuid.UUID
    acknowledged_by_name: str | None = None
    acknowledgement_notes: str | None = None
    confirmations_json: dict[str, Any] = Field(default_factory=dict)
    acknowledgement_hash: str | None = None
    acknowledged_at: datetime
    created_at: datetime


class HandoverDeliveryResponse(BaseModel):
    """Published package delivery record with acknowledgement & clarification state."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_id: uuid.UUID
    delivered_to_user_id: uuid.UUID
    delivered_to_name: str | None = None
    delivered_by_user_id: uuid.UUID | None = None
    delivered_by_name: str | None = None
    delivery_method: str
    artifact_storage_path: str | None = None
    artifact_checksum: str | None = None
    message: str | None = None
    is_active: bool = True
    delivered_at: datetime
    expires_at: datetime | None = None
    acknowledged: bool = False
    acknowledgement: HandoverAcknowledgementResponse | None = None
    clarifications: list[DeliveryClarificationEntry] = Field(default_factory=list)
    created_at: datetime


class ResponsibilityEvidenceRef(BaseModel):
    """ACL-checked supporting evidence reference for a responsibility transfer."""

    evidence_id: uuid.UUID
    title: str
    source_type: str | None = None
    source_url: str | None = None
    source_author: str | None = None
    source_timestamp: datetime | None = None
    excerpt: str | None = None
    acl_restricted: bool = False


class ResponsibilityKnowledgeContextItem(BaseModel):
    """Canonical 8-domain knowledge item linked to a responsibility (preserves real epistemic status)."""

    id: uuid.UUID
    category: str
    title: str
    summary: str
    epistemic_status: str
    review_status: str
    is_verified: bool = False
    evidence_refs: list[ResponsibilityEvidenceRef] = Field(default_factory=list)


class ResponsibilityOwnershipValidationIssue(BaseModel):
    """Detected ownership or participant validation warning/error."""

    severity: str  # critical, high, medium, low
    code: str
    message: str
    transfer_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None


class ResponsibilityParticipantSummary(BaseModel):
    """Real project member eligible (or flagged) for handover participation."""

    user_id: uuid.UUID
    full_name: str
    email: str
    role_name: str
    membership_status: str
    is_active: bool = True
    is_departing_owner: bool = False
    is_case_successor: bool = False
    has_handover_access: bool = True


class ResponsibilityCandidateItem(BaseModel):
    """Unmapped responsibility discovered in canonical project KnowledgeItems (never auto-promoted)."""

    knowledge_item_id: uuid.UUID
    title: str
    summary: str
    epistemic_status: str
    review_status: str
    is_verified: bool = False
    ownership_certainty: str = "uncertain"
    source_context: str | None = None
    evidence_refs: list[ResponsibilityEvidenceRef] = Field(default_factory=list)


class HandoverResponsibilityTransferResponse(BaseModel):
    """Responsibility transfer mapping with Stage 5 governance, knowledge & ACL-safe evidence."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    version_id: uuid.UUID | None = None
    title: str | None = None
    responsibility_description: str
    current_owner_id: uuid.UUID
    current_owner_name: str | None = None
    current_owner_role: str | None = None
    current_owner_active: bool = True
    proposed_successor_id: uuid.UUID | None = None
    proposed_successor_name: str | None = None
    proposed_successor_role: str | None = None
    proposed_successor_active: bool | None = None
    knowledge_domain: str | None = None
    component_name: str | None = None
    priority: str = "medium"
    ownership_certainty: str = "proposed"
    operational_context: str | None = None
    required_access: str | None = None
    effective_transfer_date: date | None = None
    transfer_status: str
    transfer_notes: str | None = None
    blocker_reason: str | None = None
    related_entity_id: uuid.UUID | None = None
    related_entity_name: str | None = None
    related_knowledge_item_id: uuid.UUID | None = None
    outgoing_confirmed_by_user_id: uuid.UUID | None = None
    outgoing_confirmed_by_name: str | None = None
    outgoing_confirmed_at: datetime | None = None
    outgoing_confirmation_notes: str | None = None
    successor_acknowledged_by_user_id: uuid.UUID | None = None
    successor_acknowledged_by_name: str | None = None
    successor_acknowledged_at: datetime | None = None
    successor_acknowledgement_notes: str | None = None
    clarification_requested_by_user_id: uuid.UUID | None = None
    clarification_requested_by_name: str | None = None
    clarification_requested_at: datetime | None = None
    clarification_request_notes: str | None = None
    clarification_response_notes: str | None = None
    reopened_count: int = 0
    reopened_reason: str | None = None
    version: int = 1
    transferred_at: datetime | None = None
    validation_warnings: list[str] = Field(default_factory=list)
    related_knowledge: list[ResponsibilityKnowledgeContextItem] = Field(default_factory=list)
    supporting_evidence: list[ResponsibilityEvidenceRef] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class HandoverResponsibilityWorkspaceResponse(BaseModel):
    """Aggregated Stage 5 Responsibility Transfer & Ownership Management workspace."""

    case_id: uuid.UUID
    project_id: uuid.UUID
    departing_member_id: uuid.UUID
    case_successor_id: uuid.UUID | None = None
    total_transfers: int = 0
    unassigned_count: int = 0
    awaiting_outgoing_count: int = 0
    awaiting_successor_count: int = 0
    acknowledged_count: int = 0
    blocked_count: int = 0
    clarification_count: int = 0
    validation_issues: list[ResponsibilityOwnershipValidationIssue] = Field(default_factory=list)
    eligible_participants: list[ResponsibilityParticipantSummary] = Field(default_factory=list)
    transfers: list[HandoverResponsibilityTransferResponse] = Field(default_factory=list)
    discovered_candidates: list[ResponsibilityCandidateItem] = Field(default_factory=list)
    activity_history: list[HandoverStage5ActivityItem] = Field(default_factory=list)


class HandoverStatusHistoryResponse(BaseModel):
    """Immutable status transition record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    previous_status: str
    new_status: str
    changed_by_user_id: uuid.UUID
    change_reason: str | None = None
    changed_at: datetime


class HandoverOwnershipTransferResponse(BaseModel):
    """Ownership transfer record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    version_id: uuid.UUID
    transfer_type: str
    from_user_id: uuid.UUID
    to_user_id: uuid.UUID
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    executed_at: datetime
    executed_by_user_id: uuid.UUID
    rolled_back: bool = False
    rollback_reason: str | None = None
    created_at: datetime


class HandoverEligibilityCheckResponse(BaseModel):
    """Eligibility check result for a knowledge item or relationship."""

    target_type: str
    target_id: uuid.UUID
    is_eligible: bool
    case_status: str
    epistemic_status: str
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Paginated response wrapper
# ---------------------------------------------------------------------------


class PaginatedHandoverCaseResponse(BaseModel):
    """Paginated list of handover cases."""

    items: list[HandoverCaseListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class HandoverCaseDetailResponse(BaseModel):
    """Full handover case with nested package/version/signoff details."""

    case: HandoverCaseResponse
    packages: list[HandoverPackageResponse] = Field(default_factory=list)
    current_version: HandoverPackageVersionResponse | None = None
    signoffs: list[HandoverSignoffResponse] = Field(default_factory=list)
    status_history: list[HandoverStatusHistoryResponse] = Field(default_factory=list)
    responsibility_transfers: list[HandoverResponsibilityTransferResponse] = Field(
        default_factory=list
    )


class HandoverPackageDetailResponse(BaseModel):
    """Full package version with sections and content links."""

    version: HandoverPackageVersionResponse
    sections: list[HandoverSectionResponse] = Field(default_factory=list)
    readiness: HandoverReadinessSummaryResponse | None = None
    checklists: list[HandoverChecklistResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Stage 6: Signoff, Approval, Publication & Recipient Acknowledgement Workspace
# ---------------------------------------------------------------------------


class SignoffPhaseDetail(BaseModel):
    """Authoritative status & eligibility details for a single signoff phase."""

    phase_number: int
    phase_name: str
    signoff_type: str
    purpose: str
    assigned_user_id: uuid.UUID | None = None
    assigned_user_name: str | None = None
    assigned_user_role: str | None = None
    required_permission: str
    status: str  # pending, in_progress, completed, rejected, returned_for_revision, blocked, superseded
    viewer_can_act: bool = False
    viewer_ineligibility_reason: str | None = None
    pending_requirements: list[str] = Field(default_factory=list)
    latest_decision: HandoverSignoffResponse | None = None


class SignoffLifecycleSummary(BaseModel):
    """Canonical lifecycle state, permitted transitions, responsible party, and history."""

    current_status: str
    previous_status: str | None = None
    next_permitted_transitions: list[str] = Field(default_factory=list)
    responsible_role_label: str
    responsible_user_name: str | None = None
    blocked_transition_reasons: list[str] = Field(default_factory=list)
    case_version: int = 1
    status_history: list[HandoverStatusHistoryResponse] = Field(default_factory=list)


class SignoffPublicationStatus(BaseModel):
    """Controlled publication & delivery status bound to exact approved version & SHA-256 hash."""

    is_eligible_to_publish: bool = False
    is_published: bool = False
    blocking_reasons: list[str] = Field(default_factory=list)
    approved_version_id: uuid.UUID | None = None
    approved_version_number: int | None = None
    approved_content_hash: str | None = None
    published_version_id: uuid.UUID | None = None
    published_version_number: int | None = None
    published_content_hash: str | None = None
    published_at: datetime | None = None
    published_by_name: str | None = None
    deliveries: list[HandoverDeliveryResponse] = Field(default_factory=list)


class HandoverSignoffWorkspaceResponse(BaseModel):
    """Complete authoritative Stage 6 Signoff, Approval, Publication & Recipient workspace."""

    case_id: uuid.UUID
    project_id: uuid.UUID
    case_title: str
    case_status: str
    case_version: int = 1
    departing_member_id: uuid.UUID
    departing_member_name: str | None = None
    successor_id: uuid.UUID | None = None
    successor_name: str | None = None
    assigned_reviewer_id: uuid.UUID | None = None
    assigned_reviewer_name: str | None = None
    selected_version_id: uuid.UUID | None = None
    selected_version_number: int | None = None
    selected_content_hash: str | None = None
    package_changed_since_approval: bool = False
    package_change_notice: str | None = None
    readiness_score: int | None = None
    readiness_level: str | None = None
    readiness_assessed_at: datetime | None = None
    approval_eligibility: ReadinessApprovalEligibility | None = None
    lifecycle: SignoffLifecycleSummary
    phases: list[SignoffPhaseDetail] = Field(default_factory=list)
    publication: SignoffPublicationStatus
    eligible_reviewers: list[ResponsibilityParticipantSummary] = Field(default_factory=list)
    eligible_recipients: list[ResponsibilityParticipantSummary] = Field(default_factory=list)
    signoff_history: list[HandoverSignoffResponse] = Field(default_factory=list)
    activity_history: list[HandoverStage5ActivityItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Project Successor Onboarding Progress Schemas
# ---------------------------------------------------------------------------


class UpdateOnboardingStepRequest(BaseModel):
    is_completed: bool = Field(default=True, description="Whether the step is completed")


class OnboardingStepProgressItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    step_id: str
    is_completed: bool
    completed_at: datetime | None = None


class OnboardingProgressResponse(BaseModel):
    project_id: uuid.UUID
    user_id: uuid.UUID
    completed_steps: dict[str, bool] = Field(default_factory=dict)
    items: list[OnboardingStepProgressItem] = Field(default_factory=list)

