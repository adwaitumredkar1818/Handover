"""FastAPI routes for the Verification Center (Phase 1 Rebuild + Direct Review Bridge)."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, require_project_permission
from app.core.cache.local_cache import local_response_cache
from app.core.exceptions import NotFoundError
from app.models.evidence import EvidenceItem
from app.models.knowledge import KnowledgeItem
from app.models.verification import VerificationCase
from app.schemas.verification import (
    ApproveFindingRequest,
    AssignReviewerRequest,
    EditFindingRequest,
    MarkUnresolvedRequest,
    MonitorSourceChangeRequest,
    MonitorSourceChangeResponse,
    RejectFindingRequest,
    RequestContextRequest,
    RespondContextRequest,
    SyncAndAssessResponse,
    VerificationCaseDetailResponse,
    VerificationContextRequestDetail,
    VerificationQueueResponse,
    VerificationSummaryResponse,
)
from app.services.rbac import ProjectContext
from app.services.verification_engine import VerificationEngine
from app.services.verification_review import VerificationReviewService

router = APIRouter(tags=["Verification Center"])


def _invalidate_project_caches(project_id: uuid.UUID) -> None:
    """Clear short-lived L1 response caches on verification mutations."""
    local_response_cache.invalidate_prefix(f"ki_findings:{project_id}:")
    local_response_cache.invalidate_prefix(f"ki_graph:{project_id}:")
    local_response_cache.invalidate_prefix(f"ki_domains:{project_id}:")
    local_response_cache.invalidate_prefix(f"ki_summary:{project_id}:")
    local_response_cache.invalidate_prefix(f"rel_graph:{project_id}:")
    local_response_cache.invalidate_prefix(f"contrib_graph:{project_id}:")
    local_response_cache.invalidate_prefix(f"verification_summary:{project_id}:")


def _invalidate_ki_caches(project_id: uuid.UUID) -> None:
    _invalidate_project_caches(project_id)


class DirectReviewFindingRequest(BaseModel):
    action: str = Field(description="'approve', 'flag', or 'reject'")
    notes: str | None = Field(default=None)


class CaseEvidenceResponse(BaseModel):
    case_id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    supporting_evidence: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/projects/{project_id}/verification/target-case")
def ensure_target_verification_case(
    project_id: uuid.UUID,
    project_ctx: Annotated[
        ProjectContext, Depends(require_project_permission("project.knowledge.review"))
    ],
    session: Annotated[Session, Depends(get_db_session)],
    target_type: str = Query(...),
    target_id: uuid.UUID = Query(...),
) -> dict[str, object]:
    """Fast indexed lookup (or lazy sync) of a VerificationCase by target_type + target_id."""
    vc = session.execute(
        select(VerificationCase).where(
            VerificationCase.project_id == project_ctx.project.id,
            VerificationCase.target_type == target_type,
            VerificationCase.target_id == target_id,
        )
    ).scalar_one_or_none()
    if vc is None:
        VerificationEngine(session).sync_project_findings(project_ctx.project.id)
        session.commit()
        vc = session.execute(
            select(VerificationCase).where(
                VerificationCase.project_id == project_ctx.project.id,
                VerificationCase.target_type == target_type,
                VerificationCase.target_id == target_id,
            )
        ).scalar_one_or_none()
    if vc is None:
        raise NotFoundError("Verification case not found for target.", code="VERIFICATION_CASE_NOT_FOUND")
    return {
        "id": str(vc.id),
        "version": vc.version,
        "case_status": str(getattr(vc.case_status, "value", vc.case_status)),
    }
@router.get(
    "/projects/{project_id}/verification/summary",
    response_model=VerificationSummaryResponse,
)
def get_verification_summary(
    project_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> VerificationSummaryResponse:
    service = VerificationReviewService(session)
    return service.get_summary(project_ctx.project.id, project_ctx=project_ctx)


@router.get(
    "/projects/{project_id}/verification/queue",
    response_model=VerificationQueueResponse,
)
def list_verification_queue(
    project_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    session: Annotated[Session, Depends(get_db_session)],
    status: str | None = Query(default=None),
    domain: str | None = Query(default=None),
    person: str | None = Query(default=None),
    source: str | None = Query(default=None),
    reviewer_id: uuid.UUID | None = Query(default=None),
    category: str | None = Query(default=None),
    search: str | None = Query(default=None),
    sort_by: str = Query(default="updated_at"),
    sort_dir: str = Query(default="desc"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> VerificationQueueResponse:
    service = VerificationReviewService(session)
    return service.list_queue(
        project_ctx.project.id,
        project_ctx=project_ctx,
        status=status,
        domain=domain,
        person=person,
        source=source,
        reviewer_id=reviewer_id,
        category=category,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/projects/{project_id}/verification/cases/{case_id}",
    response_model=VerificationCaseDetailResponse,
)
def get_verification_case_detail(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> VerificationCaseDetailResponse:
    service = VerificationReviewService(session)
    return service.get_case_detail(case_id, project_ctx=project_ctx)


@router.get(
    "/projects/{project_id}/verification/cases/{case_id}/evidence",
    response_model=CaseEvidenceResponse,
)
def get_verification_case_evidence(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> CaseEvidenceResponse:
    service = VerificationReviewService(session)
    detail = service.get_case_detail(case_id, project_ctx=project_ctx)
    supporting: list[dict[str, Any]] = []
    for ref in detail.evidence_references:
        supporting.append(ref.model_dump(mode="json"))
    return CaseEvidenceResponse(
        case_id=detail.id,
        target_type=detail.target_type,
        target_id=detail.target_id,
        supporting_evidence=supporting,
        conflicts=[],
    )


@router.post(
    "/projects/{project_id}/verification/sync",
    response_model=SyncAndAssessResponse,
)
def sync_and_assess_verification(
    project_id: uuid.UUID,
    project_ctx: Annotated[
        ProjectContext, Depends(require_project_permission("project.knowledge.review"))
    ],
    session: Annotated[Session, Depends(get_db_session)],
) -> SyncAndAssessResponse:
    engine = VerificationEngine(session)
    sync_res = engine.sync_project_findings(project_ctx.project.id)
    assess_res = engine.assess_project(project_ctx.project.id)
    session.commit()
    _invalidate_project_caches(project_ctx.project.id)
    return SyncAndAssessResponse(
        project_id=project_ctx.project.id,
        cases_created=sync_res["cases_created"],
        cases_updated=sync_res["cases_updated"],
        cases_assessed=assess_res["cases_assessed"],
        issues_detected=assess_res["issues_detected"],
    )


@router.post(
    "/projects/{project_id}/verification/assess",
    response_model=SyncAndAssessResponse,
)
def run_verification_checks(
    project_id: uuid.UUID,
    project_ctx: Annotated[
        ProjectContext, Depends(require_project_permission("project.knowledge.review"))
    ],
    session: Annotated[Session, Depends(get_db_session)],
    case_id: uuid.UUID | None = Query(default=None),
) -> SyncAndAssessResponse:
    engine = VerificationEngine(session)
    assess_res = engine.assess_project(project_ctx.project.id, case_id=case_id)
    session.commit()
    _invalidate_project_caches(project_ctx.project.id)
    return SyncAndAssessResponse(
        project_id=project_ctx.project.id,
        cases_assessed=assess_res["cases_assessed"],
        issues_detected=assess_res["issues_detected"],
    )


@router.post(
    "/projects/{project_id}/verification/cases/{case_id}/approve",
    response_model=VerificationCaseDetailResponse,
)
def approve_verification_case(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    payload: ApproveFindingRequest,
    project_ctx: Annotated[
        ProjectContext, Depends(require_project_permission("project.knowledge.review"))
    ],
    session: Annotated[Session, Depends(get_db_session)],
) -> VerificationCaseDetailResponse:
    service = VerificationReviewService(session)
    res = service.approve_case(case_id, project_ctx=project_ctx, payload=payload)
    _invalidate_project_caches(project_ctx.project.id)
    return res


@router.post(
    "/projects/{project_id}/verification/cases/{case_id}/reject",
    response_model=VerificationCaseDetailResponse,
)
def reject_verification_case(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    payload: RejectFindingRequest,
    project_ctx: Annotated[
        ProjectContext, Depends(require_project_permission("project.knowledge.review"))
    ],
    session: Annotated[Session, Depends(get_db_session)],
) -> VerificationCaseDetailResponse:
    service = VerificationReviewService(session)
    res = service.reject_case(case_id, project_ctx=project_ctx, payload=payload)
    _invalidate_project_caches(project_ctx.project.id)
    return res


@router.patch(
    "/projects/{project_id}/verification/cases/{case_id}/finding",
    response_model=VerificationCaseDetailResponse,
)
def edit_verification_finding(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    payload: EditFindingRequest,
    project_ctx: Annotated[
        ProjectContext, Depends(require_project_permission("project.knowledge.review"))
    ],
    session: Annotated[Session, Depends(get_db_session)],
) -> VerificationCaseDetailResponse:
    service = VerificationReviewService(session)
    res = service.edit_finding(case_id, project_ctx=project_ctx, payload=payload)
    _invalidate_project_caches(project_ctx.project.id)
    return res


@router.post(
    "/projects/{project_id}/verification/cases/{case_id}/request-context",
    response_model=VerificationCaseDetailResponse,
)
def request_additional_context(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    payload: RequestContextRequest,
    project_ctx: Annotated[
        ProjectContext, Depends(require_project_permission("project.knowledge.review"))
    ],
    session: Annotated[Session, Depends(get_db_session)],
) -> VerificationCaseDetailResponse:
    service = VerificationReviewService(session)
    res = service.request_context(case_id, project_ctx=project_ctx, payload=payload)
    _invalidate_project_caches(project_ctx.project.id)
    return res


@router.get(
    "/projects/{project_id}/verification/context-requests",
    response_model=list[VerificationContextRequestDetail],
)
def list_context_requests(
    project_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    session: Annotated[Session, Depends(get_db_session)],
    case_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
) -> list[VerificationContextRequestDetail]:
    service = VerificationReviewService(session)
    return service.list_context_requests(
        project_ctx.project.id,
        project_ctx=project_ctx,
        case_id=case_id,
        status=status,
    )


@router.post(
    "/projects/{project_id}/verification/context-requests/{request_id}/respond",
    response_model=VerificationContextRequestDetail,
)
def respond_to_context_request(
    project_id: uuid.UUID,
    request_id: uuid.UUID,
    payload: RespondContextRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> VerificationContextRequestDetail:
    service = VerificationReviewService(session)
    res = service.respond_context_request(
        request_id, project_ctx=project_ctx, payload=payload
    )
    _invalidate_project_caches(project_ctx.project.id)
    return res


@router.post(
    "/projects/{project_id}/verification/cases/{case_id}/mark-unresolved",
    response_model=VerificationCaseDetailResponse,
)
def mark_case_unresolved(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    payload: MarkUnresolvedRequest,
    project_ctx: Annotated[
        ProjectContext, Depends(require_project_permission("project.knowledge.review"))
    ],
    session: Annotated[Session, Depends(get_db_session)],
) -> VerificationCaseDetailResponse:
    service = VerificationReviewService(session)
    res = service.mark_unresolved(case_id, project_ctx=project_ctx, payload=payload)
    _invalidate_project_caches(project_ctx.project.id)
    return res


@router.post(
    "/projects/{project_id}/verification/cases/{case_id}/assign",
    response_model=VerificationCaseDetailResponse,
)
def assign_case_reviewer(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    payload: AssignReviewerRequest,
    project_ctx: Annotated[
        ProjectContext, Depends(require_project_permission("project.knowledge.review"))
    ],
    session: Annotated[Session, Depends(get_db_session)],
) -> VerificationCaseDetailResponse:
    service = VerificationReviewService(session)
    res = service.assign_reviewer(
        case_id,
        project_ctx=project_ctx,
        assigned_reviewer_id=payload.assigned_reviewer_id,
    )
    _invalidate_project_caches(project_ctx.project.id)
    return res


@router.post(
    "/projects/{project_id}/verification/findings/{finding_id}/review",
    response_model=VerificationCaseDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Directly review and verify, flag, or reject a knowledge finding in one atomic step",
)
def direct_review_finding(
    project_id: uuid.UUID,
    finding_id: uuid.UUID,
    payload: Annotated[DirectReviewFindingRequest, Body()],
    project_ctx: Annotated[
        ProjectContext, Depends(require_project_permission("project.knowledge.review"))
    ],
    session: Annotated[Session, Depends(get_db_session)],
) -> VerificationCaseDetailResponse:
    engine = VerificationEngine(session)
    # Ensure finding has an associated verification case
    sync_res = engine.sync_project_findings(project_ctx.project.id)
    service = VerificationReviewService(session)
    
    # Locate case for this finding
    queue = service.list_queue(project_ctx.project.id, project_ctx=project_ctx, limit=200)
    target_case = next((item for item in queue.items if item.target_id == finding_id), None)
    
    if not target_case:
        item = session.get(KnowledgeItem, finding_id)
        if not item or item.project_id != project_ctx.project.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge item not found."
            )
        assess_res = engine.assess_project(project_ctx.project.id)
        session.commit()
        queue = service.list_queue(project_ctx.project.id, project_ctx=project_ctx, limit=200)
        target_case = next((it for it in queue.items if it.target_id == finding_id), None)

    if not target_case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Verification case for finding could not be established."
        )

    act = payload.action.lower().strip()
    notes = payload.notes or f"Reviewed directly in Knowledge Intelligence ({act})"

    if act == "approve":
        res = service.approve_case(
            target_case.id,
            project_ctx=project_ctx,
            payload=ApproveFindingRequest(reviewer_note=notes),
        )
    elif act in ("flag", "mark_unresolved", "needs_clarification"):
        res = service.mark_unresolved(
            target_case.id,
            project_ctx=project_ctx,
            payload=MarkUnresolvedRequest(reviewer_note=notes, decision_reason=notes),
        )
    elif act == "reject":
        res = service.reject_case(
            target_case.id,
            project_ctx=project_ctx,
            payload=RejectFindingRequest(reviewer_note=notes, rejection_category="incorrect_claim"),
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported review action '{payload.action}'. Must be 'approve', 'flag', or 'reject'.",
        )

    _invalidate_project_caches(project_ctx.project.id)
    return res


@router.post(
    "/projects/{project_id}/verification/monitor-change",
    response_model=MonitorSourceChangeResponse,
)
def monitor_source_change(
    project_id: uuid.UUID,
    payload: MonitorSourceChangeRequest,
    project_ctx: Annotated[
        ProjectContext, Depends(require_project_permission("project.knowledge.review"))
    ],
    session: Annotated[Session, Depends(get_db_session)],
) -> MonitorSourceChangeResponse:
    ev = session.get(EvidenceItem, payload.evidence_id)
    if ev is None or ev.project_id != project_ctx.project.id:
        raise NotFoundError("Evidence record not found in this project.")
    engine = VerificationEngine(session)
    impact = engine.monitor_source_change(
        project_id=project_ctx.project.id,
        evidence_item=ev,
        change_type=payload.change_type,
        triggered_by_user_id=project_ctx.principal.user.id,
    )
    session.commit()
    _invalidate_project_caches(project_ctx.project.id)
    return MonitorSourceChangeResponse(
        evidence_id=impact.evidence_id,
        change_type=impact.change_type,
        affected_case_ids=impact.affected_case_ids,
        reverification_triggered=impact.reverification_triggered,
        summary=impact.summary,
    )
