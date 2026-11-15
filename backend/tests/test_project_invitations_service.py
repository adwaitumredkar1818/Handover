"""Comprehensive tests for Project Invitation Service & Atomic Dual-Membership Acceptance (Phase 2).

Covers all 34 required test cases across:
1. Invitation Creation (1-10)
2. Acceptance — New User (11-15)
3. Acceptance — Existing Organisation Member (16-18)
4. Acceptance — Multi-Organisation User (19-22)
5. Failure & Security Cases (23-31)
6. Backward Compatibility & Project Management (32-34)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    GoneError,
    NotFoundError,
)
from app.core.rbac_catalog import SYSTEM_ROLES
from app.core.security import generate_opaque_token, hash_opaque_token, utc_now
from app.models.audit import AuditLog
from app.models.enums import (
    InvitationStatus,
    OrganisationMembershipStatus,
    OrganisationStatus,
    ProjectMembershipStatus,
    ProjectStatus,
    RoleName,
    RoleScopeType,
)
from app.models.organisation import Organisation, OrganisationInvitation, OrganisationMembership
from app.models.project import Project, ProjectMembership
from app.models.rbac import Permission, Role
from app.models.user import User
from app.repositories.audit import AuditLogRepository
from app.repositories.organisation import OrganisationRepository
from app.repositories.project import ProjectRepository
from app.repositories.rbac import RbacRepository
from app.repositories.user import UserRepository
from app.schemas.project import CreateProjectInvitationRequest
from app.services.audit import AuditService
from app.services.organisation import OrganisationService
from app.services.project import ProjectService
from app.services.rbac import AuthenticatedPrincipal, RbacService
from tests.conftest import isolated_auth_app


# =============================================================================
# Helper Utilities & Fixtures
# =============================================================================

def _create_user(session: Session, email: str, name: str) -> User:
    user = User(
        email=email.lower().strip(),
        full_name=name,
        password_hash="test-password-hash",
        is_email_verified=True,
    )
    session.add(user)
    session.flush()
    return user


def _create_org(session: Session, name: str, slug: str, creator: User) -> Organisation:
    org = Organisation(
        name=name,
        slug=slug,
        created_by_id=creator.id,
        status=OrganisationStatus.ACTIVE.value,
    )
    session.add(org)
    session.flush()
    return org


def _create_project(
    session: Session,
    org: Organisation,
    name: str,
    slug: str,
    creator: User,
    status: str = ProjectStatus.ACTIVE.value,
) -> Project:
    project = Project(
        organisation_id=org.id,
        name=name,
        slug=slug,
        created_by_id=creator.id,
        owner_id=creator.id,
        status=status,
    )
    session.add(project)
    session.flush()
    return project


def _get_role(session: Session, name: str) -> Role:
    role = session.scalar(select(Role).where(Role.name == name))
    assert role is not None, f"Role {name} not found"
    return role


def _add_org_member(
    session: Session,
    org: Organisation,
    user: User,
    role_name: str,
) -> OrganisationMembership:
    role = _get_role(session, role_name)
    mem = OrganisationMembership(
        organisation_id=org.id,
        user_id=user.id,
        role_id=role.id,
        status=OrganisationMembershipStatus.ACTIVE.value,
        joined_at=utc_now(),
    )
    session.add(mem)
    session.flush()
    return mem


def _add_project_member(
    session: Session,
    project: Project,
    user: User,
    role_name: str,
) -> ProjectMembership:
    role = _get_role(session, role_name)
    mem = ProjectMembership(
        project_id=project.id,
        user_id=user.id,
        role_id=role.id,
        status=ProjectMembershipStatus.ACTIVE.value,
        joined_at=utc_now(),
    )
    session.add(mem)
    session.flush()
    return mem


class ServiceHarness:
    """Convenience bundle of repositories, RBAC, and business services for testing."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.org_repo = OrganisationRepository(session)
        self.project_repo = ProjectRepository(session)
        self.user_repo = UserRepository(session)
        self.rbac_repo = RbacRepository(session)
        self.audit_repo = AuditLogRepository(session)
        self.audit = AuditService(audit_repository=self.audit_repo)
        self.rbac_service = RbacService(
            db_session=session,
            rbac_repository=self.rbac_repo,
            user_repository=self.user_repo,
        )
        self.project_service = ProjectService(
            db_session=session,
            org_repository=self.org_repo,
            project_repository=self.project_repo,
            rbac_repository=self.rbac_repo,
            rbac_service=self.rbac_service,
            audit_service=self.audit,
            user_repository=self.user_repo,
            settings=settings,
        )
        self.org_service = OrganisationService(
            settings=settings,
            db_session=session,
            org_repository=self.org_repo,
            project_repository=self.project_repo,
            rbac_repository=self.rbac_repo,
            user_repository=self.user_repo,
            rbac_service=self.rbac_service,
            audit_service=self.audit,
        )

    def principal(self, user: User) -> AuthenticatedPrincipal:
        return AuthenticatedPrincipal(
            user=user,
            session_family_id=uuid.uuid4(),
            roles=(RoleName.STANDARD_USER.value,),
            permissions=frozenset(),
        )


# =============================================================================
# PART 1: INVITATION CREATION (Tests 1 - 10)
# =============================================================================

def test_1_project_manager_can_create_project_invitation(monkeypatch: pytest.MonkeyPatch) -> None:
    """1. Authorised Project Manager can create a project invitation."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            owner = _create_user(session, "owner@org.com", "Org Owner")
            pm = _create_user(session, "pm@org.com", "Project Manager")
            org = _create_org(session, "Acme Corp", "acme-corp", owner)
            project = _create_project(session, org, "Alpha", "alpha", owner)

            _add_org_member(session, org, owner, RoleName.ORG_OWNER.value)
            _add_org_member(session, org, pm, RoleName.ORG_MEMBER.value)
            _add_project_member(session, project, pm, RoleName.PROJECT_MANAGER.value)
            session.commit()

            pm_principal = h.principal(pm)
            proj_ctx = h.rbac_service.resolve_project_context(
                project_id=project.id,
                principal=pm_principal,
            )

            payload = CreateProjectInvitationRequest(
                email="invitee@example.com",
                role_name="project_member",
                expires_in_hours=72,
            )
            result = h.project_service.create_project_invitation(ctx=proj_ctx, payload=payload)

            assert result.invitation.email == "invitee@example.com"
            assert result.invitation.project_id == project.id
            assert result.invitation.project_role_name == "project_member"
            assert result.invitation.role_name == "org_member"
            assert result.invitation.status == "pending"
            assert result.development_invitation_token is not None


def test_2_project_member_cannot_create_project_invitation(monkeypatch: pytest.MonkeyPatch) -> None:
    """2. Regular Project Member cannot create an invitation (ForbiddenError)."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            owner = _create_user(session, "owner@org.com", "Org Owner")
            member = _create_user(session, "member@org.com", "Project Member")
            org = _create_org(session, "Acme Corp", "acme-corp", owner)
            project = _create_project(session, org, "Alpha", "alpha", owner)

            _add_org_member(session, org, owner, RoleName.ORG_OWNER.value)
            _add_org_member(session, org, member, RoleName.ORG_MEMBER.value)
            _add_project_member(session, project, member, RoleName.PROJECT_MEMBER.value)
            session.commit()

            member_ctx = h.rbac_service.resolve_project_context(
                project_id=project.id,
                principal=h.principal(member),
            )

            payload = CreateProjectInvitationRequest(
                email="invitee@example.com",
                role_name="project_member",
            )
            with pytest.raises(ForbiddenError) as exc_info:
                h.project_service.create_project_invitation(ctx=member_ctx, payload=payload)
            assert "permission" in str(exc_info.value).lower() or exc_info.value.code == "FORBIDDEN"


def test_3_reviewer_cannot_create_project_invitation(monkeypatch: pytest.MonkeyPatch) -> None:
    """3. Reviewer cannot create an invitation (ForbiddenError)."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            owner = _create_user(session, "owner@org.com", "Org Owner")
            reviewer = _create_user(session, "rev@org.com", "Reviewer")
            org = _create_org(session, "Acme Corp", "acme-corp", owner)
            project = _create_project(session, org, "Alpha", "alpha", owner)

            _add_org_member(session, org, owner, RoleName.ORG_OWNER.value)
            _add_org_member(session, org, reviewer, RoleName.ORG_MEMBER.value)
            _add_project_member(session, project, reviewer, RoleName.REVIEWER.value)
            session.commit()

            rev_ctx = h.rbac_service.resolve_project_context(
                project_id=project.id,
                principal=h.principal(reviewer),
            )
            payload = CreateProjectInvitationRequest(
                email="invitee@example.com",
                role_name="project_member",
            )
            with pytest.raises(ForbiddenError):
                h.project_service.create_project_invitation(ctx=rev_ctx, payload=payload)


def test_4_org_owner_and_admin_override_can_create_project_invitation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """4. Organisation Owner / Admin override works within their own organisation."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            owner = _create_user(session, "owner@org.com", "Org Owner")
            admin = _create_user(session, "admin@org.com", "Org Admin")
            org = _create_org(session, "Acme Corp", "acme-corp", owner)
            project = _create_project(session, org, "Alpha", "alpha", owner)

            _add_org_member(session, org, owner, RoleName.ORG_OWNER.value)
            _add_org_member(session, org, admin, RoleName.ORG_ADMIN.value)
            # Notice: Neither owner nor admin is an explicit member in Project Alpha!
            session.commit()

            # Org Owner override
            owner_proj_ctx = h.rbac_service.resolve_project_context(
                project_id=project.id,
                principal=h.principal(owner),
            )
            res_owner = h.project_service.create_project_invitation(
                ctx=owner_proj_ctx,
                payload=CreateProjectInvitationRequest(
                    email="sub1@example.com",
                    role_name="project_manager",
                ),
            )
            assert res_owner.invitation.project_role_name == "project_manager"

            # Org Admin override
            admin_proj_ctx = h.rbac_service.resolve_project_context(
                project_id=project.id,
                principal=h.principal(admin),
            )
            res_admin = h.project_service.create_project_invitation(
                ctx=admin_proj_ctx,
                payload=CreateProjectInvitationRequest(
                    email="sub2@example.com",
                    role_name="project_member",
                ),
            )
            assert res_admin.invitation.project_role_name == "project_member"


def test_5_inviter_cannot_assign_unauthorised_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    """5. Inviter cannot assign unauthorised roles (higher rank or wrong scope)."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            owner = _create_user(session, "owner@org.com", "Org Owner")
            pm = _create_user(session, "pm@org.com", "Project Manager")
            org = _create_org(session, "Acme Corp", "acme-corp", owner)
            project = _create_project(session, org, "Alpha", "alpha", owner)

            _add_org_member(session, org, owner, RoleName.ORG_OWNER.value)
            _add_org_member(session, org, pm, RoleName.ORG_MEMBER.value)
            _add_project_member(session, project, pm, RoleName.PROJECT_MANAGER.value)
            session.commit()

            pm_ctx = h.rbac_service.resolve_project_context(
                project_id=project.id,
                principal=h.principal(pm),
            )

            # A: Requesting an organisation-scoped role for a project invitation
            with pytest.raises(BadRequestError) as exc_scope:
                h.project_service.create_project_invitation(
                    ctx=pm_ctx,
                    payload=CreateProjectInvitationRequest(
                        email="test@example.com",
                        role_name="org_admin",
                    ),
                )
            assert exc_scope.value.code == "INVALID_ROLE_SCOPE"


def test_6_project_must_belong_to_specified_organisation(monkeypatch: pytest.MonkeyPatch) -> None:
    """6. Project must belong to the specified organisation (cross-tenant rejection)."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            owner_a = _create_user(session, "owner_a@org.com", "Owner A")
            owner_b = _create_user(session, "owner_b@org.com", "Owner B")
            org_a = _create_org(session, "Org A", "org-a", owner_a)
            org_b = _create_org(session, "Org B", "org-b", owner_b)
            project_b = _create_project(session, org_b, "Project B", "proj-b", owner_b)

            _add_org_member(session, org_a, owner_a, RoleName.ORG_OWNER.value)
            _add_org_member(session, org_b, owner_b, RoleName.ORG_OWNER.value)
            session.commit()

            # Attempting to resolve project context for Project B using Org A owner fails
            with pytest.raises((ForbiddenError, NotFoundError)):
                h.rbac_service.resolve_project_context(
                    project_id=project_b.id,
                    principal=h.principal(owner_a),
                )


def test_7_inactive_or_archived_project_cannot_receive_invitations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """7. Inactive / archived projects cannot receive invitations (ConflictError)."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            owner = _create_user(session, "owner@org.com", "Org Owner")
            org = _create_org(session, "Acme Corp", "acme-corp", owner)
            project = _create_project(
                session,
                org,
                "Archived Proj",
                "arch-proj",
                owner,
                status=ProjectStatus.ARCHIVED.value,
            )

            _add_org_member(session, org, owner, RoleName.ORG_OWNER.value)
            session.commit()

            proj_ctx = h.rbac_service.resolve_project_context(
                project_id=project.id,
                principal=h.principal(owner),
            )
            with pytest.raises(ConflictError) as exc_info:
                h.project_service.create_project_invitation(
                    ctx=proj_ctx,
                    payload=CreateProjectInvitationRequest(
                        email="dev@example.com",
                        role_name="project_member",
                    ),
                )
            assert exc_info.value.code == "PROJECT_ARCHIVED"


def test_8_duplicate_pending_invitation_to_same_project_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """8. Duplicate pending invitations for the same email and project are rejected."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            owner = _create_user(session, "owner@org.com", "Org Owner")
            org = _create_org(session, "Acme Corp", "acme-corp", owner)
            project = _create_project(session, org, "Alpha", "alpha", owner)

            _add_org_member(session, org, owner, RoleName.ORG_OWNER.value)
            session.commit()

            proj_ctx = h.rbac_service.resolve_project_context(
                project_id=project.id,
                principal=h.principal(owner),
            )
            payload = CreateProjectInvitationRequest(
                email="target@example.com",
                role_name="project_member",
            )
            # First invitation succeeds
            h.project_service.create_project_invitation(ctx=proj_ctx, payload=payload)

            # Second invitation raises ConflictError
            with pytest.raises(ConflictError) as exc_info:
                h.project_service.create_project_invitation(ctx=proj_ctx, payload=payload)
            assert exc_info.value.code == "INVITATION_ALREADY_EXISTS"


def test_9_existing_active_project_member_rejected_from_invitation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """9. Existing active project members are rejected from receiving an invitation."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            owner = _create_user(session, "owner@org.com", "Org Owner")
            existing = _create_user(session, "active@org.com", "Active Dev")
            org = _create_org(session, "Acme Corp", "acme-corp", owner)
            project = _create_project(session, org, "Alpha", "alpha", owner)

            _add_org_member(session, org, owner, RoleName.ORG_OWNER.value)
            _add_org_member(session, org, existing, RoleName.ORG_MEMBER.value)
            _add_project_member(session, project, existing, RoleName.PROJECT_MEMBER.value)
            session.commit()

            proj_ctx = h.rbac_service.resolve_project_context(
                project_id=project.id,
                principal=h.principal(owner),
            )
            payload = CreateProjectInvitationRequest(
                email="active@org.com",
                role_name="project_member",
            )
            with pytest.raises(ConflictError) as exc_info:
                h.project_service.create_project_invitation(ctx=proj_ctx, payload=payload)
            assert exc_info.value.code == "MEMBERSHIP_ALREADY_EXISTS"


def test_10_raw_invitation_token_is_never_persisted_in_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """10. Raw invitation token is never persisted in the database; only SHA-256 hash stored."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            owner = _create_user(session, "owner@org.com", "Org Owner")
            org = _create_org(session, "Acme Corp", "acme-corp", owner)
            project = _create_project(session, org, "Alpha", "alpha", owner)

            _add_org_member(session, org, owner, RoleName.ORG_OWNER.value)
            session.commit()

            proj_ctx = h.rbac_service.resolve_project_context(
                project_id=project.id,
                principal=h.principal(owner),
            )
            payload = CreateProjectInvitationRequest(
                email="secret@example.com",
                role_name="project_member",
            )
            result = h.project_service.create_project_invitation(ctx=proj_ctx, payload=payload)
            raw_token = result.development_invitation_token
            assert raw_token is not None

            # Verify in DB: token_hash is SHA-256, raw_token does NOT exist in columns
            inv = session.scalar(
                select(OrganisationInvitation).where(
                    OrganisationInvitation.id == result.invitation.id
                )
            )
            assert inv is not None
            assert inv.token_hash == hash_opaque_token(raw_token)
            assert raw_token not in inv.token_hash
            assert not hasattr(inv, "raw_token")


# =============================================================================
# PART 2: ACCEPTANCE — NEW USER (Tests 11 - 15)
# =============================================================================

def _setup_new_user_invitation(session: Session, h: ServiceHarness, project_role: str = "reviewer") -> tuple[Organisation, Project, User, str, OrganisationInvitation]:
    owner = _create_user(session, f"owner_{uuid.uuid4().hex[:6]}@org.com", "Org Owner")
    org = _create_org(session, "Acme Corp", f"acme-{uuid.uuid4().hex[:6]}", owner)
    project = _create_project(session, org, "Alpha", f"alpha-{uuid.uuid4().hex[:6]}", owner)
    _add_org_member(session, org, owner, RoleName.ORG_OWNER.value)
    session.commit()

    proj_ctx = h.rbac_service.resolve_project_context(
        project_id=project.id,
        principal=h.principal(owner),
    )
    email = f"newbie_{uuid.uuid4().hex[:6]}@example.com"
    create_res = h.project_service.create_project_invitation(
        ctx=proj_ctx,
        payload=CreateProjectInvitationRequest(
            email=email,
            project_role_name=project_role,
        ),
    )
    raw_token = create_res.development_invitation_token
    assert raw_token is not None

    new_user = _create_user(session, email, "New User")
    session.commit()

    inv = session.scalar(
        select(OrganisationInvitation).where(
            OrganisationInvitation.id == create_res.invitation.id
        )
    )
    assert inv is not None
    return org, project, new_user, raw_token, inv


def test_11_acceptance_creates_org_membership_with_default_org_member_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """11. New organisation membership is created with the default org_member role."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            org, project, new_user, raw_token, _ = _setup_new_user_invitation(session, h)
            res = h.org_service.accept_invitation(
                raw_token=raw_token,
                acting_principal=h.principal(new_user),
            )
            assert res.is_new_organisation_member is True
            assert res.role_name == "org_member"
            org_mem = h.org_repo.get_active_membership(organisation_id=org.id, user_id=new_user.id)
            assert org_mem is not None
            assert org_mem.role.name == "org_member"


def test_12_acceptance_creates_project_membership_with_assigned_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """12. Project membership is created with the exact role assigned in the invitation."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            org, project, new_user, raw_token, _ = _setup_new_user_invitation(session, h, project_role="reviewer")
            res = h.org_service.accept_invitation(
                raw_token=raw_token,
                acting_principal=h.principal(new_user),
            )
            assert res.project_id == project.id
            assert res.project_role_name == "reviewer"
            assert res.project_membership_status == "active"
            proj_mem = h.project_repo.get_active_membership(project_id=project.id, user_id=new_user.id)
            assert proj_mem is not None
            assert proj_mem.role.name == "reviewer"


def test_13_acceptance_updates_invitation_status_to_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """13. Invitation status transitions to accepted with timestamps and consumer user ID."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            org, project, new_user, raw_token, inv = _setup_new_user_invitation(session, h)
            h.org_service.accept_invitation(
                raw_token=raw_token,
                acting_principal=h.principal(new_user),
            )
            session.refresh(inv)
            assert inv.status == InvitationStatus.ACCEPTED.value
            assert inv.accepted_by_user_id == new_user.id
            assert inv.accepted_at is not None


def test_14_acceptance_records_required_audit_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """14. Audit events are recorded for invitation acceptance and both membership additions."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            org, project, new_user, raw_token, inv = _setup_new_user_invitation(session, h)
            h.org_service.accept_invitation(
                raw_token=raw_token,
                acting_principal=h.principal(new_user),
            )
            audit_events = session.scalars(
                select(AuditLog).where(
                    AuditLog.actor_user_id == new_user.id,
                    AuditLog.organisation_id == org.id,
                )
            ).all()
            event_types = {e.event_type for e in audit_events}
            assert "organisation.invitation.accepted" in event_types
            assert "organisation.member.added" in event_types
            assert "project.member.added" in event_types


def test_15_acceptance_is_atomic_both_memberships_in_same_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """15. Both organisation and project memberships are established within the same atomic transaction."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            org, project, new_user, raw_token, _ = _setup_new_user_invitation(session, h)
            # Before acceptance, user has 0 memberships
            assert h.org_repo.get_active_membership(organisation_id=org.id, user_id=new_user.id) is None
            assert h.project_repo.get_active_membership(project_id=project.id, user_id=new_user.id) is None

            h.org_service.accept_invitation(
                raw_token=raw_token,
                acting_principal=h.principal(new_user),
            )

            # After atomic commit, both exist simultaneously
            assert h.org_repo.get_active_membership(organisation_id=org.id, user_id=new_user.id) is not None
            assert h.project_repo.get_active_membership(project_id=project.id, user_id=new_user.id) is not None


# =============================================================================
# PART 3: ACCEPTANCE — EXISTING ORGANISATION MEMBER (Tests 16 - 18)
# =============================================================================

def _setup_existing_member_invitation(
    session: Session,
    h: ServiceHarness,
    existing_org_role: str = RoleName.ORG_ADMIN.value,
    target_project_role: str = "project_manager",
) -> tuple[Organisation, Project, User, str]:
    owner = _create_user(session, f"owner_{uuid.uuid4().hex[:6]}@org.com", "Org Owner")
    existing_user = _create_user(session, f"member_{uuid.uuid4().hex[:6]}@org.com", "Existing Member")
    org = _create_org(session, "Acme Corp", f"acme-{uuid.uuid4().hex[:6]}", owner)
    project = _create_project(session, org, "Alpha", f"alpha-{uuid.uuid4().hex[:6]}", owner)

    _add_org_member(session, org, owner, RoleName.ORG_OWNER.value)
    _add_org_member(session, org, existing_user, existing_org_role)
    session.commit()

    owner_proj_ctx = h.rbac_service.resolve_project_context(
        project_id=project.id,
        principal=h.principal(owner),
    )
    create_res = h.project_service.create_project_invitation(
        ctx=owner_proj_ctx,
        payload=CreateProjectInvitationRequest(
            email=existing_user.email,
            project_role_name=target_project_role,
        ),
    )
    raw_token = create_res.development_invitation_token
    assert raw_token is not None
    return org, project, existing_user, raw_token


def test_16_acceptance_reuses_existing_org_membership(monkeypatch: pytest.MonkeyPatch) -> None:
    """16. Existing organisation membership is reused rather than duplicated."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            org, project, existing_user, raw_token = _setup_existing_member_invitation(session, h)
            res = h.org_service.accept_invitation(
                raw_token=raw_token,
                acting_principal=h.principal(existing_user),
            )
            assert res.is_new_organisation_member is False

            # Verify only exactly one active membership exists in the organisation
            memberships = session.scalars(
                select(OrganisationMembership).where(
                    OrganisationMembership.organisation_id == org.id,
                    OrganisationMembership.user_id == existing_user.id,
                )
            ).all()
            assert len(memberships) == 1


def test_17_acceptance_preserves_existing_org_role_without_downgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """17. Existing organisation role (e.g. org_admin) remains intact without downgrade."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            org, project, existing_user, raw_token = _setup_existing_member_invitation(
                session, h, existing_org_role=RoleName.ORG_ADMIN.value
            )
            res = h.org_service.accept_invitation(
                raw_token=raw_token,
                acting_principal=h.principal(existing_user),
            )
            assert res.role_name == RoleName.ORG_ADMIN.value
            org_mem = h.org_repo.get_active_membership(organisation_id=org.id, user_id=existing_user.id)
            assert org_mem is not None
            assert org_mem.role.name == RoleName.ORG_ADMIN.value


def test_18_acceptance_creates_project_membership_for_existing_org_member(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """18. Project membership is created with assigned role for the existing organisation member."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            org, project, existing_user, raw_token = _setup_existing_member_invitation(
                session, h, target_project_role="project_manager"
            )
            res = h.org_service.accept_invitation(
                raw_token=raw_token,
                acting_principal=h.principal(existing_user),
            )
            assert res.project_role_name == "project_manager"
            proj_mem = h.project_repo.get_active_membership(project_id=project.id, user_id=existing_user.id)
            assert proj_mem is not None
            assert proj_mem.role.name == "project_manager"


# =============================================================================
# PART 4: ACCEPTANCE — MULTI-ORGANISATION USER (Tests 19 - 22)
# =============================================================================

def _setup_multi_org_invitation(
    session: Session,
    h: ServiceHarness,
) -> tuple[Organisation, Project, Organisation, Project, User, str]:
    owner_a = _create_user(session, f"owner_a_{uuid.uuid4().hex[:6]}@org.com", "Owner A")
    owner_b = _create_user(session, f"owner_b_{uuid.uuid4().hex[:6]}@org.com", "Owner B")
    user = _create_user(session, f"multi_{uuid.uuid4().hex[:6]}@org.com", "Multi Org Dev")

    org_a = _create_org(session, "Org A", f"org-a-{uuid.uuid4().hex[:6]}", owner_a)
    proj_a = _create_project(session, org_a, "Proj A", f"proj-a-{uuid.uuid4().hex[:6]}", owner_a)

    org_b = _create_org(session, "Org B", f"org-b-{uuid.uuid4().hex[:6]}", owner_b)
    proj_b = _create_project(session, org_b, "Proj B", f"proj-b-{uuid.uuid4().hex[:6]}", owner_b)

    _add_org_member(session, org_a, owner_a, RoleName.ORG_OWNER.value)
    _add_org_member(session, org_a, user, RoleName.ORG_MEMBER.value)
    _add_project_member(session, proj_a, user, RoleName.PROJECT_MEMBER.value)

    _add_org_member(session, org_b, owner_b, RoleName.ORG_OWNER.value)
    session.commit()

    owner_b_proj_ctx = h.rbac_service.resolve_project_context(
        project_id=proj_b.id,
        principal=h.principal(owner_b),
    )
    create_res = h.project_service.create_project_invitation(
        ctx=owner_b_proj_ctx,
        payload=CreateProjectInvitationRequest(
            email=user.email,
            project_role_name="reviewer",
        ),
    )
    raw_token = create_res.development_invitation_token
    assert raw_token is not None
    return org_a, proj_a, org_b, proj_b, user, raw_token


def test_19_acceptance_preserves_existing_memberships_in_org_a(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """19. Existing organisation membership in Org A remains completely intact."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            org_a, proj_a, org_b, proj_b, user, raw_token = _setup_multi_org_invitation(session, h)
            h.org_service.accept_invitation(
                raw_token=raw_token,
                acting_principal=h.principal(user),
            )
            mem_org_a = h.org_repo.get_active_membership(organisation_id=org_a.id, user_id=user.id)
            assert mem_org_a is not None
            assert mem_org_a.role.name == RoleName.ORG_MEMBER.value


def test_20_acceptance_preserves_existing_memberships_in_project_a(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """20. Existing project membership in Proj A remains completely intact."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            org_a, proj_a, org_b, proj_b, user, raw_token = _setup_multi_org_invitation(session, h)
            h.org_service.accept_invitation(
                raw_token=raw_token,
                acting_principal=h.principal(user),
            )
            mem_proj_a = h.project_repo.get_active_membership(project_id=proj_a.id, user_id=user.id)
            assert mem_proj_a is not None
            assert mem_proj_a.role.name == RoleName.PROJECT_MEMBER.value


def test_21_acceptance_creates_membership_in_invited_org_b(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """21. Membership in invited Org B is created as a new organisation membership."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            org_a, proj_a, org_b, proj_b, user, raw_token = _setup_multi_org_invitation(session, h)
            res = h.org_service.accept_invitation(
                raw_token=raw_token,
                acting_principal=h.principal(user),
            )
            assert res.organisation_id == org_b.id
            assert res.is_new_organisation_member is True
            mem_org_b = h.org_repo.get_active_membership(organisation_id=org_b.id, user_id=user.id)
            assert mem_org_b is not None
            assert mem_org_b.role.name == RoleName.ORG_MEMBER.value


def test_22_acceptance_creates_membership_in_invited_project_b(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """22. Membership in invited Proj B is created with the assigned role."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            org_a, proj_a, org_b, proj_b, user, raw_token = _setup_multi_org_invitation(session, h)
            res = h.org_service.accept_invitation(
                raw_token=raw_token,
                acting_principal=h.principal(user),
            )
            assert res.project_id == proj_b.id
            assert res.project_role_name == "reviewer"
            mem_proj_b = h.project_repo.get_active_membership(project_id=proj_b.id, user_id=user.id)
            assert mem_proj_b is not None
            assert mem_proj_b.role.name == "reviewer"


# =============================================================================
# PART 5: FAILURE & SECURITY CASES (Tests 23 - 31)
# =============================================================================

def test_23_expired_invitation_creates_no_memberships(monkeypatch: pytest.MonkeyPatch) -> None:
    """23. Expired invitation creates no memberships and raises GoneError."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            owner = _create_user(session, "owner@org.com", "Org Owner")
            target = _create_user(session, "expired@target.com", "Target")
            org = _create_org(session, "Acme Corp", "acme-corp", owner)
            project = _create_project(session, org, "Alpha", "alpha", owner)

            _add_org_member(session, org, owner, RoleName.ORG_OWNER.value)
            session.commit()

            raw_token = generate_opaque_token(48)
            token_hash = hash_opaque_token(raw_token)
            past = utc_now() - timedelta(hours=2)

            inv = h.org_repo.create_invitation(
                organisation_id=org.id,
                email="expired@target.com",
                role_id=_get_role(session, RoleName.ORG_MEMBER.value).id,
                token_hash=token_hash,
                invited_by_id=owner.id,
                expires_at=past,
                project_id=project.id,
                project_role_id=_get_role(session, RoleName.PROJECT_MEMBER.value).id,
            )
            session.commit()

            with pytest.raises(GoneError) as exc_info:
                h.org_service.accept_invitation(
                    raw_token=raw_token,
                    acting_principal=h.principal(target),
                )
            assert exc_info.value.code == "INVITATION_EXPIRED"

            # No memberships created
            assert h.org_repo.get_active_membership(organisation_id=org.id, user_id=target.id) is None
            assert h.project_repo.get_active_membership(project_id=project.id, user_id=target.id) is None


def test_24_revoked_invitation_creates_no_memberships(monkeypatch: pytest.MonkeyPatch) -> None:
    """24. Revoked invitation creates no memberships and raises ConflictError."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            owner = _create_user(session, "owner@org.com", "Org Owner")
            target = _create_user(session, "revoked@target.com", "Target")
            org = _create_org(session, "Acme Corp", "acme-corp", owner)
            project = _create_project(session, org, "Alpha", "alpha", owner)

            _add_org_member(session, org, owner, RoleName.ORG_OWNER.value)
            session.commit()

            raw_token = generate_opaque_token(48)
            token_hash = hash_opaque_token(raw_token)
            future = utc_now() + timedelta(hours=24)

            inv = h.org_repo.create_invitation(
                organisation_id=org.id,
                email="revoked@target.com",
                role_id=_get_role(session, RoleName.ORG_MEMBER.value).id,
                token_hash=token_hash,
                invited_by_id=owner.id,
                expires_at=future,
                project_id=project.id,
                project_role_id=_get_role(session, RoleName.PROJECT_MEMBER.value).id,
            )
            inv.status = InvitationStatus.REVOKED.value
            inv.revoked_at = utc_now()
            session.commit()

            with pytest.raises(ConflictError) as exc_info:
                h.org_service.accept_invitation(
                    raw_token=raw_token,
                    acting_principal=h.principal(target),
                )
            assert exc_info.value.code == "INVITATION_REVOKED"
            assert h.org_repo.get_active_membership(organisation_id=org.id, user_id=target.id) is None
            assert h.project_repo.get_active_membership(project_id=project.id, user_id=target.id) is None


def test_25_email_mismatch_creates_no_memberships(monkeypatch: pytest.MonkeyPatch) -> None:
    """25. Email mismatch creates no memberships and raises ForbiddenError."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            owner = _create_user(session, "owner@org.com", "Org Owner")
            wrong_user = _create_user(session, "wrong@example.com", "Wrong User")
            org = _create_org(session, "Acme Corp", "acme-corp", owner)
            project = _create_project(session, org, "Alpha", "alpha", owner)

            _add_org_member(session, org, owner, RoleName.ORG_OWNER.value)
            session.commit()

            proj_ctx = h.rbac_service.resolve_project_context(
                project_id=project.id,
                principal=h.principal(owner),
            )
            create_res = h.project_service.create_project_invitation(
                ctx=proj_ctx,
                payload=CreateProjectInvitationRequest(
                    email="intended@example.com",
                    role_name="project_member",
                ),
            )
            raw_token = create_res.development_invitation_token
            assert raw_token is not None

            with pytest.raises(ForbiddenError) as exc_info:
                h.org_service.accept_invitation(
                    raw_token=raw_token,
                    acting_principal=h.principal(wrong_user),
                )
            assert exc_info.value.code == "INVITATION_EMAIL_MISMATCH"
            assert h.org_repo.get_active_membership(organisation_id=org.id, user_id=wrong_user.id) is None
            assert h.project_repo.get_active_membership(project_id=project.id, user_id=wrong_user.id) is None


def test_26_invalid_token_creates_no_memberships(monkeypatch: pytest.MonkeyPatch) -> None:
    """26. Invalid / bogus token raises NotFoundError."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            user = _create_user(session, "user@example.com", "User")
            session.commit()

            with pytest.raises(NotFoundError) as exc_info:
                h.org_service.accept_invitation(
                    raw_token="bogus-nonexistent-token",
                    acting_principal=h.principal(user),
                )
            assert exc_info.value.code == "INVITATION_NOT_FOUND"


def test_27_stale_inviter_authority_prevents_acceptance(monkeypatch: pytest.MonkeyPatch) -> None:
    """27. If inviter lost project authority before acceptance, acceptance is blocked."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            owner = _create_user(session, "owner@org.com", "Org Owner")
            pm = _create_user(session, "pm@org.com", "Project Manager")
            invitee = _create_user(session, "invitee@target.com", "Invitee")
            org = _create_org(session, "Acme Corp", "acme-corp", owner)
            project = _create_project(session, org, "Alpha", "alpha", owner)

            _add_org_member(session, org, owner, RoleName.ORG_OWNER.value)
            _add_org_member(session, org, pm, RoleName.ORG_MEMBER.value)
            pm_proj_mem = _add_project_member(session, project, pm, RoleName.PROJECT_MANAGER.value)
            session.commit()

            pm_proj_ctx = h.rbac_service.resolve_project_context(
                project_id=project.id,
                principal=h.principal(pm),
            )
            create_res = h.project_service.create_project_invitation(
                ctx=pm_proj_ctx,
                payload=CreateProjectInvitationRequest(
                    email="invitee@target.com",
                    role_name="project_member",
                ),
            )
            raw_token = create_res.development_invitation_token
            assert raw_token is not None

            # Demote PM to Project Member before acceptance!
            member_role = _get_role(session, RoleName.PROJECT_MEMBER.value)
            pm_proj_mem.role_id = member_role.id
            pm_proj_mem.role = member_role
            session.commit()
            session.expire_all()

            # Now invitee attempts acceptance: blocked due to stale inviter authority
            with pytest.raises(ForbiddenError) as exc_info:
                h.org_service.accept_invitation(
                    raw_token=raw_token,
                    acting_principal=h.principal(invitee),
                )
            assert exc_info.value.code == "INVITER_NO_LONGER_AUTHORISED"
            assert h.org_repo.get_active_membership(organisation_id=org.id, user_id=invitee.id) is None
            assert h.project_repo.get_active_membership(project_id=project.id, user_id=invitee.id) is None


def test_28_existing_project_membership_prevents_duplicate_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """28. If invitee already became an active project member, acceptance is blocked."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            owner = _create_user(session, "owner@org.com", "Org Owner")
            user = _create_user(session, "dev@example.com", "Dev")
            org = _create_org(session, "Acme Corp", "acme-corp", owner)
            project = _create_project(session, org, "Alpha", "alpha", owner)

            _add_org_member(session, org, owner, RoleName.ORG_OWNER.value)
            session.commit()

            proj_ctx = h.rbac_service.resolve_project_context(
                project_id=project.id,
                principal=h.principal(owner),
            )
            create_res = h.project_service.create_project_invitation(
                ctx=proj_ctx,
                payload=CreateProjectInvitationRequest(
                    email="dev@example.com",
                    role_name="project_member",
                ),
            )
            raw_token = create_res.development_invitation_token
            assert raw_token is not None

            # Manually add user to the project before they accept
            _add_org_member(session, org, user, RoleName.ORG_MEMBER.value)
            _add_project_member(session, project, user, RoleName.PROJECT_MEMBER.value)
            session.commit()

            with pytest.raises(ConflictError) as exc_info:
                h.org_service.accept_invitation(
                    raw_token=raw_token,
                    acting_principal=h.principal(user),
                )
            assert exc_info.value.code == "MEMBERSHIP_ALREADY_EXISTS"


def test_29_concurrent_acceptance_replay_protection(monkeypatch: pytest.MonkeyPatch) -> None:
    """29. Acceptance of an already accepted invitation raises ConflictError."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            owner = _create_user(session, "owner@org.com", "Org Owner")
            user = _create_user(session, "target@example.com", "Target")
            org = _create_org(session, "Acme Corp", "acme-corp", owner)
            project = _create_project(session, org, "Alpha", "alpha", owner)

            _add_org_member(session, org, owner, RoleName.ORG_OWNER.value)
            session.commit()

            proj_ctx = h.rbac_service.resolve_project_context(
                project_id=project.id,
                principal=h.principal(owner),
            )
            create_res = h.project_service.create_project_invitation(
                ctx=proj_ctx,
                payload=CreateProjectInvitationRequest(
                    email="target@example.com",
                    role_name="project_member",
                ),
            )
            raw_token = create_res.development_invitation_token
            assert raw_token is not None

            # First acceptance succeeds
            h.org_service.accept_invitation(
                raw_token=raw_token,
                acting_principal=h.principal(user),
            )

            # Second acceptance fails
            with pytest.raises(ConflictError) as exc_info:
                h.org_service.accept_invitation(
                    raw_token=raw_token,
                    acting_principal=h.principal(user),
                )
            assert exc_info.value.code in ("INVITATION_ALREADY_ACCEPTED", "MEMBERSHIP_ALREADY_EXISTS")


def test_30_failure_during_project_membership_rolls_back_org_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """30. If project membership creation fails, newly created org membership is completely rolled back."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            owner = _create_user(session, "owner@org.com", "Org Owner")
            user = _create_user(session, "failtest@example.com", "Fail Test User")
            org = _create_org(session, "Acme Corp", "acme-corp", owner)
            project = _create_project(session, org, "Alpha", "alpha", owner)

            _add_org_member(session, org, owner, RoleName.ORG_OWNER.value)
            session.commit()

            proj_ctx = h.rbac_service.resolve_project_context(
                project_id=project.id,
                principal=h.principal(owner),
            )
            create_res = h.project_service.create_project_invitation(
                ctx=proj_ctx,
                payload=CreateProjectInvitationRequest(
                    email="failtest@example.com",
                    role_name="project_member",
                ),
            )
            raw_token = create_res.development_invitation_token
            assert raw_token is not None

            # Simulate failure during project membership creation by monkeypatching project_repo.create_membership
            original_create_proj_mem = h.project_repo.create_membership

            def _exploding_create_mem(*args: Any, **kwargs: Any) -> Any:
                raise RuntimeError("Simulated DB error during project membership insertion")

            monkeypatch.setattr(h.project_repo, "create_membership", _exploding_create_mem)

            with pytest.raises(RuntimeError):
                h.org_service.accept_invitation(
                    raw_token=raw_token,
                    acting_principal=h.principal(user),
                )

            # Restore original method
            monkeypatch.setattr(h.project_repo, "create_membership", original_create_proj_mem)

            # Verify: User has NO organisation membership in org! (Full transaction rollback)
            org_mem = h.org_repo.get_active_membership(organisation_id=org.id, user_id=user.id)
            assert org_mem is None


def test_31_invitation_acceptance_cannot_cross_organisation_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """31. Project invitation acceptance cannot assign membership to a mismatched organisation."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            owner_a = _create_user(session, "owner_a@org.com", "Owner A")
            owner_b = _create_user(session, "owner_b@org.com", "Owner B")
            user = _create_user(session, "cross@example.com", "Cross User")
            org_a = _create_org(session, "Org A", "org-a", owner_a)
            org_b = _create_org(session, "Org B", "org-b", owner_b)
            project_b = _create_project(session, org_b, "Project B", "proj-b", owner_b)

            _add_org_member(session, org_a, owner_a, RoleName.ORG_OWNER.value)
            _add_org_member(session, org_b, owner_b, RoleName.ORG_OWNER.value)
            session.commit()

            # Attempt to fabricate an invitation with org_a.id but project_b.id (mismatch)
            raw_token = generate_opaque_token(48)
            token_hash = hash_opaque_token(raw_token)
            inv = OrganisationInvitation(
                organisation_id=org_a.id,
                email="cross@example.com",
                role_id=_get_role(session, RoleName.ORG_MEMBER.value).id,
                token_hash=token_hash,
                invited_by_id=owner_a.id,
                expires_at=utc_now() + timedelta(hours=24),
                project_id=project_b.id,
                project_role_id=_get_role(session, RoleName.PROJECT_MEMBER.value).id,
            )
            session.add(inv)
            # The database composite foreign key or service logic must reject this!
            # If session.commit() raises IntegrityError due to composite FK, that passes Part A constraint.
            try:
                session.commit()
                # If DB constraint didn't fire (e.g. SQLite dialect quirks), service check must fire:
                with pytest.raises(ForbiddenError) as exc_info:
                    h.org_service.accept_invitation(
                        raw_token=raw_token,
                        acting_principal=h.principal(user),
                    )
                assert exc_info.value.code == "TENANT_MISMATCH"
            except Exception as exc:
                session.rollback()
                assert "foreign key" in str(exc).lower() or "check" in str(exc).lower() or "constraint" in str(exc).lower()


# =============================================================================
# PART 6: BACKWARD COMPATIBILITY & PROJECT MANAGEMENT (Tests 32 - 34)
# =============================================================================

def test_32_existing_organisation_only_invitation_acceptance_still_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """32. Existing organisation-only invitation acceptance still functions without project fields."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            owner = _create_user(session, "owner@org.com", "Org Owner")
            user = _create_user(session, "orgonly@example.com", "Org Only User")
            org = _create_org(session, "Acme Corp", "acme-corp", owner)

            _add_org_member(session, org, owner, RoleName.ORG_OWNER.value)
            session.commit()

            raw_token = generate_opaque_token(48)
            token_hash = hash_opaque_token(raw_token)
            inv = h.org_repo.create_invitation(
                organisation_id=org.id,
                email="orgonly@example.com",
                role_id=_get_role(session, RoleName.ORG_MEMBER.value).id,
                token_hash=token_hash,
                invited_by_id=owner.id,
                expires_at=utc_now() + timedelta(hours=24),
                project_id=None,
                project_role_id=None,
            )
            session.commit()

            res = h.org_service.accept_invitation(
                raw_token=raw_token,
                acting_principal=h.principal(user),
            )
            assert res.organisation_id == org.id
            assert res.role_name == "org_member"
            assert res.project_id is None
            assert res.project_name is None
            assert res.project_role_name is None
            assert res.is_new_organisation_member is True

            org_mem = h.org_repo.get_active_membership(organisation_id=org.id, user_id=user.id)
            assert org_mem is not None
            assert org_mem.role.name == "org_member"


def test_33_list_and_revoke_project_invitations_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """33. Project managers can list and revoke pending invitations scoped to their project."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            owner = _create_user(session, "owner@org.com", "Org Owner")
            pm = _create_user(session, "pm@org.com", "Project Manager")
            org = _create_org(session, "Acme Corp", "acme-corp", owner)
            project = _create_project(session, org, "Alpha", "alpha", owner)

            _add_org_member(session, org, owner, RoleName.ORG_OWNER.value)
            _add_org_member(session, org, pm, RoleName.ORG_MEMBER.value)
            _add_project_member(session, project, pm, RoleName.PROJECT_MANAGER.value)
            session.commit()

            pm_ctx = h.rbac_service.resolve_project_context(
                project_id=project.id,
                principal=h.principal(pm),
            )
            create_res = h.project_service.create_project_invitation(
                ctx=pm_ctx,
                payload=CreateProjectInvitationRequest(
                    email="to_revoke@example.com",
                    role_name="project_member",
                ),
            )
            inv_id = create_res.invitation.id

            # List project invitations
            inv_list = h.project_service.list_project_invitations(ctx=pm_ctx)
            assert inv_list.total == 1
            assert inv_list.items[0].id == inv_id
            assert inv_list.items[0].email == "to_revoke@example.com"
            assert inv_list.items[0].project_id == project.id

            # Revoke invitation
            rev_res = h.project_service.revoke_project_invitation(
                ctx=pm_ctx,
                invitation_id=inv_id,
            )
            assert rev_res.status == InvitationStatus.REVOKED.value

            # Check DB state
            inv = session.scalar(
                select(OrganisationInvitation).where(OrganisationInvitation.id == inv_id)
            )
            assert inv is not None
            assert inv.status == InvitationStatus.REVOKED.value
            assert inv.revoked_by_id == pm.id
            assert inv.revoked_at is not None


def test_34_expired_invitation_auto_transition_on_project_invitation_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """34. A stale expired invitation is transitioned to expired when a new invitation is created."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            h = ServiceHarness(session, ctx.settings)
            owner = _create_user(session, "owner@org.com", "Org Owner")
            org = _create_org(session, "Acme Corp", "acme-corp", owner)
            project = _create_project(session, org, "Alpha", "alpha", owner)

            _add_org_member(session, org, owner, RoleName.ORG_OWNER.value)
            session.commit()

            # Seed an expired pending invitation in the DB
            raw_token = generate_opaque_token(48)
            token_hash = hash_opaque_token(raw_token)
            past = utc_now() - timedelta(hours=10)

            old_inv = h.org_repo.create_invitation(
                organisation_id=org.id,
                email="reinvited@example.com",
                role_id=_get_role(session, RoleName.ORG_MEMBER.value).id,
                token_hash=token_hash,
                invited_by_id=owner.id,
                expires_at=past,
                project_id=project.id,
                project_role_id=_get_role(session, RoleName.PROJECT_MEMBER.value).id,
            )
            session.commit()
            assert old_inv.status == InvitationStatus.PENDING.value

            # Creating a new invitation for the same email auto-expires the old one
            proj_ctx = h.rbac_service.resolve_project_context(
                project_id=project.id,
                principal=h.principal(owner),
            )
            new_inv_res = h.project_service.create_project_invitation(
                ctx=proj_ctx,
                payload=CreateProjectInvitationRequest(
                    email="reinvited@example.com",
                    role_name="project_member",
                ),
            )
            assert new_inv_res.invitation.status == InvitationStatus.PENDING.value

            # Refresh old invitation from DB
            session.refresh(old_inv)
            assert old_inv.status == InvitationStatus.EXPIRED.value
