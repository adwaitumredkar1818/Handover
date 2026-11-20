"""Handover Case Management Service.

Platform: The Handover
Module: Handover Workspace (Module 4 / Knowledge Transfer Area)

Enforces:
1. Multi-tenant project boundary validation
2. Optimistic concurrency control (via case.version increments)
3. Strict 14-state lifecycle state machine
4. Immutable HandoverStatusHistory audit trail
5. System audit log generation
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.security import utc_now
from app.models.audit import AuditLog
from app.models.enums import (
    AuditOutcome,
    ChunkIndexingStatus,
    EpistemicStatus,
    EvidenceIndexingStatus,
    EvidenceProcessingStatus,
    EvidenceSourceType,
    HandoverCaseStatus,
    KnowledgeReviewStatus,
    VerificationTargetType,
)
from app.models.evidence import EvidenceChunk, EvidenceContent, EvidenceItem
from app.models.handover import HandoverCase, HandoverStatusHistory
from app.models.knowledge import KnowledgeEvidenceLink, KnowledgeItem
from app.models.user import User
from app.repositories.audit import AuditLogRepository
from app.repositories.handover import (
    HandoverCaseRepository,
    HandoverStatusHistoryRepository,
)
from app.repositories.verification import VerificationRepository
from app.schemas.handover import (
    HandoverCaseCreateRequest,
    HandoverCaseUpdateRequest,
    HandoverContextContributionRequest,
    HandoverContextContributionResponse,
)
from app.services.audit import AuditService

VALID_HANDOVER_TYPES: frozenset[str] = frozenset(
    {"developer", "project_manager", "technical_lead"}
)

VALID_CONTEXT_CATEGORIES: frozenset[str] = frozenset(
    {
        "project_overview_context",
        "decisions_rationale",
        "technical_architecture",
        "architecture_technical",
        "work_items",
        "work_progress",
        "responsibilities_ownership",
        "dependencies",
        "dependencies_relationships",
        "bugs_blockers_risks",
        "risks_blockers_questions",
        "operational_historical",
    }
)

PUBLISHED_HANDOVER_STATUSES: frozenset[str] = frozenset(
    {
        HandoverCaseStatus.DELIVERED.value,
        HandoverCaseStatus.ACKNOWLEDGED.value,
        HandoverCaseStatus.TRANSFERRED.value,
    }
)


def is_unapproved_draft_restricted_for_successor(
    case: HandoverCase,
    viewer_user_id: uuid.UUID,
    can_review_or_manage: bool,
) -> bool:
    """Block designated incoming successors from reading unapproved drafts before publication."""
    if can_review_or_manage:
        return False
    if case.successor_id is None or case.successor_id != viewer_user_id:
        return False
    if viewer_user_id in (
        case.departing_member_id,
        case.created_by_user_id,
        case.assigned_reviewer_id,
    ):
        return False
    return case.status not in PUBLISHED_HANDOVER_STATUSES

# Allowed lifecycle state transitions
VALID_TRANSITIONS: dict[str, set[str]] = {
    HandoverCaseStatus.DRAFT.value: {
        HandoverCaseStatus.ASSEMBLING.value,
        HandoverCaseStatus.ARCHIVED.value,
    },
    HandoverCaseStatus.ASSEMBLING.value: {
        HandoverCaseStatus.ASSEMBLED.value,
        HandoverCaseStatus.DRAFT.value,
        HandoverCaseStatus.ARCHIVED.value,
    },
    HandoverCaseStatus.ASSEMBLED.value: {
        HandoverCaseStatus.READINESS_PENDING.value,
        HandoverCaseStatus.READINESS_ASSESSED.value,
        HandoverCaseStatus.ASSEMBLING.value,
        HandoverCaseStatus.DRAFT.value,
        HandoverCaseStatus.ARCHIVED.value,
        HandoverCaseStatus.SUPERSEDED.value,
    },
    HandoverCaseStatus.READINESS_PENDING.value: {
        HandoverCaseStatus.READINESS_ASSESSED.value,
        HandoverCaseStatus.ASSEMBLED.value,
        HandoverCaseStatus.ARCHIVED.value,
    },
    HandoverCaseStatus.READINESS_ASSESSED.value: {
        HandoverCaseStatus.REVIEW_PENDING.value,
        HandoverCaseStatus.READINESS_PENDING.value,
        HandoverCaseStatus.ASSEMBLED.value,
        HandoverCaseStatus.DRAFT.value,
        HandoverCaseStatus.ARCHIVED.value,
    },
    HandoverCaseStatus.REVIEW_PENDING.value: {
        HandoverCaseStatus.UNDER_REVIEW.value,
        HandoverCaseStatus.APPROVED.value,
        HandoverCaseStatus.REJECTED.value,
        HandoverCaseStatus.READINESS_ASSESSED.value,
        HandoverCaseStatus.ASSEMBLED.value,
        HandoverCaseStatus.ARCHIVED.value,
    },
    HandoverCaseStatus.UNDER_REVIEW.value: {
        HandoverCaseStatus.APPROVED.value,
        HandoverCaseStatus.REJECTED.value,
        HandoverCaseStatus.REVIEW_PENDING.value,
        HandoverCaseStatus.READINESS_ASSESSED.value,
        HandoverCaseStatus.ASSEMBLED.value,
        HandoverCaseStatus.ARCHIVED.value,
    },
    HandoverCaseStatus.APPROVED.value: {
        HandoverCaseStatus.DELIVERED.value,
        HandoverCaseStatus.UNDER_REVIEW.value,
        HandoverCaseStatus.ASSEMBLED.value,
        HandoverCaseStatus.ARCHIVED.value,
        HandoverCaseStatus.SUPERSEDED.value,
    },
    HandoverCaseStatus.REJECTED.value: {
        HandoverCaseStatus.DRAFT.value,
        HandoverCaseStatus.ASSEMBLED.value,
        HandoverCaseStatus.REVIEW_PENDING.value,
        HandoverCaseStatus.ARCHIVED.value,
    },
    HandoverCaseStatus.DELIVERED.value: {
        HandoverCaseStatus.ACKNOWLEDGED.value,
        HandoverCaseStatus.ARCHIVED.value,
        HandoverCaseStatus.SUPERSEDED.value,
    },
    HandoverCaseStatus.ACKNOWLEDGED.value: {
        HandoverCaseStatus.TRANSFERRED.value,
        HandoverCaseStatus.ARCHIVED.value,
    },
    HandoverCaseStatus.TRANSFERRED.value: {
        HandoverCaseStatus.ARCHIVED.value,
    },
    HandoverCaseStatus.ARCHIVED.value: {
        HandoverCaseStatus.DRAFT.value,  # unarchive
    },
    HandoverCaseStatus.SUPERSEDED.value: {
        HandoverCaseStatus.ARCHIVED.value,
    },
}


class HandoverCaseService:
    """Domain service managing the HandoverCase lifecycle."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.case_repo = HandoverCaseRepository(session)
        self.history_repo = HandoverStatusHistoryRepository(session)
        self.audit_service = AuditService(
            audit_repository=AuditLogRepository(session)
        )

    def create_case(
        self,
        *,
        organisation_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        request: HandoverCaseCreateRequest,
    ) -> HandoverCase:
        """Create a new HandoverCase in DRAFT status."""
        if request.successor_id is not None and request.successor_id == request.departing_member_id:
            raise BadRequestError(
                "The designated successor cannot be the same user as the departing member."
            )

        meta = dict(request.metadata_json or {})
        if "handover_type" in request.model_fields_set or not meta.get("handover_type"):
            meta["handover_type"] = request.handover_type or "developer"

        case = HandoverCase(
            organisation_id=organisation_id,
            project_id=project_id,
            title=request.title,
            description=request.description,
            status=HandoverCaseStatus.DRAFT.value,
            departing_member_id=request.departing_member_id,
            successor_id=request.successor_id,
            target_handover_date=request.target_handover_date,
            created_by_user_id=user_id,
            metadata_json=meta,
            version=1,
        )
        created_case = self.case_repo.create(case)

        # Record initial status in history
        self.history_repo.create(
            HandoverStatusHistory(
                organisation_id=organisation_id,
                project_id=project_id,
                case_id=created_case.id,
                previous_status="none",
                new_status=HandoverCaseStatus.DRAFT.value,
                changed_by_user_id=user_id,
                change_reason="Handover case created",
            )
        )

        self.audit_service.record_event(
            event_type="handover.case.created",
            resource_type="handover_case",
            resource_id=str(created_case.id),
            actor_user_id=user_id,
            organisation_id=organisation_id,
            project_id=project_id,
            outcome=AuditOutcome.SUCCESS.value,
            metadata={
                "title": request.title,
                "departing_member_id": str(request.departing_member_id),
                "handover_type": meta["handover_type"],
            },
        )

        return created_case

    def get_case(
        self,
        case_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        load_relationships: bool = True,
    ) -> HandoverCase:
        """Retrieve a HandoverCase ensuring project boundary isolation."""
        case = self.case_repo.get_by_id(case_id, load_relationships=load_relationships)
        if not case or case.project_id != project_id:
            raise NotFoundError(f"Handover case {case_id} not found in this project.")
        return case

    def list_cases(
        self,
        *,
        project_id: uuid.UUID,
        status: str | None = None,
        departing_member_id: uuid.UUID | None = None,
        successor_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[HandoverCase], int]:
        """List cases with filtering and pagination."""
        return self.case_repo.list_by_project(
            project_id=project_id,
            status=status,
            departing_member_id=departing_member_id,
            successor_id=successor_id,
            offset=offset,
            limit=limit,
        )

    def update_case(
        self,
        case_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        request: HandoverCaseUpdateRequest,
    ) -> HandoverCase:
        """Update mutable fields of a HandoverCase."""
        case = self.get_case(case_id, project_id=project_id, load_relationships=False)
        if case.status in (
            HandoverCaseStatus.APPROVED.value,
            HandoverCaseStatus.DELIVERED.value,
            HandoverCaseStatus.ACKNOWLEDGED.value,
            HandoverCaseStatus.TRANSFERRED.value,
            HandoverCaseStatus.ARCHIVED.value,
            HandoverCaseStatus.SUPERSEDED.value,
        ):
            raise BadRequestError(
                f"Cannot update case in locked status '{case.status}'."
            )

        if request.title is not None:
            case.title = request.title
        if request.description is not None:
            case.description = request.description
        if request.successor_id is not None:
            if request.successor_id == case.departing_member_id:
                raise BadRequestError(
                    "The designated successor cannot be the same user as the departing member."
                )
            case.successor_id = request.successor_id
        if request.target_handover_date is not None:
            case.target_handover_date = request.target_handover_date
        if request.metadata_json is not None:
            meta = dict(request.metadata_json)
            if request.handover_type is not None:
                meta["handover_type"] = request.handover_type
            case.metadata_json = meta
        elif request.handover_type is not None:
            meta = dict(case.metadata_json or {})
            meta["handover_type"] = request.handover_type
            case.metadata_json = meta

        case.version += 1
        case.updated_at = utc_now()
        self.session.flush()

        self.audit_service.record_event(
            event_type="handover.case.updated",
            resource_type="handover_case",
            resource_id=str(case.id),
            actor_user_id=user_id,
            organisation_id=case.organisation_id,
            project_id=project_id,
            outcome=AuditOutcome.SUCCESS.value,
        )

        return case

    def contribute_context(
        self,
        case_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        request: HandoverContextContributionRequest,
    ) -> HandoverContextContributionResponse:
        """Persist departing/member context as attributable unverified candidate knowledge."""
        from app.services.verification_engine import VerificationEngine

        case = self.get_case(case_id, project_id=project_id, load_relationships=False)
        if case.status in (
            HandoverCaseStatus.APPROVED.value,
            HandoverCaseStatus.DELIVERED.value,
            HandoverCaseStatus.ACKNOWLEDGED.value,
            HandoverCaseStatus.TRANSFERRED.value,
            HandoverCaseStatus.ARCHIVED.value,
            HandoverCaseStatus.SUPERSEDED.value,
        ):
            raise BadRequestError(
                f"Cannot contribute new draft context while case is in locked status '{case.status}'."
            )

        category = request.category.strip()
        if category not in VALID_CONTEXT_CATEGORIES:
            raise BadRequestError(
                f"Unsupported knowledge category '{request.category}'."
            )

        actor = self.session.get(User, user_id)
        actor_name = (actor.full_name or actor.email) if actor else str(user_id)
        now = utc_now()
        full_text = request.content.strip()
        if request.rationale and request.rationale.strip():
            full_text = f"{full_text}\n\nRationale: {request.rationale.strip()}"

        nonce = uuid.uuid4().hex
        content_hash = hashlib.sha256(
            f"{project_id}:{case.id}:{nonce}:{full_text}".encode("utf-8")
        ).hexdigest()

        ev = EvidenceItem(
            organisation_id=case.organisation_id,
            project_id=project_id,
            uploaded_by_user_id=user_id,
            source_type=EvidenceSourceType.MANUAL_NOTE.value,
            source_provider="handover_context",
            category="project_document",
            source_external_id=f"handover-context:{case.id}:{nonce[:12]}",
            source_author_identity=actor_name,
            title=request.title.strip(),
            content_hash=content_hash,
            acl_scope="project_members",
            source_created_at=now,
            source_updated_at=now,
            extracted_at=now,
            processing_status=EvidenceProcessingStatus.EXTRACTED.value,
            extraction_method="human_handover_context",
            indexing_status=EvidenceIndexingStatus.NOT_INDEXED.value,
            chunk_count=1,
            metadata_json={
                "handover_case_id": str(case.id),
                "contributed_by_user_id": str(user_id),
                "category": category,
            },
        )
        self.session.add(ev)
        self.session.flush()

        ev_content = EvidenceContent(
            evidence_id=ev.id,
            extracted_text=full_text,
            char_count=len(full_text),
            word_count=len(full_text.split()),
            extraction_warnings=[],
        )
        self.session.add(ev_content)

        chunk_hash = hashlib.sha256(full_text.encode("utf-8")).hexdigest()
        chunk = EvidenceChunk(
            organisation_id=case.organisation_id,
            project_id=project_id,
            evidence_id=ev.id,
            chunk_index=0,
            chunk_type="text_segment",
            section_title=request.title.strip(),
            char_start=0,
            char_end=len(full_text),
            char_count=len(full_text),
            token_estimate=max(1, len(full_text.split())),
            chunk_text=full_text,
            chunk_content_hash=chunk_hash,
            search_identifier_text=request.title.strip(),
            source_type=EvidenceSourceType.MANUAL_NOTE.value,
            source_author_identity=actor_name,
            source_created_at=now,
            acl_scope="project_members",
            indexing_status=ChunkIndexingStatus.CHUNKED.value,
            metadata_json={"handover_case_id": str(case.id)},
        )
        self.session.add(chunk)
        self.session.flush()

        # Contributed member context NEVER enters as human_verified truth automatically
        ki = KnowledgeItem(
            organisation_id=case.organisation_id,
            project_id=project_id,
            category=category,
            primary_domain=category,
            epistemic_status=EpistemicStatus.EXTRACTED.value,
            review_status=KnowledgeReviewStatus.PENDING_REVIEW.value,
            support_classification="direct",
            title=request.title.strip(),
            structured_summary=full_text,
            structured_payload={
                "handover_case_id": str(case.id),
                "contributed_by_user_id": str(user_id),
                "rationale": request.rationale.strip() if request.rationale else None,
            },
            person_or_owner_label=actor_name,
            source_attribution_json={
                "handover_case_id": str(case.id),
                "author_user_id": str(user_id),
                "author_name": actor_name,
            },
            extraction_model="human_handover_contribution",
            prompt_version="handover_context_v1",
            fingerprint=hashlib.sha256(
                f"{project_id}:{category}:{request.title.strip()}:{nonce}".encode("utf-8")
            ).hexdigest(),
            confidence_metadata_json={
                "confidence": 0.9,
                "note": "Attributable handover context contributed prior to verification.",
            },
            source_observed_at=now,
        )
        self.session.add(ki)
        self.session.flush()

        link = KnowledgeEvidenceLink(
            organisation_id=case.organisation_id,
            project_id=project_id,
            knowledge_item_id=ki.id,
            evidence_id=ev.id,
            evidence_chunk_id=chunk.id,
            support_type="direct",
            source_location_json={"section": "handover_context"},
            supporting_excerpt=full_text,
            excerpt_verified=True,
            excerpt_match_mode="exact",
        )
        self.session.add(link)
        self.session.flush()

        VerificationEngine(self.session).sync_project_findings(project_id)
        vc = VerificationRepository(self.session).get_case_by_target(
            project_id=project_id,
            target_type=VerificationTargetType.KNOWLEDGE_ITEM.value,
            target_id=ki.id,
        )
        assert vc is not None

        self.audit_service.record_event(
            event_type="handover.context.contributed",
            resource_type="handover_case",
            resource_id=str(case.id),
            actor_user_id=user_id,
            organisation_id=case.organisation_id,
            project_id=project_id,
            outcome=AuditOutcome.SUCCESS.value,
            metadata={
                "case_id": str(case.id),
                "evidence_id": str(ev.id),
                "knowledge_item_id": str(ki.id),
                "verification_case_id": str(vc.id),
                "category": category,
                "epistemic_status": ki.epistemic_status,
                "review_status": ki.review_status,
            },
        )
        self.session.flush()

        return HandoverContextContributionResponse(
            evidence_id=ev.id,
            knowledge_item_id=ki.id,
            verification_case_id=vc.id,
            epistemic_status=ki.epistemic_status,
            review_status=ki.review_status,
            category=ki.category,
            title=ki.title,
            created_at=ki.created_at,
        )

    def transition_status(
        self,
        case_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        new_status: str,
        user_id: uuid.UUID,
        change_reason: str | None = None,
        expected_version: int | None = None,
    ) -> HandoverCase:
        """Execute a state machine transition with audit and concurrency checks."""
        case = self.get_case(case_id, project_id=project_id, load_relationships=False)

        current_status = case.status
        allowed_next = VALID_TRANSITIONS.get(current_status, set())
        if new_status not in allowed_next:
            raise BadRequestError(
                f"Invalid status transition from '{current_status}' to '{new_status}'. "
                f"Allowed transitions: {sorted(allowed_next)}"
            )

        if expected_version is not None and case.version != expected_version:
            raise ConflictError(
                f"Concurrency conflict: Case version is {case.version}, expected {expected_version}."
            )

        case.status = new_status
        case.version += 1
        case.updated_at = utc_now()

        # Record history
        self.history_repo.create(
            HandoverStatusHistory(
                organisation_id=case.organisation_id,
                project_id=project_id,
                case_id=case.id,
                previous_status=current_status,
                new_status=new_status,
                changed_by_user_id=user_id,
                change_reason=change_reason,
            )
        )

        self.audit_service.record_event(
            event_type="handover.case.status_changed",
            resource_type="handover_case",
            resource_id=str(case.id),
            actor_user_id=user_id,
            organisation_id=case.organisation_id,
            project_id=project_id,
            outcome=AuditOutcome.SUCCESS.value,
            metadata={
                "previous_status": current_status,
                "new_status": new_status,
                "reason": change_reason,
            },
        )

        self.session.flush()
        return case
