"""FastAPI HTTP endpoints for Handover Workspace (Module 4 / Knowledge Transfer Area).

Provides:
- Handover case management and 14-state lifecycle progression
- Deterministic 8-domain package assembly and versioning
- 9-category readiness evaluation with blocker gating
- Dynamic offboarding checklists and task completion tracking
- Responsibility transfer mapping (departing -> successor)
- Three-phase human sign-offs (departing -> reviewer -> successor)
- Secure package delivery and receipt acknowledgement
- Explicit internal ownership transfers with rollback capability
- AI-assisted narrative drafting and section editing
- Handover eligibility verification gate checks
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import (
    get_db_session,
    get_llm_client,
    require_project_permission,
)
from app.core.cache.local_cache import local_response_cache
from app.core.exceptions import ForbiddenError
from app.models.enums import RoleName, SignoffType, VerificationTargetType
from app.models.handover import HandoverCase, ProjectOnboardingProgress
from app.repositories.handover import (
    HandoverCaseRepository,
    HandoverPackageVersionRepository,
    HandoverReadinessRepository,
    HandoverSectionRepository,
    HandoverSignoffRepository,
)
from app.schemas.handover import (
    AcknowledgementRequest,
    ChecklistItemCreateRequest,
    ChecklistItemReviewRequest,
    ChecklistItemUpdateRequest,
    DeliveryClarificationRequest,
    DeliveryRequest,
    HandoverAcknowledgementResponse,
    HandoverCaseCreateRequest,
    HandoverCaseDetailResponse,
    HandoverCaseListItem,
    HandoverCaseResponse,
    HandoverCaseUpdateRequest,
    HandoverChecklistItemResponse,
    HandoverChecklistResponse,
    HandoverChecklistWorkspaceResponse,
    HandoverContentLinkResponse,
    HandoverContextContributionRequest,
    HandoverContextContributionResponse,
    HandoverDeliveryResponse,
    HandoverEligibilityCheckResponse,
    HandoverOwnershipTransferResponse,
    HandoverPackageDetailResponse,
    HandoverPackageResponse,
    HandoverPackageVersionResponse,
    HandoverReadinessAssessmentResponse,
    HandoverReadinessSummaryResponse,
    HandoverResponsibilityTransferResponse,
    HandoverResponsibilityWorkspaceResponse,
    HandoverSectionResponse,
    HandoverSignoffResponse,
    HandoverSignoffWorkspaceResponse,
    HandoverStatusHistoryResponse,
    HandoverVersionSectionsResponse,
    NarrativeDraftRequest,
    OnboardingProgressResponse,
    OnboardingStepProgressItem,
    OwnershipTransferRequest,
    OwnershipTransferRollbackRequest,
    PackageAssemblyRequest,
    PaginatedHandoverCaseResponse,
    ReadinessAssessmentRequest,
    ResponsibilityClarificationRequest,
    ResponsibilityOutgoingConfirmRequest,
    ResponsibilityReopenRequest,
    ResponsibilitySuccessorAckRequest,
    ResponsibilityTransferBulkRequest,
    ResponsibilityTransferUpdateRequest,
    ReviewerAssignRequest,
    SectionEditRequest,
    SignoffPhaseReopenRequest,
    SignoffRequest,
    UpdateOnboardingStepRequest,
)
from app.services.handover_assembly import PackageAssemblyService
from app.services.handover_case import (
    HandoverCaseService,
    is_unapproved_draft_restricted_for_successor,
)
from app.services.handover_checklist import ChecklistService
from app.services.handover_sections import HandoverSectionReadService
from app.services.handover_eligibility import HandoverEligibilityService
from app.services.handover_export import HandoverExportService
from app.services.handover_narrative import HandoverNarrativeService
from app.services.handover_ownership import OwnershipTransferService
from app.services.handover_readiness import HandoverReadinessEngine
from app.services.handover_signoff import HandoverSignoffService
from app.services.llm import StructuredLLMClient
from app.services.rbac import ProjectContext

def _invalidate_handover_workspace_cache(project_id: uuid.UUID) -> None:
    local_response_cache.invalidate_prefix(f"handover_ws:{project_id}:")
    from app.services.handover_sections import invalidate_handover_sections_cache

    invalidate_handover_sections_cache(project_id)


def _auto_invalidate_on_mutation(request: Request, project_id: uuid.UUID):
    yield
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        _invalidate_handover_workspace_cache(project_id)


def _cached_handover_get(cache_key: str, builder: Any, *, ttl_seconds: int = 300) -> Any:
    if not os.getenv("PYTEST_CURRENT_TEST"):
        cached = local_response_cache.get(cache_key)
        if cached is not None:
            return cached
    result = builder()
    if not os.getenv("PYTEST_CURRENT_TEST"):
        local_response_cache.set(cache_key, jsonable_encoder(result), ttl_seconds=ttl_seconds)
    return result


router = APIRouter(
    prefix="/projects/{project_id}/handover",
    tags=["Handover Workspace"],
    dependencies=[Depends(_auto_invalidate_on_mutation)],
)


def _can_review_or_manage_handover(project_ctx: ProjectContext) -> bool:
    return any(
        project_ctx.has_permission(p)
        for p in (
            "handover.review",
            "handover.approve",
            "handover.deliver",
            "handover.admin",
            "project.manage",
        )
    )


def _enforce_successor_draft_gate(case: HandoverCase, project_ctx: ProjectContext) -> None:
    if is_unapproved_draft_restricted_for_successor(
        case,
        viewer_user_id=project_ctx.user_id,
        can_review_or_manage=_can_review_or_manage_handover(project_ctx),
    ):
        raise ForbiddenError(
            "Incoming successor cannot access unapproved handover drafts before formal publication."
        )


# ---------------------------------------------------------------------------
# 1. Handover Cases
# ---------------------------------------------------------------------------


@router.get(
    "/cases",
    response_model=PaginatedHandoverCaseResponse,
    summary="List project handover cases",
)
def list_handover_cases(
    project_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.read"))],
    session: Annotated[Session, Depends(get_db_session)],
    status: str | None = Query(None, description="Filter by HandoverCaseStatus"),
    departing_member_id: uuid.UUID | None = Query(None),
    successor_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedHandoverCaseResponse:
    """List handover cases in the current project with pagination and filters."""
    can_bypass = _can_review_or_manage_handover(project_ctx)
    cache_key = (
        f"handover_ws:{project_id}:cases:{project_ctx.user_id}:{int(can_bypass)}:"
        f"{status or ''}:{departing_member_id or ''}:{successor_id or ''}:{page}:{page_size}"
    )

    def _build() -> PaginatedHandoverCaseResponse:
        service = HandoverCaseService(session)
        offset = (page - 1) * page_size
        items, total = service.list_cases(
            project_id=project_id,
            status=status,
            departing_member_id=departing_member_id,
            successor_id=successor_id,
            offset=offset,
            limit=page_size,
        )
        visible_items = [
            c
            for c in items
            if not is_unapproved_draft_restricted_for_successor(
                c, viewer_user_id=project_ctx.user_id, can_review_or_manage=can_bypass
            )
        ]
        adjusted_total = max(0, total - (len(items) - len(visible_items)))
        total_pages = (adjusted_total + page_size - 1) // page_size if adjusted_total > 0 else 0
        return PaginatedHandoverCaseResponse(
            items=[
                HandoverCaseListItem(
                    id=c.id,
                    project_id=c.project_id,
                    title=c.title,
                    status=c.status,
                    version=c.version,
                    departing_member_id=c.departing_member_id,
                    successor_id=c.successor_id,
                    assigned_reviewer_id=c.assigned_reviewer_id,
                    target_handover_date=c.target_handover_date,
                    metadata_json=c.metadata_json or {},
                    created_at=c.created_at,
                    updated_at=c.updated_at,
                )
                for c in visible_items
            ],
            total=adjusted_total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    return _cached_handover_get(cache_key, _build)


@router.post(
    "/cases",
    response_model=HandoverCaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new handover case",
)
def create_handover_case(
    project_id: uuid.UUID,
    request: HandoverCaseCreateRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.create"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverCaseResponse:
    """Create a new handover case in DRAFT status."""
    service = HandoverCaseService(session)
    case = service.create_case(
        organisation_id=project_ctx.organisation.id,
        project_id=project_id,
        user_id=project_ctx.user_id,
        request=request,
    )
    session.commit()
    return HandoverCaseResponse.model_validate(case)


@router.get(
    "/cases/{case_id}",
    response_model=HandoverCaseDetailResponse,
    summary="Get full handover case details",
)
def get_handover_case_details(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.read"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverCaseDetailResponse:
    """Get comprehensive case details including package versions, signoffs, and history."""
    can_manage_or_review = _can_review_or_manage_handover(project_ctx)
    cache_key = f"handover_ws:{project_id}:case:{case_id}:{project_ctx.user_id}:{int(can_manage_or_review)}"

    def _build() -> HandoverCaseDetailResponse:
        service = HandoverCaseService(session)
        case = service.get_case(case_id, project_id=project_id, load_relationships=True)
        _enforce_successor_draft_gate(case, project_ctx)

        packages = [HandoverPackageResponse.model_validate(case.package)] if case.package else []
        current_version = next((v for v in case.versions if v.is_current), None)

        return HandoverCaseDetailResponse(
            case=HandoverCaseResponse.model_validate(case),
            packages=packages,
            current_version=HandoverPackageVersionResponse.model_validate(current_version) if current_version else None,
            signoffs=[HandoverSignoffResponse.model_validate(s) for s in case.signoffs],
            status_history=[HandoverStatusHistoryResponse.model_validate(h) for h in case.status_history],
            responsibility_transfers=[
                HandoverResponsibilityTransferResponse.model_validate(t)
                for t in case.responsibility_transfers
            ],
        )

    return _cached_handover_get(cache_key, _build)


@router.patch(
    "/cases/{case_id}",
    response_model=HandoverCaseResponse,
    summary="Update handover case metadata",
)
def update_handover_case(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    request: HandoverCaseUpdateRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.edit"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverCaseResponse:
    """Update title, description, or successor of an editable handover case."""
    service = HandoverCaseService(session)
    updated = service.update_case(
        case_id,
        project_id=project_id,
        user_id=project_ctx.user_id,
        request=request,
    )
    session.commit()
    return HandoverCaseResponse.model_validate(updated)


@router.post(
    "/cases/{case_id}/context",
    response_model=HandoverContextContributionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Contribute missing handover context or undocumented decision as candidate knowledge",
)
def contribute_handover_context(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    request: HandoverContextContributionRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.edit"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverContextContributionResponse:
    """Persist departing or team member context as attributable candidate knowledge pending Verification Center review."""
    service = HandoverCaseService(session)
    result = service.contribute_context(
        case_id=case_id,
        project_id=project_id,
        user_id=project_ctx.user_id,
        request=request,
    )
    session.commit()
    return result


# ---------------------------------------------------------------------------
# 2. Package Assembly & Versions
# ---------------------------------------------------------------------------


@router.post(
    "/cases/{case_id}/assemble",
    response_model=HandoverPackageVersionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Assemble handover package version",
)
def assemble_handover_package(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    request: PackageAssemblyRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.compile"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverPackageVersionResponse:
    """Compile human-approved project knowledge deterministically into an immutable package version (no LLM)."""
    service = PackageAssemblyService(session)
    has_manage = project_ctx.has_permission("project.manage")
    version = service.assemble_package_version(
        case_id=case_id,
        project_id=project_id,
        user_id=project_ctx.user_id,
        request=request,
        has_project_manage=has_manage,
    )
    session.commit()
    return HandoverPackageVersionResponse.model_validate(version)


@router.get(
    "/cases/{case_id}/versions",
    response_model=list[HandoverPackageVersionResponse],
    summary="List package versions for a case",
)
def list_package_versions(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.read"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> list[HandoverPackageVersionResponse]:
    """List all version snapshots compiled for this handover case."""
    can_manage_or_review = _can_review_or_manage_handover(project_ctx)
    cache_key = f"handover_ws:{project_id}:versions:{case_id}:{project_ctx.user_id}:{int(can_manage_or_review)}"

    def _build() -> list[HandoverPackageVersionResponse]:
        case_repo = HandoverCaseRepository(session)
        case = case_repo.get_by_id(case_id, load_relationships=False)
        if not case or case.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
        _enforce_successor_draft_gate(case, project_ctx)

        version_repo = HandoverPackageVersionRepository(session)
        if case.package:
            versions = version_repo.list_by_package(case.package.id)
        else:
            versions = []
        return [HandoverPackageVersionResponse.model_validate(v) for v in versions]

    return _cached_handover_get(cache_key, _build)


@router.get(
    "/cases/{case_id}/versions/{version_id}",
    response_model=HandoverPackageDetailResponse,
    summary="Get package version details with sections",
)
def get_package_version_details(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    version_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.read"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverPackageDetailResponse:
    """Get full package version content including 8 domain sections and content links."""
    version_repo = HandoverPackageVersionRepository(session)
    version = version_repo.get_by_id(version_id, load_sections=True)
    if not version or version.project_id != project_id or version.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")
    case = HandoverCaseRepository(session).get_by_id(case_id, load_relationships=False)
    if case is not None:
        _enforce_successor_draft_gate(case, project_ctx)

    readiness_repo = HandoverReadinessRepository(session)
    readiness_summary = None
    if readiness_repo.list_by_version(version_id):
        readiness_summary = HandoverReadinessEngine(session).get_readiness_intelligence(
            case_id=case_id,
            version_id=version_id,
            project_id=project_id,
            viewer_user_id=project_ctx.user_id,
            has_project_manage=project_ctx.has_permission("project.manage"),
        )

    checklist_repo = ChecklistService(session)
    checklists = checklist_repo.list_checklists(case_id, project_id=project_id)

    sections_res = [
        HandoverSectionResponse(
            id=s.id,
            version_id=s.version_id,
            section_type=s.section_type,
            section_title=s.section_title,
            section_content=s.section_content,
            content_summary=s.content_summary,
            section_order=s.section_order,
            knowledge_item_count=s.knowledge_item_count,
            relationship_count=s.relationship_count,
            metadata_json=s.metadata_json or {},
            created_at=s.created_at,
            updated_at=s.created_at,
        )
        for s in version.sections
    ]

    checklists_res = [
        HandoverChecklistResponse(
            id=c.id,
            case_id=c.case_id,
            generated_for_version_id=c.version_id,
            checklist_type=c.checklist_type,
            created_at=c.created_at,
            items=[
                HandoverChecklistItemResponse.model_validate(i) for i in c.items
            ],
        )
        for c in checklists
    ]

    return HandoverPackageDetailResponse(
        version=HandoverPackageVersionResponse.model_validate(version),
        sections=sections_res,
        readiness=readiness_summary,
        checklists=checklists_res,
    )


@router.get(
    "/cases/{case_id}/versions/{version_id}/sections",
    response_model=HandoverVersionSectionsResponse,
    summary="Get canonical eight-domain and ten-mandatory handover sections with provenance",
)
def get_package_version_sections(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    version_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.read"))],
    session: Annotated[Session, Depends(get_db_session)],
    role: str | None = Query(
        None,
        description="Optional handover presentation role: 'developer', 'project_manager', or 'technical_lead'",
    ),
) -> HandoverVersionSectionsResponse:
    """Retrieve canonical persisted sections, ten mandatory sections, ACL-checked provenance,
    and epistemic/conflict separation for a specific handover case and package version.
    Read-only: never mutates the package or historical versions.
    """
    case = HandoverCaseRepository(session).get_by_id(case_id, load_relationships=False)
    if case is not None and case.project_id == project_id:
        _enforce_successor_draft_gate(case, project_ctx)

    service = HandoverSectionReadService(session)
    return service.get_version_sections(
        case_id=case_id,
        version_id=version_id,
        project_id=project_id,
        viewer_user_id=project_ctx.user_id,
        has_project_manage=project_ctx.has_permission("project.manage"),
        role_override=role,
    )


# ---------------------------------------------------------------------------
# 3. Readiness Assessments
# ---------------------------------------------------------------------------


@router.post(
    "/cases/{case_id}/readiness",
    response_model=HandoverReadinessSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Assess package readiness",
)
def assess_package_readiness(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    request: ReadinessAssessmentRequest,
    project_ctx: Annotated[
        ProjectContext, Depends(require_project_permission("handover.readiness.assess"))
    ],
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverReadinessSummaryResponse:
    """Run 9-category readiness evaluation across verified knowledge for a package version."""
    version_repo = HandoverPackageVersionRepository(session)
    version = version_repo.get_by_id(request.version_id, load_sections=False)
    if not version or version.project_id != project_id or version.case_id != case_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Package version not found for this handover case and project.",
        )

    engine = HandoverReadinessEngine(session)
    summary = engine.assess_version(
        version_id=request.version_id,
        project_id=project_id,
        user_id=project_ctx.user_id,
        notes=request.notes,
        has_project_manage=project_ctx.has_permission("project.manage"),
    )
    session.commit()
    return summary


@router.get(
    "/cases/{case_id}/readiness/{version_id}",
    response_model=HandoverReadinessSummaryResponse,
    summary="Get live readiness intelligence summary for a package version",
)
def get_readiness_assessment(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    version_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.read"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverReadinessSummaryResponse:
    """Get previously computed 9-category readiness scores enriched with live
    Verification Center, Conflict Management, Checklist, Evidence Quality, and
    authoritative Approval Eligibility intelligence. Strictly scoped to project & case.
    """
    has_manage = project_ctx.has_permission("project.manage")
    cache_key = f"handover_ws:{project_id}:readiness:{case_id}:{version_id}:{project_ctx.user_id}:{int(has_manage)}"

    def _build() -> HandoverReadinessSummaryResponse:
        case = HandoverCaseRepository(session).get_by_id(case_id, load_relationships=False)
        if case is not None and case.project_id == project_id:
            _enforce_successor_draft_gate(case, project_ctx)

        engine = HandoverReadinessEngine(session)
        return engine.get_readiness_intelligence(
            case_id=case_id,
            version_id=version_id,
            project_id=project_id,
            viewer_user_id=project_ctx.user_id,
            has_project_manage=has_manage,
        )

    return _cached_handover_get(cache_key, _build)


# ---------------------------------------------------------------------------
# 4. Transition Checklists (Stage 5 Complete)
# ---------------------------------------------------------------------------


@router.post(
    "/cases/{case_id}/checklists/generate",
    response_model=list[HandoverChecklistResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Idempotently generate transition checklists",
)
def generate_checklists(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.edit"))],
    session: Annotated[Session, Depends(get_db_session)],
    version_id: uuid.UUID | None = Query(None),
) -> list[HandoverChecklistResponse]:
    """Idempotently generate standard transition checklists (pre-handover, knowledge-transfer, access)."""
    service = ChecklistService(session)
    service.generate_checklists_for_case(
        case_id=case_id,
        project_id=project_id,
        user_id=project_ctx.user_id,
        version_id=version_id,
    )
    session.commit()
    workspace = service.get_checklist_workspace(
        case_id,
        project_id=project_id,
        viewer_user_id=project_ctx.user_id,
        has_project_manage=project_ctx.has_permission("project.manage"),
    )
    return workspace.checklists


@router.get(
    "/cases/{case_id}/checklists",
    response_model=list[HandoverChecklistResponse],
    summary="List hydrated checklists for a case",
)
def list_case_checklists(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.read"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> list[HandoverChecklistResponse]:
    """List all checklists and ACL-checked items attached to this handover case."""
    service = ChecklistService(session)
    workspace = service.get_checklist_workspace(
        case_id,
        project_id=project_id,
        viewer_user_id=project_ctx.user_id,
        has_project_manage=project_ctx.has_permission("project.manage"),
    )
    return workspace.checklists


@router.get(
    "/cases/{case_id}/checklists/workspace",
    response_model=HandoverChecklistWorkspaceResponse,
    summary="Get full Stage 5 transition checklist workspace with metrics and audit history",
)
def get_checklist_workspace(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.read"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverChecklistWorkspaceResponse:
    """Retrieve complete Stage 5 checklist workspace, overdue/blocked metrics, ACL-checked evidence, and audit log."""
    has_manage = project_ctx.has_permission("project.manage")
    cache_key = f"handover_ws:{project_id}:checklists:{case_id}:{project_ctx.user_id}:{int(has_manage)}"

    def _build() -> HandoverChecklistWorkspaceResponse:
        service = ChecklistService(session)
        return service.get_checklist_workspace(
            case_id,
            project_id=project_id,
            viewer_user_id=project_ctx.user_id,
            has_project_manage=has_manage,
        )

    return _cached_handover_get(cache_key, _build)


@router.post(
    "/cases/{case_id}/checklists/{checklist_id}/items",
    response_model=HandoverChecklistItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a custom checklist item",
)
def create_checklist_item(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    checklist_id: uuid.UUID,
    request: ChecklistItemCreateRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.edit"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverChecklistItemResponse:
    """Create a custom transition checklist item with active participant and project evidence validation."""
    service = ChecklistService(session)
    item = service.create_item(
        case_id=case_id,
        checklist_id=checklist_id,
        project_id=project_id,
        user_id=project_ctx.user_id,
        request=request,
    )
    session.commit()
    return service.hydrate_item_response(
        item,
        project_id=project_id,
        viewer_user_id=project_ctx.user_id,
        has_project_manage=project_ctx.has_permission("project.manage"),
    )


@router.patch(
    "/checklists/items/{item_id}",
    response_model=HandoverChecklistItemResponse,
    summary="Update checklist item status, assignment, due date, evidence, or reopen",
)
def update_checklist_item(
    project_id: uuid.UUID,
    item_id: uuid.UUID,
    request: ChecklistItemUpdateRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.edit"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverChecklistItemResponse:
    """Update status, assignee, due date, completion notes, evidence attachment, or reopen with mandatory reason."""
    service = ChecklistService(session)
    item = service.update_item_status(
        item_id=item_id,
        project_id=project_id,
        user_id=project_ctx.user_id,
        request=request,
    )
    session.commit()
    return service.hydrate_item_response(
        item,
        project_id=project_id,
        viewer_user_id=project_ctx.user_id,
        has_project_manage=project_ctx.has_permission("project.manage"),
    )


@router.post(
    "/checklists/items/{item_id}/review",
    response_model=HandoverChecklistItemResponse,
    summary="Independently verify or reopen a completed checklist item",
)
def review_checklist_item(
    project_id: uuid.UUID,
    item_id: uuid.UUID,
    request: ChecklistItemReviewRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.review"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverChecklistItemResponse:
    """Record independent reviewer verification of a completed checklist item (separation of duties enforced)."""
    service = ChecklistService(session)
    is_org_admin = project_ctx.organisation_role.name in (
        RoleName.ORG_OWNER.value,
        RoleName.ORG_ADMIN.value,
    )
    item = service.review_item(
        item_id=item_id,
        project_id=project_id,
        reviewer_user_id=project_ctx.user_id,
        request=request,
        is_org_admin=is_org_admin,
    )
    session.commit()
    return service.hydrate_item_response(
        item,
        project_id=project_id,
        viewer_user_id=project_ctx.user_id,
        has_project_manage=project_ctx.has_permission("project.manage"),
    )


# ---------------------------------------------------------------------------
# 5. Responsibilities & Ownership Transfer (Stage 5 Complete)
# ---------------------------------------------------------------------------


@router.post(
    "/cases/{case_id}/responsibilities",
    response_model=list[HandoverResponsibilityTransferResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Map departing member responsibilities",
)
def create_responsibility_transfers(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    request: ResponsibilityTransferBulkRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.edit"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> list[HandoverResponsibilityTransferResponse]:
    """Define explicit responsibility transfer mappings validated against active project members."""
    service = OwnershipTransferService(session)
    created = service.create_responsibility_transfers(
        case_id=case_id,
        project_id=project_id,
        user_id=project_ctx.user_id,
        request=request,
    )
    session.commit()
    created_ids = {t.id for t in created}
    workspace = service.get_responsibility_workspace(
        case_id=case_id,
        project_id=project_id,
        viewer_user_id=project_ctx.user_id,
        has_project_manage=project_ctx.has_permission("project.manage"),
    )
    return [t for t in workspace.transfers if t.id in created_ids]


@router.get(
    "/cases/{case_id}/responsibilities",
    response_model=list[HandoverResponsibilityTransferResponse],
    summary="List hydrated responsibility transfers",
)
def list_responsibility_transfers(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.read"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> list[HandoverResponsibilityTransferResponse]:
    """List mapped responsibilities enriched with 8-domain knowledge and ACL-checked evidence."""
    service = OwnershipTransferService(session)
    workspace = service.get_responsibility_workspace(
        case_id=case_id,
        project_id=project_id,
        viewer_user_id=project_ctx.user_id,
        has_project_manage=project_ctx.has_permission("project.manage"),
    )
    return workspace.transfers


@router.get(
    "/cases/{case_id}/responsibilities/workspace",
    response_model=HandoverResponsibilityWorkspaceResponse,
    summary="Get full Stage 5 responsibility transfer & ownership management workspace",
)
def get_responsibility_workspace(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.read"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverResponsibilityWorkspaceResponse:
    """Return full Stage 5 responsibility workspace with validation issues, eligible participants, candidates & audit history."""
    has_manage = project_ctx.has_permission("project.manage")
    cache_key = f"handover_ws:{project_id}:resp:{case_id}:{project_ctx.user_id}:{int(has_manage)}"

    def _build() -> HandoverResponsibilityWorkspaceResponse:
        service = OwnershipTransferService(session)
        return service.get_responsibility_workspace(
            case_id=case_id,
            project_id=project_id,
            viewer_user_id=project_ctx.user_id,
            has_project_manage=has_manage,
        )

    return _cached_handover_get(cache_key, _build)


@router.patch(
    "/responsibilities/{transfer_id}",
    response_model=HandoverResponsibilityTransferResponse,
    summary="Update responsibility transfer details, successor, or operational status",
)
def update_responsibility_status(
    project_id: uuid.UUID,
    transfer_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.edit"))],
    session: Annotated[Session, Depends(get_db_session)],
    body: ResponsibilityTransferUpdateRequest | None = Body(default=None),
    status_value: str | None = Query(None, alias="status"),
    notes: str | None = Query(None),
) -> HandoverResponsibilityTransferResponse:
    """Update responsibility transfer details, reassign successor, or update status."""
    service = OwnershipTransferService(session)
    if body is not None:
        updated = service.update_responsibility_transfer(
            transfer_id=transfer_id,
            project_id=project_id,
            user_id=project_ctx.user_id,
            request=body,
        )
    elif status_value is not None:
        updated = service.update_responsibility_status(
            transfer_id=transfer_id,
            project_id=project_id,
            user_id=project_ctx.user_id,
            status=status_value,
            notes=notes,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide a JSON update body or status query parameter.",
        )
    session.commit()
    workspace = service.get_responsibility_workspace(
        case_id=updated.case_id,
        project_id=project_id,
        viewer_user_id=project_ctx.user_id,
        has_project_manage=project_ctx.has_permission("project.manage"),
    )
    for t in workspace.transfers:
        if t.id == updated.id:
            return t
    return HandoverResponsibilityTransferResponse.model_validate(updated)


@router.post(
    "/responsibilities/{transfer_id}/confirm-outgoing",
    response_model=HandoverResponsibilityTransferResponse,
    summary="Outgoing-owner confirmation of responsibility transfer preparation",
)
def confirm_responsibility_outgoing(
    project_id: uuid.UUID,
    transfer_id: uuid.UUID,
    request: ResponsibilityOutgoingConfirmRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.edit"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverResponsibilityTransferResponse:
    """Outgoing owner confirms responsibility transfer is ready for successor acknowledgement."""
    service = OwnershipTransferService(session)
    can_manage = project_ctx.has_permission("project.manage") or project_ctx.organisation_role.name in (
        RoleName.ORG_OWNER.value,
        RoleName.ORG_ADMIN.value,
    )
    updated = service.confirm_outgoing_owner(
        transfer_id=transfer_id,
        project_id=project_id,
        user_id=project_ctx.user_id,
        request=request,
        can_manage_project=can_manage,
    )
    session.commit()
    workspace = service.get_responsibility_workspace(
        case_id=updated.case_id,
        project_id=project_id,
        viewer_user_id=project_ctx.user_id,
        has_project_manage=project_ctx.has_permission("project.manage"),
    )
    for t in workspace.transfers:
        if t.id == updated.id:
            return t
    return HandoverResponsibilityTransferResponse.model_validate(updated)


@router.post(
    "/responsibilities/{transfer_id}/acknowledge",
    response_model=HandoverResponsibilityTransferResponse,
    summary="Receiving-successor acknowledgement of transferred responsibility",
)
def acknowledge_responsibility_successor(
    project_id: uuid.UUID,
    transfer_id: uuid.UUID,
    request: ResponsibilitySuccessorAckRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.acknowledge"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverResponsibilityTransferResponse:
    """Designated incoming successor explicitly acknowledges receipt & understanding (distinct from managerial approval)."""
    service = OwnershipTransferService(session)
    updated = service.acknowledge_as_successor(
        transfer_id=transfer_id,
        project_id=project_id,
        user_id=project_ctx.user_id,
        request=request,
    )
    session.commit()
    workspace = service.get_responsibility_workspace(
        case_id=updated.case_id,
        project_id=project_id,
        viewer_user_id=project_ctx.user_id,
        has_project_manage=project_ctx.has_permission("project.manage"),
    )
    for t in workspace.transfers:
        if t.id == updated.id:
            return t
    return HandoverResponsibilityTransferResponse.model_validate(updated)


@router.post(
    "/responsibilities/{transfer_id}/clarify",
    response_model=HandoverResponsibilityTransferResponse,
    summary="Request or respond to clarification on a responsibility transfer",
)
def clarify_responsibility_transfer(
    project_id: uuid.UUID,
    transfer_id: uuid.UUID,
    request: ResponsibilityClarificationRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.read"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverResponsibilityTransferResponse:
    """Successor requests clarification or outgoing owner posts a clarification response."""
    service = OwnershipTransferService(session)
    can_manage = project_ctx.has_permission("handover.review") or project_ctx.has_permission("project.manage")
    updated = service.handle_clarification(
        transfer_id=transfer_id,
        project_id=project_id,
        user_id=project_ctx.user_id,
        request=request,
        can_manage_project=can_manage,
    )
    session.commit()
    workspace = service.get_responsibility_workspace(
        case_id=updated.case_id,
        project_id=project_id,
        viewer_user_id=project_ctx.user_id,
        has_project_manage=project_ctx.has_permission("project.manage"),
    )
    for t in workspace.transfers:
        if t.id == updated.id:
            return t
    return HandoverResponsibilityTransferResponse.model_validate(updated)


@router.post(
    "/responsibilities/{transfer_id}/reopen",
    response_model=HandoverResponsibilityTransferResponse,
    summary="Reopen an acknowledged responsibility transfer with mandatory rationale",
)
def reopen_responsibility_transfer(
    project_id: uuid.UUID,
    transfer_id: uuid.UUID,
    request: ResponsibilityReopenRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.edit"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverResponsibilityTransferResponse:
    """Reopen a responsibility transfer requiring further review or clarification."""
    service = OwnershipTransferService(session)
    can_manage = project_ctx.has_permission("project.manage") or project_ctx.organisation_role.name in (
        RoleName.ORG_OWNER.value,
        RoleName.ORG_ADMIN.value,
    )
    updated = service.reopen_transfer(
        transfer_id=transfer_id,
        project_id=project_id,
        user_id=project_ctx.user_id,
        request=request,
        can_manage_project=can_manage,
    )
    session.commit()
    workspace = service.get_responsibility_workspace(
        case_id=updated.case_id,
        project_id=project_id,
        viewer_user_id=project_ctx.user_id,
        has_project_manage=project_ctx.has_permission("project.manage"),
    )
    for t in workspace.transfers:
        if t.id == updated.id:
            return t
    return HandoverResponsibilityTransferResponse.model_validate(updated)


# ---------------------------------------------------------------------------
# 6. Sign-Offs, Approval, Publication & Recipient Acknowledgement (Stage 6)
# ---------------------------------------------------------------------------


@router.get(
    "/cases/{case_id}/signoffs/workspace",
    response_model=HandoverSignoffWorkspaceResponse,
    summary="Get complete Stage 6 signoff, approval, publication & recipient workspace",
)
def get_handover_signoff_workspace(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.read"))],
    session: Annotated[Session, Depends(get_db_session)],
    version_id: uuid.UUID | None = Query(None),
) -> HandoverSignoffWorkspaceResponse:
    """Return authoritative three-phase signoff status, 4-gate approval eligibility, publication state, and recipient acknowledgements."""
    is_org_admin = project_ctx.organisation_role.name in (
        RoleName.ORG_OWNER.value,
        RoleName.ORG_ADMIN.value,
    )
    can_review = project_ctx.has_permission("handover.review")
    can_approve = project_ctx.has_permission("handover.approve")
    can_deliver = project_ctx.has_permission("handover.deliver")
    can_acknowledge = project_ctx.has_permission("handover.acknowledge")
    has_manage = project_ctx.has_permission("project.manage")
    cache_key = (
        f"handover_ws:{project_id}:signoffs:{case_id}:{version_id or 'cur'}:{project_ctx.user_id}:"
        f"{int(is_org_admin)}:{int(can_review)}:{int(can_approve)}:{int(can_deliver)}:{int(can_acknowledge)}:{int(has_manage)}"
    )

    def _build() -> HandoverSignoffWorkspaceResponse:
        service = HandoverSignoffService(session)
        return service.get_signoff_workspace(
            case_id=case_id,
            project_id=project_id,
            viewer_user_id=project_ctx.user_id,
            version_id=version_id,
            is_org_admin=is_org_admin,
            can_review=can_review,
            can_approve=can_approve,
            can_deliver=can_deliver,
            can_acknowledge=can_acknowledge,
            has_project_manage=has_manage,
        )

    return _cached_handover_get(cache_key, _build)


@router.post(
    "/cases/{case_id}/signoffs",
    response_model=HandoverSignoffResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit human sign-off decision",
)
def submit_handover_signoff(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    request: SignoffRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.read"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverSignoffResponse:
    """Submit Phase 1 (departing), Phase 2 (independent reviewer approval/rejection/change request), or Phase 3 (recipient ack)."""
    is_org_admin = project_ctx.organisation_role.name in (
        RoleName.ORG_OWNER.value,
        RoleName.ORG_ADMIN.value,
    )
    # Phase-specific RBAC enforcement
    if request.signoff_type == SignoffType.DEPARTING_SIGNOFF.value:
        if not (
            project_ctx.has_permission("handover.edit")
            or project_ctx.has_permission("handover.review")
            or is_org_admin
        ):
            raise ForbiddenError("Permission 'handover.edit' or 'handover.review' required for Phase 1 sign-off.")
    elif request.signoff_type == SignoffType.REVIEWER_APPROVAL.value:
        if not (
            project_ctx.has_permission("handover.review")
            or project_ctx.has_permission("handover.approve")
            or is_org_admin
        ):
            raise ForbiddenError("Permission 'handover.review' required for Phase 2 reviewer decisions.")
    elif request.signoff_type == SignoffType.SUCCESSOR_ACKNOWLEDGEMENT.value:
        if not project_ctx.has_permission("handover.acknowledge"):
            raise ForbiddenError("Permission 'handover.acknowledge' required for Phase 3 recipient acknowledgement.")

    service = HandoverSignoffService(session)
    signoff = service.submit_signoff(
        case_id=case_id,
        project_id=project_id,
        user_id=project_ctx.user_id,
        request=request,
        is_org_admin=is_org_admin,
        can_approve=project_ctx.has_permission("handover.approve"),
        has_project_manage=project_ctx.has_permission("project.manage"),
    )
    session.commit()
    return HandoverSignoffResponse.model_validate(signoff)


@router.get(
    "/cases/{case_id}/signoffs",
    response_model=list[HandoverSignoffResponse],
    summary="List sign-offs for case",
)
def list_handover_signoffs(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.read"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> list[HandoverSignoffResponse]:
    """List all human sign-offs recorded for this handover case (strictly scoped to project)."""
    HandoverCaseService(session).get_case(case_id, project_id=project_id, load_relationships=False)
    repo = HandoverSignoffRepository(session)
    signoffs = repo.list_by_case(case_id)
    return [HandoverSignoffResponse.model_validate(s) for s in signoffs]


@router.post(
    "/cases/{case_id}/signoffs/reviewer",
    response_model=HandoverSignoffWorkspaceResponse,
    summary="Assign or reassign an eligible independent reviewer",
)
def assign_handover_reviewer(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    request: ReviewerAssignRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.admin"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverSignoffWorkspaceResponse:
    """Assign an active independent project member (not departing owner) as case reviewer."""
    service = HandoverSignoffService(session)
    service.assign_reviewer(
        case_id=case_id,
        project_id=project_id,
        actor_user_id=project_ctx.user_id,
        request=request,
    )
    session.commit()
    is_org_admin = project_ctx.organisation_role.name in (
        RoleName.ORG_OWNER.value,
        RoleName.ORG_ADMIN.value,
    )
    return service.get_signoff_workspace(
        case_id=case_id,
        project_id=project_id,
        viewer_user_id=project_ctx.user_id,
        is_org_admin=is_org_admin,
        can_review=project_ctx.has_permission("handover.review"),
        can_approve=project_ctx.has_permission("handover.approve"),
        can_deliver=project_ctx.has_permission("handover.deliver"),
        can_acknowledge=project_ctx.has_permission("handover.acknowledge"),
        has_project_manage=project_ctx.has_permission("project.manage"),
    )


@router.post(
    "/cases/{case_id}/signoffs/reopen",
    response_model=HandoverSignoffWorkspaceResponse,
    summary="Reopen a signoff phase with mandatory audit rationale",
)
def reopen_handover_signoff_phase(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    request: SignoffPhaseReopenRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.approve"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverSignoffWorkspaceResponse:
    """Explicitly reopen Phase 1 or Phase 2 prior to publication, preserving prior signoffs immutably."""
    service = HandoverSignoffService(session)
    service.reopen_signoff_phase(
        case_id=case_id,
        project_id=project_id,
        actor_user_id=project_ctx.user_id,
        request=request,
    )
    session.commit()
    is_org_admin = project_ctx.organisation_role.name in (
        RoleName.ORG_OWNER.value,
        RoleName.ORG_ADMIN.value,
    )
    return service.get_signoff_workspace(
        case_id=case_id,
        project_id=project_id,
        viewer_user_id=project_ctx.user_id,
        is_org_admin=is_org_admin,
        can_review=project_ctx.has_permission("handover.review"),
        can_approve=project_ctx.has_permission("handover.approve"),
        can_deliver=project_ctx.has_permission("handover.deliver"),
        can_acknowledge=project_ctx.has_permission("handover.acknowledge"),
        has_project_manage=project_ctx.has_permission("project.manage"),
    )


@router.post(
    "/cases/{case_id}/deliver",
    response_model=list[HandoverDeliveryResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Publish and deliver approved package version",
)
def deliver_handover_package(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    request: DeliveryRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.deliver"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> list[HandoverDeliveryResponse]:
    """Publish an approved, integrity-verified package version to eligible active recipients."""
    service = HandoverSignoffService(session)
    deliveries = service.deliver_package(
        case_id=case_id,
        project_id=project_id,
        user_id=project_ctx.user_id,
        request=request,
    )
    session.commit()
    return [HandoverDeliveryResponse.model_validate(d) for d in deliveries]


@router.post(
    "/deliveries/{delivery_id}/acknowledge",
    response_model=HandoverAcknowledgementResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Recipient formal acknowledgement of published handover package",
)
def acknowledge_delivery(
    project_id: uuid.UUID,
    delivery_id: uuid.UUID,
    request: AcknowledgementRequest,
    project_ctx: Annotated[
        ProjectContext, Depends(require_project_permission("handover.acknowledge"))
    ],
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverAcknowledgementResponse:
    """Designated recipient submits formal acknowledgement of complete published handover package."""
    service = HandoverSignoffService(session)
    ack = service.acknowledge_delivery(
        delivery_id=delivery_id,
        project_id=project_id,
        user_id=project_ctx.user_id,
        request=request,
    )
    session.commit()
    return HandoverAcknowledgementResponse.model_validate(ack)


@router.post(
    "/deliveries/{delivery_id}/clarify",
    response_model=HandoverDeliveryResponse,
    summary="Request or respond to clarification on a published handover package",
)
def clarify_handover_delivery(
    project_id: uuid.UUID,
    delivery_id: uuid.UUID,
    request: DeliveryClarificationRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.read"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverDeliveryResponse:
    """Recipient raises a clarification request or outgoing owner/manager posts a response without mutating the published snapshot."""
    service = HandoverSignoffService(session)
    can_manage = project_ctx.has_permission("project.manage") or project_ctx.has_permission("handover.deliver")
    updated = service.handle_delivery_clarification(
        delivery_id=delivery_id,
        project_id=project_id,
        user_id=project_ctx.user_id,
        request=request,
        can_manage_project=can_manage,
    )
    session.commit()
    workspace = service.get_signoff_workspace(
        case_id=updated.case_id,
        project_id=project_id,
        viewer_user_id=project_ctx.user_id,
        version_id=updated.version_id,
        has_project_manage=project_ctx.has_permission("project.manage"),
    )
    for d in workspace.publication.deliveries:
        if d.id == updated.id:
            return d
    return HandoverDeliveryResponse.model_validate(updated)


# ---------------------------------------------------------------------------
# 7. Ownership Transfer (Separate Operation)
# ---------------------------------------------------------------------------


@router.post(
    "/cases/{case_id}/transfer-ownership",
    response_model=HandoverOwnershipTransferResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Execute explicit project ownership transfer",
)
def transfer_project_ownership(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    request: OwnershipTransferRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.transfer"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverOwnershipTransferResponse:
    """Execute an explicit project ownership transfer after package approval and delivery."""
    service = OwnershipTransferService(session)
    transfer = service.execute_ownership_transfer(
        case_id=case_id,
        project_id=project_id,
        user_id=project_ctx.user_id,
        request=request,
    )
    session.commit()
    return HandoverOwnershipTransferResponse.model_validate(transfer)


@router.post(
    "/ownership-transfers/{transfer_id}/rollback",
    response_model=HandoverOwnershipTransferResponse,
    status_code=status.HTTP_200_OK,
    summary="Rollback an ownership transfer",
)
def rollback_ownership_transfer(
    project_id: uuid.UUID,
    transfer_id: uuid.UUID,
    request: OwnershipTransferRollbackRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.admin"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverOwnershipTransferResponse:
    """Revert a previously executed ownership transfer with documented reason."""
    service = OwnershipTransferService(session)
    rolled_back = service.rollback_ownership_transfer(
        transfer_id=transfer_id,
        project_id=project_id,
        user_id=project_ctx.user_id,
        request=request,
    )
    session.commit()
    return HandoverOwnershipTransferResponse.model_validate(rolled_back)


# ---------------------------------------------------------------------------
# 8. Narrative Drafting & Section Editing
# ---------------------------------------------------------------------------


@router.post(
    "/cases/{case_id}/narrative/draft",
    summary="Draft narrative for a section",
)
def draft_section_narrative(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    request: NarrativeDraftRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.edit"))],
    session: Annotated[Session, Depends(get_db_session)],
    llm_client: Annotated[StructuredLLMClient | None, Depends(get_llm_client)] = None,
) -> dict[str, Any]:
    """Generate an AI draft narrative grounded strictly in verified findings for a section."""
    service = HandoverNarrativeService(session, llm_client=llm_client)
    return service.draft_section_narrative(
        project_id=project_id,
        case_id=case_id,
        request=request,
        viewer_user_id=project_ctx.user_id,
        has_project_manage=project_ctx.has_permission("project.manage"),
    )


@router.patch(
    "/sections/{section_id}",
    response_model=HandoverSectionResponse,
    summary="Edit section content",
)
def edit_section_content(
    project_id: uuid.UUID,
    section_id: uuid.UUID,
    request: SectionEditRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.edit"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverSectionResponse:
    """Human editor edits section content narrative text or summary."""
    service = HandoverNarrativeService(session)
    updated = service.edit_section_content(
        section_id=section_id,
        project_id=project_id,
        user_id=project_ctx.user_id,
        request=request,
    )
    session.commit()
    return HandoverSectionResponse(
        id=updated.id,
        version_id=updated.version_id,
        section_type=updated.section_type,
        section_title=updated.section_title,
        section_content=updated.section_content,
        content_summary=updated.content_summary,
        section_order=updated.section_order,
        knowledge_item_count=updated.knowledge_item_count,
        relationship_count=updated.relationship_count,
        created_at=updated.created_at,
        updated_at=updated.created_at,
    )


# ---------------------------------------------------------------------------
# 9. Eligibility Gate Check
# ---------------------------------------------------------------------------


@router.get(
    "/eligibility/{target_type}/{target_id}",
    response_model=HandoverEligibilityCheckResponse,
    summary="Check handover eligibility for a knowledge item or relationship",
)
def check_handover_eligibility(
    project_id: uuid.UUID,
    target_type: str,
    target_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.read"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> HandoverEligibilityCheckResponse:
    """Pre-check whether a knowledge item or relationship edge meets handover eligibility rules."""
    service = HandoverEligibilityService(session)
    has_manage = project_ctx.has_permission("project.manage")
    if target_type == VerificationTargetType.KNOWLEDGE_ITEM.value:
        res = service.check_knowledge_item_eligibility(
            target_id,
            viewer_user_id=project_ctx.user_id,
            has_project_manage=has_manage,
            project_id=project_id,
        )
    elif target_type == VerificationTargetType.RELATIONSHIP.value:
        res = service.check_relationship_eligibility(
            target_id,
            viewer_user_id=project_ctx.user_id,
            has_project_manage=has_manage,
            project_id=project_id,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid target type '{target_type}'. Must be 'knowledge_item' or 'relationship'.",
        )

    if res.case_status == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{target_type} {target_id} not found in this project.",
        )

    return HandoverEligibilityCheckResponse(
        target_type=target_type,
        target_id=target_id,
        is_eligible=res.is_eligible,
        case_status=res.case_status,
        epistemic_status=res.epistemic_status,
        blockers=res.blockers,
        warnings=res.warnings,
    )


# ---------------------------------------------------------------------------
# 10. Handover Package Export (Markdown, JSON, PDF)
# ---------------------------------------------------------------------------


@router.get(
    "/cases/{case_id}/export",
    summary="Export handover package in Markdown, JSON, or PDF format",
)
def export_handover_package(
    project_id: uuid.UUID,
    case_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("handover.read"))],
    session: Annotated[Session, Depends(get_db_session)],
    format: str = Query("markdown", description="Export format: 'markdown', 'json', or 'pdf'"),
    version_id: uuid.UUID | None = Query(None, description="Optional specific package version UUID"),
    role: str | None = Query(
        None,
        description="Optional handover presentation role: 'developer', 'project_manager', or 'technical_lead'",
    ),
) -> Any:
    """Export a viewer-authorized handover package with strict per-request source ACL filtering and secret redaction."""
    service = HandoverExportService(session)
    fmt = format.lower().strip()
    has_manage = project_ctx.has_permission("project.manage")
    can_bypass = _can_review_or_manage_handover(project_ctx)

    try:
        if fmt == "markdown":
            md_content = service.export_markdown(
                project_id=project_id,
                case_id=case_id,
                user_id=project_ctx.user_id,
                version_id=version_id,
                has_project_manage=has_manage,
                can_review_or_manage=can_bypass,
                role_override=role,
            )
            session.commit()
            return PlainTextResponse(
                content=md_content,
                media_type="text/markdown",
                headers={
                    "Content-Disposition": f"attachment; filename=handover_case_{case_id}.md"
                },
            )
        elif fmt == "json":
            json_data = service.export_json(
                project_id=project_id,
                case_id=case_id,
                user_id=project_ctx.user_id,
                version_id=version_id,
                has_project_manage=has_manage,
                can_review_or_manage=can_bypass,
                role_override=role,
            )
            session.commit()
            return json_data
        elif fmt == "pdf":
            pdf_bytes = service.export_pdf(
                project_id=project_id,
                case_id=case_id,
                user_id=project_ctx.user_id,
                version_id=version_id,
                has_project_manage=has_manage,
                can_review_or_manage=can_bypass,
                role_override=role,
            )
            session.commit()
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename=handover_case_{case_id}.pdf"
                },
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported export format '{format}'. Supported formats are: 'markdown', 'json', 'pdf'.",
            )
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(val_err),
        ) from val_err


# ---------------------------------------------------------------------------
# Project Successor Onboarding Progress Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/onboarding/progress",
    response_model=OnboardingProgressResponse,
    summary="Get user's onboarding progress for a project",
)
def get_onboarding_progress(
    project_id: uuid.UUID,
    project_ctx: Annotated[
        ProjectContext, Depends(require_project_permission("project.read"))
    ],
    session: Annotated[Session, Depends(get_db_session)],
    target_user_id: uuid.UUID | None = Query(
        None, description="Optional user ID (requires project.manage if not self)"
    ),
) -> OnboardingProgressResponse:
    effective_user_id = project_ctx.principal.user.id
    if target_user_id and target_user_id != effective_user_id:
        if not project_ctx.has_permission("project.manage"):
            raise ForbiddenError(
                "Only project managers can view another member's onboarding progress."
            )
        effective_user_id = target_user_id

    records = (
        session.execute(
            select(ProjectOnboardingProgress).where(
                ProjectOnboardingProgress.project_id == project_ctx.project.id,
                ProjectOnboardingProgress.user_id == effective_user_id,
            )
        )
        .scalars()
        .all()
    )

    completed_map = {r.step_id: r.is_completed for r in records}
    items = [
        OnboardingStepProgressItem(
            step_id=r.step_id,
            is_completed=r.is_completed,
            completed_at=r.completed_at,
        )
        for r in records
    ]

    return OnboardingProgressResponse(
        project_id=project_ctx.project.id,
        user_id=effective_user_id,
        completed_steps=completed_map,
        items=items,
    )


@router.put(
    "/onboarding/progress/{step_id}",
    response_model=OnboardingStepProgressItem,
    summary="Update or set completion state for an onboarding step",
)
def update_onboarding_step(
    project_id: uuid.UUID,
    step_id: str,
    payload: UpdateOnboardingStepRequest,
    project_ctx: Annotated[
        ProjectContext, Depends(require_project_permission("project.read"))
    ],
    session: Annotated[Session, Depends(get_db_session)],
) -> OnboardingStepProgressItem:
    clean_step = step_id.strip()
    if not clean_step or len(clean_step) > 64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Step ID must be non-empty and at most 64 characters.",
        )

    user_id = project_ctx.principal.user.id
    record = (
        session.execute(
            select(ProjectOnboardingProgress).where(
                ProjectOnboardingProgress.project_id == project_ctx.project.id,
                ProjectOnboardingProgress.user_id == user_id,
                ProjectOnboardingProgress.step_id == clean_step,
            )
        )
        .scalars()
        .first()
    )

    now = datetime.now(timezone.utc)
    if record is None:
        record = ProjectOnboardingProgress(
            organisation_id=project_ctx.project.organisation_id,
            project_id=project_ctx.project.id,
            user_id=user_id,
            step_id=clean_step,
            is_completed=payload.is_completed,
            completed_at=now if payload.is_completed else None,
        )
        session.add(record)
    else:
        record.is_completed = payload.is_completed
        record.completed_at = now if payload.is_completed else None
        record.updated_at = now

    session.commit()
    session.refresh(record)

    return OnboardingStepProgressItem(
        step_id=record.step_id,
        is_completed=record.is_completed,
        completed_at=record.completed_at,
    )


@router.delete(
    "/onboarding/progress/{step_id}",
    summary="Delete completion record for an onboarding step",
)
def delete_onboarding_step(
    project_id: uuid.UUID,
    step_id: str,
    project_ctx: Annotated[
        ProjectContext, Depends(require_project_permission("project.read"))
    ],
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, str]:
    clean_step = step_id.strip()
    user_id = project_ctx.principal.user.id
    record = (
        session.execute(
            select(ProjectOnboardingProgress).where(
                ProjectOnboardingProgress.project_id == project_ctx.project.id,
                ProjectOnboardingProgress.user_id == user_id,
                ProjectOnboardingProgress.step_id == clean_step,
            )
        )
        .scalars()
        .first()
    )

    if record:
        session.delete(record)
        session.commit()

    return {"status": "deleted", "step_id": clean_step}

