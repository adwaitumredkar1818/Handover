"""FastAPI HTTP endpoints for Verification Center (Module 3 / Validation Area).

Provides:
- Paginated human review queue and summary metrics
- Case detail inspection with side-by-side evidence and conflict comparison
- Atomic human review actions (approve, reject, edit, mark unresolved, assign)
- In-platform context requests and response handling
- Handover eligibility verification gate checks
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db_session, require_project_permission
from app.models.enums import (
    ConflictResolutionState,
    ConflictType,
    ContextRequestStatus,
    VerificationCaseStatus,
    VerificationPriority,
    VerificationTargetType,
)
from app.models.evidence import EvidenceItem
from app.models.knowledge import KnowledgeEvidenceLink, KnowledgeItem
from app.models.relationship import KnowledgeRelationship
from app.models.verification import VerificationCase, VerificationConflict
from app.repositories.verification import (
    VerificationCaseRepository,
    VerificationConflictRepository,
    VerificationContextRequestRepository,
)
from app.schemas.verification import (
    ApproveCaseRequest,
    AssignReviewerRequest,
    ConflictListResponse,
    ConflictSummaryResponse,
    DetectConflictsResponse,
    EditFindingRequest,
    HandoverEligibilityResponse,
    MarkUnresolvedRequest,
    RejectCaseRequest,
    RequestContextRequest,
    ResolveConflictRequest,
    RespondContextRequest,
    VerificationCaseDetailResponse,
    VerificationCaseItemResponse,
    VerificationConflictResponse,
    VerificationContextRequestResponse,
    VerificationIssueResponse,
    VerificationQueueResponse,
    VerificationReviewEventResponse,
    VerificationSummaryResponse,
)
from app.core.cache.local_cache import local_response_cache
from app.services.conflict_detection import ConflictDetectionEngine
from app.services.handover_eligibility import (
    HandoverEligibilityService,
    check_evidence_accessibility,
)
from app.services.rbac import ProjectContext
from app.services.verification_engine import DeterministicVerificationEngine
from app.services.verification_review import (
    ConcurrencyConflictError,
    HumanReviewService,
    ReviewValidationError,
)

router = APIRouter(tags=["Verification Center"])


class DirectReviewFindingRequest(BaseModel):
    action: str = Field(description="'approve', 'flag', or 'reject'")
    notes: str | None = Field(default=None)


def _invalidate_project_caches(project_id: uuid.UUID) -> None:
    """Clear short-lived L1 response caches on verification mutations."""
    local_response_cache.invalidate_prefix(f"ki_graph:{project_id}:")
    local_response_cache.invalidate_prefix(f"ki_domains:{project_id}:")
    local_response_cache.invalidate_prefix(f"ki_summary:{project_id}:")
    local_response_cache.invalidate_prefix(f"rel_graph:{project_id}:")
    local_response_cache.invalidate_prefix(f"contrib_graph:{project_id}:")
    local_response_cache.invalidate_prefix(f"verification_summary:{project_id}:")


def _str_val(val: Any) -> str:
    if hasattr(val, "value"):
        return str(val.value)
    return str(val) if val is not None else ""


def _to_case_item_response(
    case: VerificationCase,
    target_obj: KnowledgeItem | KnowledgeRelationship | None = None,
) -> VerificationCaseItemResponse:
    open_issues = [
        i for i in getattr(case, "issues", []) if getattr(i, "resolution_state", "") == "open"
    ]
    open_conflicts = [
        c
        for c in getattr(case, "conflicts", [])
        if getattr(c, "resolution_state", "") == "unresolved"
    ]

    title: str | None = None
    summary: str | None = None
    domain: str | None = None
    category: str | None = None
    confidence_score: float | None = None
    finding_dict: dict[str, Any] | None = None

    if target_obj:
        if isinstance(target_obj, KnowledgeItem):
            title = target_obj.title
            summary = getattr(target_obj, "structured_summary", None) or getattr(target_obj, "summary", "") or ""
            domain = getattr(target_obj, "primary_domain", None) or getattr(target_obj, "category", "") or "General"
            category = getattr(target_obj, "category", None) or domain
            confidence_score = (
                float(target_obj.confidence_score)
                if getattr(target_obj, "confidence_score", None) is not None
                else None
            )
            if confidence_score is None and getattr(target_obj, "confidence_metadata_json", None):
                meta_score = target_obj.confidence_metadata_json.get("confidence_score")
                if meta_score is not None:
                    confidence_score = float(meta_score)
            finding_dict = {
                "title": title,
                "summary": summary,
                "domain": domain,
                "category": category,
            }
        elif isinstance(target_obj, KnowledgeRelationship):
            title = f"{target_obj.relationship_type.upper()}: {target_obj.relationship_basis}"
            summary = f"Relationship linking {target_obj.source_entity_id} -> {target_obj.target_entity_id}"
            domain = "Relationship"
            category = target_obj.relationship_type
            confidence_score = (
                float(target_obj.confidence_score)
                if target_obj.confidence_score is not None
                else None
            )
            finding_dict = {
                "title": title,
                "summary": summary,
                "domain": domain,
                "category": category,
            }

    return VerificationCaseItemResponse(
        id=case.id,
        organisation_id=case.organisation_id,
        project_id=case.project_id,
        target_type=_str_val(case.target_type),
        target_id=case.target_id,
        case_status=_str_val(case.case_status),
        machine_assessment_status=_str_val(case.machine_assessment_status),
        priority=_str_val(case.priority),
        assigned_reviewer_id=case.assigned_reviewer_id,
        machine_assessment_json=case.machine_assessment_json or {},
        version=case.version,
        open_issues_count=len(open_issues),
        open_conflicts_count=len(open_conflicts),
        last_assessed_at=case.last_assessed_at,
        last_reviewed_at=case.last_reviewed_at,
        resolved_at=case.resolved_at,
        created_at=case.created_at,
        updated_at=case.updated_at,
        title=title,
        summary=summary,
        domain=domain,
        category=category,
        confidence_score=confidence_score,
        finding=finding_dict,
        status=_str_val(case.case_status),
        risk_level=_str_val(case.priority),
        issue_count=len(open_issues),
    )


def _to_case_detail_response(
    case: VerificationCase, session: Session, *, viewer_user_id: uuid.UUID, has_manage: bool
) -> VerificationCaseDetailResponse:
    # Fetch target data
    target_data: dict[str, Any] = {}
    if _str_val(case.target_type) == _str_val(VerificationTargetType.KNOWLEDGE_ITEM):
        item = session.get(KnowledgeItem, case.target_id)
        if item:
            score_val = (
                float(item.confidence_score)
                if getattr(item, "confidence_score", None) is not None
                else None
            )
            if score_val is None and getattr(item, "confidence_metadata_json", None):
                meta_sc = item.confidence_metadata_json.get("confidence_score")
                if meta_sc is not None:
                    score_val = float(meta_sc)

            target_data = {
                "id": str(item.id),
                "title": item.title,
                "summary": getattr(item, "structured_summary", None)
                or getattr(item, "summary", ""),
                "knowledge_domain": getattr(item, "primary_domain", None)
                or getattr(item, "category", ""),
                "epistemic_status": _str_val(item.epistemic_status),
                "review_status": _str_val(item.review_status),
                "confidence_score": score_val,
                "item_payload": getattr(item, "structured_payload", None)
                or getattr(item, "item_payload", {}),
            }
    elif _str_val(case.target_type) == _str_val(VerificationTargetType.RELATIONSHIP):
        rel = session.get(KnowledgeRelationship, case.target_id)
        if rel:
            target_data = {
                "id": str(rel.id),
                "relationship_type": rel.relationship_type,
                "relationship_basis": rel.relationship_basis,
                "source_entity_id": str(rel.source_entity_id),
                "target_entity_id": str(rel.target_entity_id),
                "verification_status": rel.verification_status,
                "confidence_score": float(rel.confidence_score)
                if rel.confidence_score is not None
                else None,
            }

    issues_resp = [VerificationIssueResponse.model_validate(i) for i in getattr(case, "issues", [])]
    conflicts_resp = [
        VerificationConflictResponse.model_validate(c) for c in getattr(case, "conflicts", [])
    ]
    events_resp: list[VerificationReviewEventResponse] = []
    for e in getattr(case, "review_events", []):
        action_val = _str_val(getattr(e, "action", ""))
        notes_val = getattr(e, "review_notes", None)
        events_resp.append(
            VerificationReviewEventResponse(
                id=e.id,
                case_id=e.case_id,
                reviewer_user_id=e.reviewer_user_id,
                action=action_val,
                event_type=action_val,
                previous_status=_str_val(e.previous_status),
                new_status=_str_val(e.new_status),
                review_notes=notes_val,
                notes=notes_val,
                finding_patch_json=getattr(e, "finding_patch_json", None),
                correlation_id=getattr(e, "correlation_id", ""),
                created_at=e.created_at,
            )
        )
    context_resp = [
        VerificationContextRequestResponse.model_validate(r)
        for r in getattr(case, "context_requests", [])
    ]

    return VerificationCaseDetailResponse(
        id=case.id,
        organisation_id=case.organisation_id,
        project_id=case.project_id,
        target_type=_str_val(case.target_type),
        target_id=case.target_id,
        case_status=_str_val(case.case_status),
        machine_assessment_status=_str_val(case.machine_assessment_status),
        priority=_str_val(case.priority),
        assigned_reviewer_id=case.assigned_reviewer_id,
        machine_assessment_json=case.machine_assessment_json or {},
        version=case.version,
        last_assessed_at=case.last_assessed_at,
        last_reviewed_at=case.last_reviewed_at,
        resolved_at=case.resolved_at,
        created_at=case.created_at,
        updated_at=case.updated_at,
        target_data=target_data,
        issues=issues_resp,
        conflicts=conflicts_resp,
        review_events=events_resp,
        context_requests=context_resp,
    )


# ==============================================================================
# Queue & Summary
# ==============================================================================


@router.get(
    "/projects/{project_id}/verification/queue",
    response_model=VerificationQueueResponse,
    status_code=status.HTTP_200_OK,
    summary="List verification cases in the human review queue",
)
def list_verification_queue(
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
    case_status: Annotated[VerificationCaseStatus | None, Query()] = None,
    status: Annotated[VerificationCaseStatus | None, Query()] = None,
    priority: Annotated[VerificationPriority | None, Query()] = None,
    target_type: Annotated[VerificationTargetType | None, Query()] = None,
    assigned_reviewer_id: Annotated[uuid.UUID | None, Query()] = None,
    unassigned_only: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> VerificationQueueResponse:
    repo = VerificationCaseRepository(db_session)
    effective_status = case_status or status
    items = repo.list_queue(
        project_ctx.project.id,
        case_status=effective_status,
        priority=priority,
        target_type=target_type,
        assigned_reviewer_id=assigned_reviewer_id,
        unassigned_only=unassigned_only,
        limit=limit,
        offset=offset,
    )
    total = repo.count_queue(
        project_ctx.project.id,
        case_status=effective_status,
        priority=priority,
        target_type=target_type,
        assigned_reviewer_id=assigned_reviewer_id,
        unassigned_only=unassigned_only,
    )

    item_ids = [
        c.target_id
        for c in items
        if _str_val(c.target_type) == _str_val(VerificationTargetType.KNOWLEDGE_ITEM)
    ]
    items_map: dict[uuid.UUID, KnowledgeItem] = {}
    if item_ids:
        item_records = (
            db_session.execute(select(KnowledgeItem).where(KnowledgeItem.id.in_(item_ids)))
            .scalars()
            .all()
        )
        items_map = {it.id: it for it in item_records}

    rel_ids = [
        c.target_id
        for c in items
        if _str_val(c.target_type) == _str_val(VerificationTargetType.RELATIONSHIP)
    ]
    rels_map: dict[uuid.UUID, KnowledgeRelationship] = {}
    if rel_ids:
        rel_records = (
            db_session.execute(select(KnowledgeRelationship).where(KnowledgeRelationship.id.in_(rel_ids)))
            .scalars()
            .all()
        )
        rels_map = {r.id: r for r in rel_records}

    resp_items = []
    for c in items:
        target_obj = (
            items_map.get(c.target_id)
            if _str_val(c.target_type) == _str_val(VerificationTargetType.KNOWLEDGE_ITEM)
            else rels_map.get(c.target_id)
        )
        resp_items.append(_to_case_item_response(c, target_obj))

    return VerificationQueueResponse(
        items=resp_items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/projects/{project_id}/verification/summary",
    response_model=VerificationSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Aggregated project verification statistics",
)
def get_verification_summary(
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> VerificationSummaryResponse:
    bind_id = id(db_session.get_bind())
    cache_key = f"verification_summary:{project_ctx.project.id}:{bind_id}"
    cached = local_response_cache.get(cache_key)
    if isinstance(cached, dict):
        return VerificationSummaryResponse(**cached)

    repo = VerificationCaseRepository(db_session)
    summary_data = repo.get_summary(project_ctx.project.id)
    local_response_cache.set(cache_key, summary_data, ttl_seconds=30)
    return VerificationSummaryResponse(**summary_data)


# ==============================================================================
# Case Details & Evidence Inspection
# ==============================================================================


@router.get(
    "/projects/{project_id}/verification/cases/{case_id}",
    response_model=VerificationCaseDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get complete details, issues, and audit history of a verification case",
)
def get_verification_case(
    case_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> VerificationCaseDetailResponse:
    repo = VerificationCaseRepository(db_session)
    case = repo.get_by_id(case_id, load_relationships=True)
    if not case or case.project_id != project_ctx.project.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Verification case not found."
        )

    has_manage = project_ctx.has_permission("project.manage")
    return _to_case_detail_response(
        case, db_session, viewer_user_id=project_ctx.user_id, has_manage=has_manage
    )


@router.get(
    "/projects/{project_id}/verification/cases/{case_id}/evidence",
    status_code=status.HTTP_200_OK,
    summary="Get side-by-side supporting and contradictory evidence for a case",
)
def get_case_evidence_details(
    case_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, Any]:
    repo = VerificationCaseRepository(db_session)
    case = repo.get_by_id(case_id, load_relationships=True)
    if not case or case.project_id != project_ctx.project.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Verification case not found."
        )

    has_manage = project_ctx.has_permission("project.manage")

    # Fetch supporting links
    supporting_evidence: list[dict[str, Any]] = []
    if _str_val(case.target_type) == _str_val(VerificationTargetType.KNOWLEDGE_ITEM):
        links = list(
            db_session.execute(
                select(KnowledgeEvidenceLink)
                .where(KnowledgeEvidenceLink.knowledge_item_id == case.target_id)
                .options(
                    selectinload(KnowledgeEvidenceLink.evidence_item),
                    selectinload(KnowledgeEvidenceLink.evidence_chunk),
                )
            )
            .scalars()
            .all()
        )
        ev_items = [link.evidence_item for link in links if link.evidence_item]
        ev_ids = [ev.id for ev in ev_items]
        accessible_set: set[uuid.UUID] = set()
        if ev_ids:
            _, accessible_set = check_evidence_accessibility(
                db_session,
                ev_ids,
                project_id=case.project_id,
                viewer_user_id=project_ctx.user_id,
                has_project_manage=has_manage,
            )

        for link in links:
            ev = link.evidence_item
            if not ev:
                continue
            accessible = ev.id in accessible_set
            if not accessible:
                supporting_evidence.append(
                    {
                        "evidence_id": str(ev.id),
                        "restricted": True,
                        "reason": "Source restricted by project ACLs",
                    }
                )
                continue

            link_conf = (
                float(link.confidence_score)
                if getattr(link, "confidence_score", None) is not None
                else None
            )
            if link_conf is None and getattr(link, "source_metadata_json", None):
                meta_sc = link.source_metadata_json.get("confidence_score")
                if meta_sc is not None:
                    link_conf = float(meta_sc)

            supporting_evidence.append(
                {
                    "evidence_id": str(ev.id),
                    "title": ev.title,
                    "source_type": ev.source_type,
                    "source_url": ev.source_url,
                    "author": getattr(ev, "author_or_creator", None),
                    "support_type": link.support_type,
                    "supporting_excerpt": link.supporting_excerpt,
                    "excerpt_verified": link.excerpt_verified,
                    "source_location": link.source_location_json,
                    "chunk_id": str(link.evidence_chunk_id) if link.evidence_chunk_id else None,
                    "chunk_text": getattr(link.evidence_chunk, "chunk_text", None),
                    "confidence_score": link_conf,
                    "restricted": False,
                }
            )

    # Conflicts (zero fabrication - return exact links only)
    conflicts_data: list[dict[str, Any]] = []
    for c in getattr(case, "conflicts", []):
        conflicts_data.append(
            {
                "id": str(c.id),
                "conflict_type": _str_val(c.conflict_type),
                "claim_a_text": c.claim_a_text,
                "claim_a_evidence_id": str(c.claim_a_source_evidence_id),
                "claim_a_timestamp": c.claim_a_source_timestamp.isoformat()
                if c.claim_a_source_timestamp
                else None,
                "claim_b_text": c.claim_b_text,
                "claim_b_evidence_id": str(c.claim_b_source_evidence_id),
                "claim_b_timestamp": c.claim_b_source_timestamp.isoformat()
                if c.claim_b_source_timestamp
                else None,
                "explanation": c.explanation,
                "temporal_comparison": _str_val(c.temporal_comparison),
                "resolution_state": _str_val(c.resolution_state),
            }
        )

    return {
        "case_id": str(case.id),
        "target_type": _str_val(case.target_type),
        "target_id": str(case.target_id),
        "supporting_evidence": supporting_evidence,
        "conflicts": conflicts_data,
    }


# ==============================================================================
# Human Review Actions (Require project.knowledge.review)
# ==============================================================================


@router.post(
    "/projects/{project_id}/verification/cases/{case_id}/approve",
    response_model=VerificationCaseDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Approve finding as human-verified project knowledge",
)
def approve_case(
    case_id: uuid.UUID,
    payload: ApproveCaseRequest,
    project_ctx: Annotated[
        ProjectContext, Depends(require_project_permission("project.knowledge.review"))
    ],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> VerificationCaseDetailResponse:
    repo = VerificationCaseRepository(db_session)
    existing_case = repo.get_by_id(case_id)
    if not existing_case or existing_case.project_id != project_ctx.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verification case not found.")

    service = HumanReviewService(db_session)
    version = payload.expected_version if payload.expected_version is not None else existing_case.version
    notes = payload.review_notes or payload.notes or "Approved by human reviewer"

    try:
        case = service.approve(
            case_id=case_id,
            reviewer_user_id=project_ctx.user_id,
            expected_version=version,
            review_notes=notes,
        )
        db_session.commit()
        _invalidate_project_caches(project_ctx.project.id)
    except ConcurrencyConflictError as exc:
        db_session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ReviewValidationError as exc:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except Exception as exc:
        db_session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    has_manage = project_ctx.has_permission("project.manage")
    return _to_case_detail_response(
        case, db_session, viewer_user_id=project_ctx.user_id, has_manage=has_manage
    )


@router.post(
    "/projects/{project_id}/verification/cases/{case_id}/reject",
    response_model=VerificationCaseDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Reject candidate finding or relationship",
)
def reject_case(
    case_id: uuid.UUID,
    payload: RejectCaseRequest,
    project_ctx: Annotated[
        ProjectContext, Depends(require_project_permission("project.knowledge.review"))
    ],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> VerificationCaseDetailResponse:
    repo = VerificationCaseRepository(db_session)
    existing_case = repo.get_by_id(case_id)
    if not existing_case or existing_case.project_id != project_ctx.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verification case not found.")

    service = HumanReviewService(db_session)
    version = payload.expected_version if payload.expected_version is not None else existing_case.version
    reason = payload.reason or payload.notes or "Rejected by human reviewer"
    notes = payload.review_notes or payload.notes

    try:
        case = service.reject(
            case_id=case_id,
            reviewer_user_id=project_ctx.user_id,
            expected_version=version,
            reason=reason,
            review_notes=notes,
        )
        db_session.commit()
        _invalidate_project_caches(project_ctx.project.id)
    except ConcurrencyConflictError as exc:
        db_session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except Exception as exc:
        db_session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    has_manage = project_ctx.has_permission("project.manage")
    return _to_case_detail_response(
        case, db_session, viewer_user_id=project_ctx.user_id, has_manage=has_manage
    )


@router.patch(
    "/projects/{project_id}/verification/cases/{case_id}/finding",
    response_model=VerificationCaseDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Correct finding fields with version tracking and full audit diff",
)
def edit_case_finding(
    case_id: uuid.UUID,
    payload: EditFindingRequest,
    project_ctx: Annotated[
        ProjectContext, Depends(require_project_permission("project.knowledge.review"))
    ],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> VerificationCaseDetailResponse:
    repo = VerificationCaseRepository(db_session)
    existing_case = repo.get_by_id(case_id)
    if not existing_case or existing_case.project_id != project_ctx.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verification case not found.")

    service = HumanReviewService(db_session)
    version = payload.expected_version if payload.expected_version is not None else existing_case.version
    reason = payload.reason or "Human reviewer correction"
    patch_data = dict(payload.patch_data or {})
    if payload.title is not None:
        patch_data["title"] = payload.title
    if payload.summary is not None:
        patch_data["summary"] = payload.summary

    try:
        case = service.edit_finding(
            case_id=case_id,
            reviewer_user_id=project_ctx.user_id,
            expected_version=version,
            patch_data=patch_data,
            reason=reason,
        )
        db_session.commit()
        _invalidate_project_caches(project_ctx.project.id)
    except ConcurrencyConflictError as exc:
        db_session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ReviewValidationError as exc:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except Exception as exc:
        db_session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    has_manage = project_ctx.has_permission("project.manage")
    return _to_case_detail_response(
        case, db_session, viewer_user_id=project_ctx.user_id, has_manage=has_manage
    )


@router.post(
    "/projects/{project_id}/verification/cases/{case_id}/request-context",
    response_model=VerificationContextRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Dispatch clarification question to team member",
)
def request_case_context(
    case_id: uuid.UUID,
    payload: RequestContextRequest,
    project_ctx: Annotated[
        ProjectContext, Depends(require_project_permission("project.knowledge.review"))
    ],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> VerificationContextRequestResponse:
    repo = VerificationCaseRepository(db_session)
    existing_case = repo.get_by_id(case_id)
    if not existing_case or existing_case.project_id != project_ctx.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verification case not found.")

    service = HumanReviewService(db_session)
    version = payload.expected_version if payload.expected_version is not None else existing_case.version

    try:
        req = service.request_context(
            case_id=case_id,
            reviewer_user_id=project_ctx.user_id,
            requested_from_user_id=payload.requested_from_user_id,
            question=payload.question,
            requested_information_type=payload.requested_information_type,
            expected_version=version,
        )
        db_session.commit()
        _invalidate_project_caches(project_ctx.project.id)
    except ConcurrencyConflictError as exc:
        db_session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except Exception as exc:
        db_session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return VerificationContextRequestResponse.model_validate(req)


@router.post(
    "/projects/{project_id}/verification/cases/{case_id}/mark-unresolved",
    response_model=VerificationCaseDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark case as unresolved when consensus cannot be established",
)
def mark_case_unresolved(
    case_id: uuid.UUID,
    payload: MarkUnresolvedRequest,
    project_ctx: Annotated[
        ProjectContext, Depends(require_project_permission("project.knowledge.review"))
    ],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> VerificationCaseDetailResponse:
    repo = VerificationCaseRepository(db_session)
    existing_case = repo.get_by_id(case_id)
    if not existing_case or existing_case.project_id != project_ctx.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verification case not found.")

    service = HumanReviewService(db_session)
    version = payload.expected_version if payload.expected_version is not None else existing_case.version
    explanation = payload.explanation or payload.reason or "Unresolved pending consensus"

    try:
        case = service.mark_unresolved(
            case_id=case_id,
            reviewer_user_id=project_ctx.user_id,
            expected_version=version,
            explanation=explanation,
        )
        db_session.commit()
        _invalidate_project_caches(project_ctx.project.id)
    except ConcurrencyConflictError as exc:
        db_session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except Exception as exc:
        db_session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    has_manage = project_ctx.has_permission("project.manage")
    return _to_case_detail_response(
        case, db_session, viewer_user_id=project_ctx.user_id, has_manage=has_manage
    )


@router.post(
    "/projects/{project_id}/verification/cases/{case_id}/assign",
    response_model=VerificationCaseDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Assign or reassign review case",
)
def assign_case_reviewer(
    case_id: uuid.UUID,
    payload: AssignReviewerRequest,
    project_ctx: Annotated[
        ProjectContext, Depends(require_project_permission("project.knowledge.review"))
    ],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> VerificationCaseDetailResponse:
    service = HumanReviewService(db_session)
    try:
        case = service.assign_reviewer(
            case_id=case_id,
            actor_user_id=project_ctx.user_id,
            assignee_user_id=payload.assignee_user_id,
            expected_version=payload.expected_version,
        )
        db_session.commit()
        _invalidate_project_caches(project_ctx.project.id)
    except ConcurrencyConflictError as exc:
        db_session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except Exception as exc:
        db_session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    has_manage = project_ctx.has_permission("project.manage")
    return _to_case_detail_response(
        case, db_session, viewer_user_id=project_ctx.user_id, has_manage=has_manage
    )


@router.post(
    "/projects/{project_id}/verification/findings/{finding_id}/review",
    response_model=VerificationCaseDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Directly review and verify, flag, or reject a knowledge finding in one atomic step",
)
def direct_review_finding(
    finding_id: uuid.UUID,
    payload: Annotated[DirectReviewFindingRequest, Body()],
    project_ctx: Annotated[
        ProjectContext, Depends(require_project_permission("project.knowledge.review"))
    ],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> VerificationCaseDetailResponse:
    repo = VerificationCaseRepository(db_session)
    existing_case = repo.get_by_target(
        project_ctx.project.id, VerificationTargetType.KNOWLEDGE_ITEM, finding_id
    )
    if not existing_case:
        item = db_session.get(KnowledgeItem, finding_id)
        if not item or item.project_id != project_ctx.project.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge item not found."
            )
        engine = DeterministicVerificationEngine(db_session)
        res = engine.assess_knowledge_item(item)
        existing_case = engine.persist_assessment(res)
        db_session.flush()

    service = HumanReviewService(db_session)
    act = payload.action.lower().strip()
    notes = payload.notes or f"Reviewed directly in Knowledge Intelligence ({act})"

    try:
        if act == "approve":
            case = service.approve(
                case_id=existing_case.id,
                reviewer_user_id=project_ctx.user_id,
                expected_version=existing_case.version,
                review_notes=notes,
            )
        elif act in ("flag", "mark_unresolved", "needs_clarification"):
            case = service.mark_unresolved(
                case_id=existing_case.id,
                reviewer_user_id=project_ctx.user_id,
                expected_version=existing_case.version,
                explanation=notes,
            )
        elif act == "reject":
            case = service.reject(
                case_id=existing_case.id,
                reviewer_user_id=project_ctx.user_id,
                expected_version=existing_case.version,
                review_notes=notes,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported review action '{payload.action}'. Must be 'approve', 'flag', or 'reject'.",
            )
        db_session.commit()
        _invalidate_project_caches(project_ctx.project.id)
    except ConcurrencyConflictError as exc:
        db_session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    has_manage = project_ctx.has_permission("project.manage")
    return _to_case_detail_response(
        case, db_session, viewer_user_id=project_ctx.user_id, has_manage=has_manage
    )


# ==============================================================================
# Context Requests
# ==============================================================================


@router.get(
    "/projects/{project_id}/verification/context-requests",
    response_model=list[VerificationContextRequestResponse],
    status_code=status.HTTP_200_OK,
    summary="List clarification requests directed to the current user",
)
def list_user_context_requests(
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
    status_filter: Annotated[ContextRequestStatus | None, Query()] = None,
) -> list[VerificationContextRequestResponse]:
    repo = VerificationContextRequestRepository(db_session)
    items = repo.list_by_user(project_ctx.project.id, project_ctx.user_id, status=status_filter)
    return [VerificationContextRequestResponse.model_validate(r) for r in items]


@router.post(
    "/projects/{project_id}/verification/context-requests/{request_id}/respond",
    response_model=VerificationContextRequestResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit response to clarification question",
)
def respond_context_request(
    request_id: uuid.UUID,
    payload: RespondContextRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> VerificationContextRequestResponse:
    repo = VerificationContextRequestRepository(db_session)
    req = repo.get_by_id(request_id)
    if not req or req.project_id != project_ctx.project.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Context request not found."
        )

    if req.requested_from_user_id != project_ctx.user_id and not project_ctx.has_permission(
        "project.knowledge.review"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to respond to this request.",
        )

    updated = repo.respond(
        request_id,
        payload.response_text,
        evidence_id=payload.response_evidence_id,
    )
    db_session.commit()
    return VerificationContextRequestResponse.model_validate(updated)


# ==============================================================================
# Handover Eligibility Gate
# ==============================================================================


@router.get(
    "/projects/{project_id}/verification/cases/{case_id}/eligibility",
    response_model=HandoverEligibilityResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify if finding is eligible for handover package inclusion",
)
def check_case_handover_eligibility(
    case_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> HandoverEligibilityResponse:
    case_repo = VerificationCaseRepository(db_session)
    case = case_repo.get_by_id(case_id, load_relationships=False)
    if not case or case.project_id != project_ctx.project.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Verification case not found."
        )

    has_manage = project_ctx.has_permission("project.manage")
    eligibility_service = HandoverEligibilityService(db_session)

    if case.target_type == VerificationTargetType.KNOWLEDGE_ITEM:
        res = eligibility_service.check_knowledge_item_eligibility(
            case.target_id,
            viewer_user_id=project_ctx.user_id,
            has_project_manage=has_manage,
        )
    else:
        res = eligibility_service.check_relationship_eligibility(
            case.target_id,
            viewer_user_id=project_ctx.user_id,
            has_project_manage=has_manage,
        )

    return HandoverEligibilityResponse(
        is_eligible=res.is_eligible,
        target_type=_str_val(res.target_type),
        target_id=res.target_id,
        case_status=res.case_status,
        epistemic_status=res.epistemic_status,
        blockers=res.blockers,
        warnings=res.warnings,
    )


# ==============================================================================
# Assessment Trigger (Deterministic)
# ==============================================================================


@router.post(
    "/projects/{project_id}/verification/assess",
    response_model=VerificationCaseDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger deterministic verification assessment on finding or relationship",
)
def trigger_deterministic_assessment(
    target_type: Annotated[VerificationTargetType, Query()],
    target_id: Annotated[uuid.UUID, Query()],
    project_ctx: Annotated[
        ProjectContext, Depends(require_project_permission("project.knowledge.review"))
    ],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> VerificationCaseDetailResponse:
    engine = DeterministicVerificationEngine(db_session)
    if target_type == VerificationTargetType.KNOWLEDGE_ITEM:
        item = db_session.get(KnowledgeItem, target_id)
        if not item or item.project_id != project_ctx.project.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge item not found."
            )
        res = engine.assess_knowledge_item(item)
    elif target_type == VerificationTargetType.RELATIONSHIP:
        rel = db_session.get(KnowledgeRelationship, target_id)
        if not rel or rel.project_id != project_ctx.project.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Relationship not found."
            )
        res = engine.assess_relationship(rel)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported target type."
        )

    case = engine.persist_assessment(res)
    db_session.commit()

    has_manage = project_ctx.has_permission("project.manage")
    return _to_case_detail_response(
        case, db_session, viewer_user_id=project_ctx.user_id, has_manage=has_manage
    )


@router.post(
    "/projects/{project_id}/verification/assess-all",
    response_model=VerificationSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Assess all project knowledge items and relationships deterministically",
)
def assess_all_project_items(
    project_ctx: Annotated[
        ProjectContext, Depends(require_project_permission("project.knowledge.review"))
    ],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> VerificationSummaryResponse:
    engine = DeterministicVerificationEngine(db_session)
    items = list(
        db_session.execute(
            select(KnowledgeItem).where(KnowledgeItem.project_id == project_ctx.project.id)
        )
        .scalars()
        .all()
    )
    for item in items:
        res = engine.assess_knowledge_item(item)
        engine.persist_assessment(res)

    rels = list(
        db_session.execute(
            select(KnowledgeRelationship).where(KnowledgeRelationship.project_id == project_ctx.project.id)
        )
        .scalars()
        .all()
    )
    for rel in rels:
        res = engine.assess_relationship(rel)
        engine.persist_assessment(res)

    db_session.commit()
    repo = VerificationCaseRepository(db_session)
    summary_data = repo.get_summary(project_ctx.project.id)
    return VerificationSummaryResponse(**summary_data)


# ==============================================================================
# Conflicts & Contradictions Endpoints
# ==============================================================================


def _enrich_conflict_response(c: VerificationConflict, db_session: Session) -> VerificationConflictResponse:
    target_id: uuid.UUID | None = None
    target_type: str | None = None
    target_title: str | None = None
    target_category: str | None = None

    if c.case:
        target_id = c.case.target_id
        target_type = _str_val(c.case.target_type)
        if c.case.target_type == VerificationTargetType.KNOWLEDGE_ITEM:
            ki = db_session.get(KnowledgeItem, c.case.target_id)
            if ki:
                target_title = ki.title
                target_category = _str_val(ki.category)
        elif c.case.target_type == VerificationTargetType.RELATIONSHIP:
            rel = db_session.get(KnowledgeRelationship, c.case.target_id)
            if rel:
                target_title = f"{rel.relationship_type.replace('_', ' ').title()}"
                target_category = "relationship"

    a_ev = c.claim_a_evidence
    b_ev = c.claim_b_evidence

    return VerificationConflictResponse(
        id=c.id,
        case_id=c.case_id,
        conflict_type=_str_val(c.conflict_type),
        claim_a_text=c.claim_a_text,
        claim_a_source_evidence_id=c.claim_a_source_evidence_id,
        claim_a_chunk_id=c.claim_a_chunk_id,
        claim_a_source_timestamp=c.claim_a_source_timestamp,
        claim_a_source_title=a_ev.title if a_ev else None,
        claim_a_source_type=_str_val(a_ev.source_type) if a_ev else None,
        claim_b_text=c.claim_b_text,
        claim_b_source_evidence_id=c.claim_b_source_evidence_id,
        claim_b_chunk_id=c.claim_b_chunk_id,
        claim_b_source_timestamp=c.claim_b_source_timestamp,
        claim_b_source_title=b_ev.title if b_ev else None,
        claim_b_source_type=_str_val(b_ev.source_type) if b_ev else None,
        explanation=c.explanation,
        temporal_comparison=_str_val(c.temporal_comparison),
        resolution_state=_str_val(c.resolution_state),
        resolution_notes=c.resolution_notes,
        resolved_by_user_id=c.resolved_by_user_id,
        resolved_at=c.resolved_at,
        created_at=c.created_at,
        target_id=target_id,
        target_type=target_type,
        target_title=target_title,
        target_category=target_category,
    )


@router.get(
    "/projects/{project_id}/conflicts",
    response_model=ConflictListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all detected cross-source conflicts for the project",
)
def list_project_conflicts(
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
    resolution_state: Annotated[str | None, Query()] = None,
    conflict_type: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ConflictListResponse:
    repo = VerificationConflictRepository(db_session)
    items, total = repo.list_by_project(
        project_ctx.project.id,
        resolution_state=resolution_state,
        conflict_type=conflict_type,
        limit=limit,
        offset=offset,
    )
    summary = repo.get_summary_by_project(project_ctx.project.id)

    enriched_items = [_enrich_conflict_response(c, db_session) for c in items]

    return ConflictListResponse(
        items=enriched_items,
        total=total,
        unresolved_count=summary["unresolved_count"],
        reconciled_count=summary["reconciled_count"],
        superseded_count=summary["superseded_count"],
        dismissed_count=summary["dismissed_count"],
    )


@router.get(
    "/projects/{project_id}/conflicts/summary",
    response_model=ConflictSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get aggregated conflict summary for the project",
)
def get_project_conflict_summary(
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> ConflictSummaryResponse:
    repo = VerificationConflictRepository(db_session)
    summary = repo.get_summary_by_project(project_ctx.project.id)
    return ConflictSummaryResponse(**summary)


@router.post(
    "/projects/{project_id}/conflicts/{conflict_id}/resolve",
    response_model=VerificationConflictResponse,
    status_code=status.HTTP_200_OK,
    summary="Adjudicate a cross-source conflict with mandatory human notes",
)
def resolve_conflict_endpoint(
    conflict_id: uuid.UUID,
    payload: ResolveConflictRequest,
    project_ctx: Annotated[
        ProjectContext, Depends(require_project_permission("project.knowledge.review"))
    ],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> VerificationConflictResponse:
    service = HumanReviewService(db_session)
    try:
        norm_state = payload.resolution_state.lower().strip()
        if norm_state not in ("reconciled", "superseded", "dismissed"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="resolution_state must be 'reconciled', 'superseded', or 'dismissed'",
            )
        res_state = ConflictResolutionState(norm_state)
        conflict = service.resolve_conflict(
            conflict_id=conflict_id,
            reviewer_user_id=project_ctx.user_id,
            resolution_state=res_state,
            resolution_notes=payload.resolution_notes,
            preferred_claim=payload.preferred_claim,
        )
        db_session.commit()
    except ReviewValidationError as exc:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except Exception as exc:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    return _enrich_conflict_response(conflict, db_session)


@router.post(
    "/projects/{project_id}/conflicts/detect",
    response_model=DetectConflictsResponse,
    status_code=status.HTTP_200_OK,
    summary="Run cross-source conflict detection on project knowledge items",
)
def detect_project_conflicts_endpoint(
    project_ctx: Annotated[
        ProjectContext, Depends(require_project_permission("project.knowledge.review"))
    ],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> DetectConflictsResponse:
    engine = ConflictDetectionEngine(db_session)
    new_conflicts = engine.detect_project_conflicts(project_ctx.project.id)
    db_session.commit()

    repo = VerificationConflictRepository(db_session)
    summary = repo.get_summary_by_project(project_ctx.project.id)

    return DetectConflictsResponse(
        detected_count=summary["total_conflicts"],
        new_conflicts_count=len(new_conflicts),
        message=f"Conflict detection completed. Found {summary['total_conflicts']} total contradictions across project sources.",
    )
