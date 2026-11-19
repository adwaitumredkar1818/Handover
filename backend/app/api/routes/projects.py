"""Multi-tenant project workspace and project membership routes."""

from __future__ import annotations

import time
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    get_db_session,
    get_project_service,
    require_organisation_permission,
    require_project_permission,
    resolve_project_read_context,
)
from sqlalchemy.orm import Session
from app.services.pipeline_coordinator import (
    _STATUS_CACHE,
    _STATUS_CACHE_TTL_SECONDS,
    PipelineCoordinatorService,
    ProjectProcessingStatus,
    invalidate_project_status_cache,
)
from app.core.exceptions import NotFoundError
from app.models.enums import InvitationStatus, ProjectMembershipStatus, ProjectStatus
from app.schemas.organisation import (
    CreateInvitationResponse,
    InvitationListResponse,
    InvitationSummaryResponse,
    RemoveMembershipResponse,
)
from app.schemas.project import (
    AddProjectMemberRequest,
    CreateProjectInvitationRequest,
    CreateProjectRequest,
    ProjectActivityListResponse,
    ProjectListResponse,
    ProjectMemberListResponse,
    ProjectMemberResponse,
    ProjectOverviewResponse,
    ProjectResponse,
    ProjectTransitionResponse,
    UpdateMemberNameRequest,
    UpdateProjectMemberRoleRequest,
    UpdateProjectRequest,
    UpsertProjectTransitionRequest,
)
from app.services.project import ProjectService
from app.services.rbac import OrganisationContext, ProjectContext

router = APIRouter(tags=["projects"])


@router.post(
    "/organisations/{organisation_id}/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project workspace (requires organisation.projects.create)",
)
def create_project(
    payload: CreateProjectRequest,
    org_ctx: Annotated[
        OrganisationContext,
        Depends(require_organisation_permission("organisation.projects.create")),
    ],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectResponse:
    """Create a project workspace inside an active organisation and assign project managers."""
    return project_service.create_project(org_ctx=org_ctx, payload=payload)


@router.get(
    "/organisations/{organisation_id}/projects",
    response_model=ProjectListResponse,
    status_code=status.HTTP_200_OK,
    summary="List permitted projects in an organisation (requires organisation.read)",
)
def list_organisation_projects(
    org_ctx: Annotated[
        OrganisationContext,
        Depends(require_organisation_permission("organisation.read")),
    ],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
    project_status: Annotated[ProjectStatus | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProjectListResponse:
    """List projects visible to the caller within their verified organisation."""
    return project_service.list_projects_in_organisation(
        org_ctx=org_ctx,
        status=project_status.value if project_status is not None else None,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/projects/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Get project workspace details (honors private vs organisation visibility)",
)
def get_project_detail(
    project_ctx: Annotated[ProjectContext, Depends(resolve_project_read_context)],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectResponse:
    """Return project metadata and resolved effective permissions for the current user."""
    return project_service.get_project_detail(project_ctx)


@router.patch(
    "/projects/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Update project workspace metadata, status, or owner (requires project.manage)",
)
def update_project(
    payload: UpdateProjectRequest,
    project_ctx: Annotated[
        ProjectContext,
        Depends(require_project_permission("project.manage")),
    ],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectResponse:
    """Update a project's metadata, visibility, lifecycle status, or assigned owner."""
    return project_service.update_project(ctx=project_ctx, payload=payload)


@router.post(
    "/projects/{project_id}/archive",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Archive a project workspace (requires project.manage)",
)
def archive_project(
    project_ctx: Annotated[
        ProjectContext,
        Depends(require_project_permission("project.manage")),
    ],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectResponse:
    """Archive a non-archived project cleanly and record an audit trail entry."""
    return project_service.archive_project(ctx=project_ctx)


@router.get(
    "/projects/{project_id}/members",
    response_model=ProjectMemberListResponse,
    status_code=status.HTTP_200_OK,
    summary="List project members (requires project.members.read)",
)
def list_project_members(
    project_ctx: Annotated[
        ProjectContext,
        Depends(require_project_permission("project.members.read")),
    ],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
    member_status: Annotated[
        ProjectMembershipStatus | None,
        Query(alias="status"),
    ] = ProjectMembershipStatus.ACTIVE,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProjectMemberListResponse:
    """List member assignments and project roles for this project workspace."""
    return project_service.list_project_members(
        ctx=project_ctx,
        status=member_status.value if member_status is not None else None,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/projects/{project_id}/members",
    response_model=ProjectMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Assign an organisation member to a project (requires project.members.manage)",
)
def add_project_member(
    payload: AddProjectMemberRequest,
    project_ctx: Annotated[
        ProjectContext,
        Depends(require_project_permission("project.members.manage")),
    ],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectMemberResponse:
    """Assign an active parent-organisation member into this project with a project role."""
    return project_service.add_project_member(ctx=project_ctx, payload=payload)


@router.patch(
    "/projects/{project_id}/members/{user_id}/role",
    response_model=ProjectMemberResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a project member's role (requires project.members.manage)",
)
def update_project_member_role(
    user_id: uuid.UUID,
    payload: UpdateProjectMemberRoleRequest,
    project_ctx: Annotated[
        ProjectContext,
        Depends(require_project_permission("project.members.manage")),
    ],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectMemberResponse:
    """Update a project member's project-scoped role with owner continuity guards."""
    return project_service.update_project_member_role(
        ctx=project_ctx,
        target_user_id=user_id,
        payload=payload,
    )


@router.patch(
    "/projects/{project_id}/members/{user_id}/name",
    response_model=ProjectMemberResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a project member's display name (manager or self)",
)
def update_project_member_name(
    user_id: uuid.UUID,
    payload: UpdateMemberNameRequest,
    project_ctx: Annotated[ProjectContext, Depends(resolve_project_read_context)],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectMemberResponse:
    """Update an active project member's display name (User.full_name)."""
    return project_service.update_project_member_name(
        ctx=project_ctx,
        target_user_id=user_id,
        payload=payload,
    )


@router.delete(
    "/projects/{project_id}/members/{user_id}",
    response_model=RemoveMembershipResponse,
    status_code=status.HTTP_200_OK,
    summary="Remove a project member (requires project.members.manage)",
)
def remove_project_member(
    user_id: uuid.UUID,
    project_ctx: Annotated[
        ProjectContext,
        Depends(require_project_permission("project.members.manage")),
    ],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
) -> RemoveMembershipResponse:
    """Revoke a user's active membership in the project workspace."""
    return project_service.remove_project_member(ctx=project_ctx, target_user_id=user_id)


@router.get(
    "/projects/{project_id}/overview",
    response_model=ProjectOverviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Get aggregated dashboard overview for the project (requires project.read)",
)
def get_project_overview(
    project_ctx: Annotated[ProjectContext, Depends(resolve_project_read_context)],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectOverviewResponse:
    """Compile aggregated project metrics, sources, evidence, and recent activity."""
    return project_service.get_project_overview(project_ctx)


@router.get(
    "/projects/{project_id}/activity",
    response_model=ProjectActivityListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get recent audit and activity stream for the project (requires project.read)",
)
def get_project_activity(
    project_ctx: Annotated[ProjectContext, Depends(resolve_project_read_context)],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProjectActivityListResponse:
    """Retrieve chronological event feed of actions inside this project workspace."""
    return project_service.get_project_activity(ctx=project_ctx, limit=limit, offset=offset)


@router.get(
    "/projects/{project_id}/transition",
    response_model=ProjectTransitionResponse | None,
    status_code=status.HTTP_200_OK,
    summary="Get transition configuration for the project (requires project.read)",
)
def get_project_transition(
    project_ctx: Annotated[ProjectContext, Depends(resolve_project_read_context)],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectTransitionResponse | None:
    """Retrieve configured departing member, successor, and capture scope."""
    return project_service.get_project_transition(project_ctx)


@router.put(
    "/projects/{project_id}/transition",
    response_model=ProjectTransitionResponse,
    status_code=status.HTTP_200_OK,
    summary="Configure transition participants and parameters (requires project.transition.manage)",
)
def upsert_project_transition(
    payload: UpsertProjectTransitionRequest,
    project_ctx: Annotated[
        ProjectContext,
        Depends(require_project_permission("project.transition.manage")),
    ],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectTransitionResponse:
    """Upsert departing member, incoming successor, and knowledge capture scope."""
    return project_service.upsert_project_transition(ctx=project_ctx, payload=payload)


@router.post(
    "/organisations/{organisation_id}/projects/{project_id}/invitations",
    response_model=CreateInvitationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project invitation (requires project.invitations.manage)",
)
def create_project_invitation(
    organisation_id: uuid.UUID,
    project_id: uuid.UUID,
    payload: CreateProjectInvitationRequest,
    project_ctx: Annotated[
        ProjectContext,
        Depends(require_project_permission("project.invitations.manage")),
    ],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
) -> CreateInvitationResponse:
    """Issue a SHA-256 hashed single-use project invitation."""
    if project_ctx.project.organisation_id != organisation_id:
        raise NotFoundError("Project was not found in this organisation.", code="PROJECT_NOT_FOUND")
    return project_service.create_project_invitation(ctx=project_ctx, payload=payload)


@router.get(
    "/organisations/{organisation_id}/projects/{project_id}/invitations",
    response_model=InvitationListResponse,
    status_code=status.HTTP_200_OK,
    summary="List project invitations (requires project.invitations.read)",
)
def list_project_invitations(
    organisation_id: uuid.UUID,
    project_id: uuid.UUID,
    project_ctx: Annotated[
        ProjectContext,
        Depends(require_project_permission("project.invitations.read")),
    ],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
    invitation_status: Annotated[InvitationStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> InvitationListResponse:
    """List hashed invitation metadata scoped to this project workspace."""
    if project_ctx.project.organisation_id != organisation_id:
        raise NotFoundError("Project was not found in this organisation.", code="PROJECT_NOT_FOUND")
    return project_service.list_project_invitations(
        ctx=project_ctx,
        status=invitation_status.value if invitation_status is not None else None,
        limit=limit,
        offset=offset,
    )


@router.delete(
    "/organisations/{organisation_id}/projects/{project_id}/invitations/{invitation_id}",
    response_model=InvitationSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke a pending project invitation (requires project.invitations.manage)",
)
def revoke_project_invitation(
    organisation_id: uuid.UUID,
    project_id: uuid.UUID,
    invitation_id: uuid.UUID,
    project_ctx: Annotated[
        ProjectContext,
        Depends(require_project_permission("project.invitations.manage")),
    ],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
) -> InvitationSummaryResponse:
    """Revoke a pending project invitation so its token can no longer be accepted."""
    if project_ctx.project.organisation_id != organisation_id:
        raise NotFoundError("Project was not found in this organisation.", code="PROJECT_NOT_FOUND")
    return project_service.revoke_project_invitation(ctx=project_ctx, invitation_id=invitation_id)


@router.get(
    "/projects/{project_id}/processing-status",
    response_model=ProjectProcessingStatus,
    status_code=status.HTTP_200_OK,
    summary="Get real-time pipeline processing and reconstruction status for a project",
)
def get_project_processing_status(
    project_ctx: Annotated[ProjectContext, Depends(resolve_project_read_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> ProjectProcessingStatus:
    """Fast indexed lookup of background jobs, evidence states, and reconstruction progress."""
    now_m = time.monotonic()
    cached = _STATUS_CACHE.get(project_ctx.project.id)
    if cached is not None and (now_m - cached[0]) < _STATUS_CACHE_TTL_SECONDS:
        return cached[1]

    coordinator = PipelineCoordinatorService(session)
    st = coordinator.get_status(project_ctx.project.id)
    _STATUS_CACHE[project_ctx.project.id] = (now_m, st)
    return st


@router.post(
    "/projects/{project_id}/processing-status/retry",
    response_model=ProjectProcessingStatus,
    status_code=status.HTTP_200_OK,
    summary="Retry or trigger automatic evidence-to-knowledge pipeline for a project",
)
def retry_project_processing_pipeline(
    project_ctx: Annotated[ProjectContext, Depends(resolve_project_read_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> ProjectProcessingStatus:
    """Enqueue missing or failed indexing and knowledge reconstruction jobs."""
    invalidate_project_status_cache(project_ctx.project.id)
    coordinator = PipelineCoordinatorService(session)
    coordinator.trigger_auto_pipeline(
        project_id=project_ctx.project.id,
        triggered_by_user_id=project_ctx.principal.user_id,
        force_reextract=False,
    )
    st = coordinator.get_status(project_ctx.project.id)
    _STATUS_CACHE[project_ctx.project.id] = (time.monotonic(), st)
    return st
