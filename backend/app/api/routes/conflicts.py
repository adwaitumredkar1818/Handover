"""FastAPI routes for the Conflict Management Workspace."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, require_project_permission
from app.schemas.conflicts import (
    AddInvestigationNotesRequest,
    AssignConflictReviewerRequest,
    ConflictDashboardMetrics,
    ConflictDetailResponse,
    ConflictListResponse,
    ReopenConflictRequest,
    RequestConflictContextRequest,
    ResolveConflictRequest,
    StartInvestigationRequest,
)
from app.services.conflict_service import ConflictService
from app.services.rbac import ProjectContext
from app.services.verification_engine import VerificationEngine

router = APIRouter(tags=["Conflict Management"])


@router.get(
    "/projects/{project_id}/conflicts/dashboard",
    response_model=ConflictDashboardMetrics,
)
@router.get(
    "/projects/{project_id}/conflicts/summary",
    response_model=ConflictDashboardMetrics,
)
def get_conflict_dashboard(
    project_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> ConflictDashboardMetrics:
    """Fetch high-level metrics for the Conflict Management Dashboard."""
    service = ConflictService(session)
    return service.get_dashboard_metrics(
        project_ctx.project.id,
        user_id=project_ctx.user_id,
        has_manage=project_ctx.has_permission("project.manage"),
    )


@router.get(
    "/projects/{project_id}/conflicts",
    response_model=ConflictListResponse,
)
def list_conflicts(
    project_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    session: Annotated[Session, Depends(get_db_session)],
    conflict_type: str | None = Query(None, description="Filter by 6 canonical conflict categories"),
    resolution_state: str | None = Query(None, description="Filter by status (open, under_investigation, awaiting_context, resolved, reopened)"),
    priority: str | None = Query(None, description="Filter by priority (critical, high, medium, low)"),
    assigned_to: uuid.UUID | None = Query(None, description="Filter by assigned reviewer"),
    search: str | None = Query(None, description="Search claim text, sources, or explanation"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ConflictListResponse:
    """List conflicts matching query filters."""
    service = ConflictService(session)
    return service.list_conflicts(
        project_ctx.project.id,
        user_id=project_ctx.user_id,
        has_manage=project_ctx.has_permission("project.manage"),
        conflict_type=conflict_type,
        resolution_state=resolution_state,
        priority=priority,
        assigned_to=assigned_to,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/projects/{project_id}/conflicts/{conflict_id}",
    response_model=ConflictDetailResponse,
)
def get_conflict_details(
    project_id: uuid.UUID,
    conflict_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> ConflictDetailResponse:
    """Fetch complete side-by-side comparative inspection for a contradiction."""
    service = ConflictService(session)
    has_manage = project_ctx.has_permission("project.manage")
    return service.get_conflict_details(
        conflict_id,
        project_ctx.project.id,
        project_ctx.user_id,
        has_manage=has_manage,
    )


@router.post(
    "/projects/{project_id}/conflicts/{conflict_id}/assign",
    response_model=ConflictDetailResponse,
)
def assign_conflict_reviewer(
    project_id: uuid.UUID,
    conflict_id: uuid.UUID,
    req: AssignConflictReviewerRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.manage"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> ConflictDetailResponse:
    """Assign an investigator to a contradiction."""
    service = ConflictService(session)
    res = service.assign_reviewer(
        conflict_id,
        project_ctx.project.id,
        project_ctx.user_id,
        req.reviewer_id,
        notes=req.notes,
    )
    session.commit()
    return res


@router.post(
    "/projects/{project_id}/conflicts/{conflict_id}/investigate",
    response_model=ConflictDetailResponse,
)
def start_conflict_investigation(
    project_id: uuid.UUID,
    conflict_id: uuid.UUID,
    req: StartInvestigationRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.manage"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> ConflictDetailResponse:
    """Advance status to under_investigation."""
    service = ConflictService(session)
    res = service.start_investigation(
        conflict_id,
        project_ctx.project.id,
        project_ctx.user_id,
        notes=req.notes,
    )
    session.commit()
    return res


@router.post(
    "/projects/{project_id}/conflicts/{conflict_id}/request-context",
    response_model=ConflictDetailResponse,
)
def request_conflict_context(
    project_id: uuid.UUID,
    conflict_id: uuid.UUID,
    req: RequestConflictContextRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.manage"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> ConflictDetailResponse:
    """Place contradiction in awaiting_context state with specific information requests."""
    service = ConflictService(session)
    res = service.request_context(
        conflict_id,
        project_ctx.project.id,
        project_ctx.user_id,
        context_queries=req.context_queries,
        notes=req.notes,
    )
    session.commit()
    return res


@router.post(
    "/projects/{project_id}/conflicts/{conflict_id}/notes",
    response_model=ConflictDetailResponse,
)
def add_conflict_investigation_notes(
    project_id: uuid.UUID,
    conflict_id: uuid.UUID,
    req: AddInvestigationNotesRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.manage"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> ConflictDetailResponse:
    """Record an investigator note."""
    service = ConflictService(session)
    res = service.add_notes(
        conflict_id,
        project_ctx.project.id,
        project_ctx.user_id,
        notes=req.notes,
    )
    session.commit()
    return res


@router.post(
    "/projects/{project_id}/conflicts/{conflict_id}/resolve",
    response_model=ConflictDetailResponse,
)
def resolve_conflict(
    project_id: uuid.UUID,
    conflict_id: uuid.UUID,
    req: ResolveConflictRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.manage"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> ConflictDetailResponse:
    """Formally resolve a contradiction using human-guided resolution strategies."""
    service = ConflictService(session)
    res = service.resolve_conflict(
        conflict_id,
        project_ctx.project.id,
        project_ctx.user_id,
        req,
    )
    session.commit()
    return res


@router.post(
    "/projects/{project_id}/conflicts/{conflict_id}/reopen",
    response_model=ConflictDetailResponse,
)
def reopen_conflict(
    project_id: uuid.UUID,
    conflict_id: uuid.UUID,
    req: ReopenConflictRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.manage"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> ConflictDetailResponse:
    """Reopen a previously resolved contradiction."""
    service = ConflictService(session)
    res = service.reopen_conflict(
        conflict_id,
        project_ctx.project.id,
        project_ctx.user_id,
        reason=req.reason,
    )
    session.commit()
    return res


@router.post(
    "/projects/{project_id}/conflicts/sync",
)
@router.post(
    "/projects/{project_id}/conflicts/detect",
)
def sync_conflicts(
    project_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.manage"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, Any]:
    """Trigger contradiction assessment and auto-materialize newly detected conflicts."""
    engine = VerificationEngine(session)
    res = engine.assess_project(project_ctx.project.id)
    session.commit()
    conflict_service = ConflictService(session)
    metrics = conflict_service.get_dashboard_metrics(
        project_ctx.project.id,
        user_id=project_ctx.user_id,
        has_manage=project_ctx.has_permission("project.manage"),
    )
    return {
        "status": "success",
        "assessment": res,
        "metrics": metrics.model_dump(),
    }
