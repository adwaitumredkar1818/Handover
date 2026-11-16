"""FastAPI HTTP routes for Team Roster intelligence and Contribution Attribution."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_principal,
    get_db_session,
    require_project_permission,
    resolve_project_context,
)
from app.core.exceptions import NotFoundError
from app.core.security import utc_now
from app.models.project import ProjectMembership
from app.models.team_roster import ContributionAttribution, TeamRosterMember
from app.models.user import User
from app.schemas.team_roster import (
    ContributionAttributionResponse,
    ReconcileRosterMemberRequest,
    TeamRosterMemberResponse,
)
from app.services.rbac import AuthenticatedPrincipal, ProjectContext

router = APIRouter(tags=["Team Roster & Contributions"])


@router.get(
    "/projects/{project_id}/roster/members",
    response_model=list[TeamRosterMemberResponse],
    status_code=status.HTTP_200_OK,
    summary="List extracted roster members for a project workspace",
)
def list_roster_members(
    project_ctx: Annotated[ProjectContext, Depends(resolve_project_context)],
    session: Annotated[Session, Depends(get_db_session)],
    evidence_id: Annotated[uuid.UUID | None, Query()] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> list[TeamRosterMemberResponse]:
    stmt = (
        select(TeamRosterMember, ProjectMembership, User)
        .outerjoin(ProjectMembership, TeamRosterMember.matched_project_membership_id == ProjectMembership.id)
        .outerjoin(User, ProjectMembership.user_id == User.id)
        .where(TeamRosterMember.project_id == project_ctx.project.id)
    )
    if evidence_id:
        stmt = stmt.where(TeamRosterMember.evidence_item_id == evidence_id)
    if status_filter:
        stmt = stmt.where(TeamRosterMember.reconciliation_status == status_filter)

    stmt = stmt.order_by(TeamRosterMember.created_at.desc())
    results = session.execute(stmt).all()

    members: list[TeamRosterMemberResponse] = []
    for rm, pm, u in results:
        matched_name = u.full_name if u else None
        members.append(
            TeamRosterMemberResponse(
                id=rm.id,
                project_id=rm.project_id,
                evidence_item_id=rm.evidence_item_id,
                member_id_in_roster=rm.member_id_in_roster,
                full_name=rm.full_name,
                email=rm.email,
                role_name=rm.role_name,
                primary_responsibilities=list(rm.primary_responsibilities or []),
                component_ownership=list(rm.component_ownership or []),
                github_username=rm.github_username,
                git_commit_email=rm.git_commit_email,
                jira_account_id=rm.jira_account_id,
                slack_user_id=rm.slack_user_id,
                reconciliation_status=rm.reconciliation_status,
                matched_project_membership_id=rm.matched_project_membership_id,
                matched_member_name=matched_name,
                reconciliation_confidence=rm.reconciliation_confidence,
                reconciliation_notes=rm.reconciliation_notes,
                created_at=rm.created_at,
                updated_at=rm.updated_at,
            )
        )
    return members


@router.patch(
    "/projects/{project_id}/roster/members/{member_id}/reconcile",
    response_model=TeamRosterMemberResponse,
    status_code=status.HTTP_200_OK,
    summary="Update human reconciliation state for an extracted roster member",
)
def reconcile_roster_member(
    member_id: uuid.UUID,
    payload: ReconcileRosterMemberRequest,
    project_ctx: Annotated[
        ProjectContext,
        Depends(require_project_permission("project.manage")),
    ],
    session: Annotated[Session, Depends(get_db_session)],
) -> TeamRosterMemberResponse:
    member = session.get(TeamRosterMember, member_id)
    if member is None or member.project_id != project_ctx.project.id:
        raise NotFoundError("Roster member not found.", code="ROSTER_MEMBER_NOT_FOUND")

    member.reconciliation_status = payload.reconciliation_status
    if payload.matched_project_membership_id is not None:
        member.matched_project_membership_id = payload.matched_project_membership_id
    if payload.reconciliation_notes:
        member.reconciliation_notes = payload.reconciliation_notes
    member.updated_at = utc_now()

    session.commit()
    session.refresh(member)

    matched_name = None
    if member.matched_project_membership_id:
        pm = session.get(ProjectMembership, member.matched_project_membership_id)
        if pm:
            u = session.get(User, pm.user_id)
            if u:
                matched_name = u.full_name

    return TeamRosterMemberResponse(
        id=member.id,
        project_id=member.project_id,
        evidence_item_id=member.evidence_item_id,
        member_id_in_roster=member.member_id_in_roster,
        full_name=member.full_name,
        email=member.email,
        role_name=member.role_name,
        primary_responsibilities=list(member.primary_responsibilities or []),
        component_ownership=list(member.component_ownership or []),
        github_username=member.github_username,
        git_commit_email=member.git_commit_email,
        jira_account_id=member.jira_account_id,
        slack_user_id=member.slack_user_id,
        reconciliation_status=member.reconciliation_status,
        matched_project_membership_id=member.matched_project_membership_id,
        matched_member_name=matched_name,
        reconciliation_confidence=member.reconciliation_confidence,
        reconciliation_notes=member.reconciliation_notes,
        created_at=member.created_at,
        updated_at=member.updated_at,
    )


@router.get(
    "/projects/{project_id}/roster/attributions",
    response_model=list[ContributionAttributionResponse],
    status_code=status.HTTP_200_OK,
    summary="List contribution attributions and domain alignments for a project",
)
def list_contribution_attributions(
    project_ctx: Annotated[ProjectContext, Depends(resolve_project_context)],
    session: Annotated[Session, Depends(get_db_session)],
    evidence_id: Annotated[uuid.UUID | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
    alignment: Annotated[str | None, Query()] = None,
) -> list[ContributionAttributionResponse]:
    stmt = (
        select(ContributionAttribution, TeamRosterMember)
        .outerjoin(TeamRosterMember, ContributionAttribution.matched_roster_member_id == TeamRosterMember.id)
        .where(ContributionAttribution.project_id == project_ctx.project.id)
    )
    if evidence_id:
        stmt = stmt.where(ContributionAttribution.evidence_item_id == evidence_id)
    if category:
        stmt = stmt.where(ContributionAttribution.contribution_category == category)
    if alignment:
        stmt = stmt.where(ContributionAttribution.responsibility_alignment == alignment)

    stmt = stmt.order_by(ContributionAttribution.created_at.desc())
    results = session.execute(stmt).all()

    attributions: list[ContributionAttributionResponse] = []
    for ca, rm in results:
        attributions.append(
            ContributionAttributionResponse(
                id=ca.id,
                project_id=ca.project_id,
                evidence_item_id=ca.evidence_item_id,
                contributor_identifier=ca.contributor_identifier,
                identifier_type=ca.identifier_type,
                matched_roster_member_id=ca.matched_roster_member_id,
                matched_roster_name=rm.full_name if rm else None,
                matched_project_membership_id=ca.matched_project_membership_id,
                match_method=ca.match_method,
                match_confidence=ca.match_confidence,
                contribution_category=ca.contribution_category,
                responsibility_alignment=ca.responsibility_alignment,
                alignment_explanation=ca.alignment_explanation,
                created_at=ca.created_at,
                updated_at=ca.updated_at,
            )
        )
    return attributions
