"""Focused tests for Project Invitation Schema, Constraints, and RBAC Foundation (Phase 1)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ForbiddenError
from app.core.rbac_catalog import (
    PROJECT_ROLE_RANK,
    SYSTEM_PERMISSIONS,
    SYSTEM_ROLES,
)
from app.core.security import generate_opaque_token, hash_opaque_token, utc_now
from app.models.enums import InvitationStatus, ProjectStatus, RoleName, RoleScopeType
from app.models.organisation import Organisation, OrganisationInvitation, OrganisationMembership
from app.models.project import Project, ProjectMembership
from app.models.rbac import Permission, Role
from app.models.user import User
from app.repositories.organisation import OrganisationRepository
from app.repositories.project import ProjectRepository
from app.repositories.rbac import RbacRepository
from app.repositories.user import UserRepository
from app.schemas.organisation import InvitationSummaryResponse
from app.services.rbac import AuthenticatedPrincipal, RbacService
from tests.conftest import isolated_auth_app


def _create_user(session, email: str, name: str) -> User:
    user = User(
        email=email.lower().strip(),
        full_name=name,
        password_hash="test-hash",
        is_email_verified=True,
    )
    session.add(user)
    session.flush()
    return user


def _create_org(session, name: str, slug: str, creator: User) -> Organisation:
    org = Organisation(
        name=name,
        slug=slug,
        created_by_id=creator.id,
    )
    session.add(org)
    session.flush()
    return org


def _create_project(session, org: Organisation, name: str, slug: str, creator: User) -> Project:
    project = Project(
        organisation_id=org.id,
        name=name,
        slug=slug,
        created_by_id=creator.id,
        owner_id=creator.id,
        status=ProjectStatus.ACTIVE.value,
    )
    session.add(project)
    session.flush()
    return project


def _get_role(session, name: str) -> Role:
    role = session.scalar(select(Role).where(Role.name == name))
    assert role is not None, f"Role {name} not found in catalog"
    return role


# -----------------------------------------------------------------------------
# Part E, Item 10: RBAC Catalog Registration & Role Rankings
# -----------------------------------------------------------------------------

def test_project_invitation_permissions_registered_in_catalog() -> None:
    """Verify project.invitations.read and manage are defined with PROJECT scope."""
    perm_codes = {spec.code: spec for spec in SYSTEM_PERMISSIONS}
    assert "project.invitations.read" in perm_codes
    assert "project.invitations.manage" in perm_codes

    read_perm = perm_codes["project.invitations.read"]
    assert read_perm.scope_type == RoleScopeType.PROJECT
    assert "Read" in read_perm.name

    manage_perm = perm_codes["project.invitations.manage"]
    assert manage_perm.scope_type == RoleScopeType.PROJECT
    assert "Manage" in manage_perm.name

    # Check project role rankings
    assert PROJECT_ROLE_RANK[RoleName.PROJECT_MEMBER.value] == 1
    assert PROJECT_ROLE_RANK[RoleName.REVIEWER.value] == 1
    assert PROJECT_ROLE_RANK[RoleName.PROJECT_MANAGER.value] == 2


def test_role_catalog_permission_mappings() -> None:
    """Verify correct roles receive project.invitations permissions."""
    role_map = {role.name: set(role.permission_codes) for role in SYSTEM_ROLES}

    # Project Manager has both
    assert "project.invitations.read" in role_map[RoleName.PROJECT_MANAGER.value]
    assert "project.invitations.manage" in role_map[RoleName.PROJECT_MANAGER.value]

    # Org Owner and Org Admin have both
    assert "project.invitations.read" in role_map[RoleName.ORG_OWNER.value]
    assert "project.invitations.manage" in role_map[RoleName.ORG_OWNER.value]
    assert "project.invitations.read" in role_map[RoleName.ORG_ADMIN.value]
    assert "project.invitations.manage" in role_map[RoleName.ORG_ADMIN.value]

    # Project Member and Reviewer must NOT have manage permission
    assert "project.invitations.manage" not in role_map[RoleName.PROJECT_MEMBER.value]
    assert "project.invitations.manage" not in role_map[RoleName.REVIEWER.value]


# -----------------------------------------------------------------------------
# Part E, Items 1 & 2: Organisation Invitations Remain Valid & have NULL project fields
# -----------------------------------------------------------------------------

def test_existing_org_invitations_have_null_project_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify organisation-only invitations have NULL project fields and load cleanly."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            creator = _create_user(session, "creator@test.com", "Creator")
            org = _create_org(session, "Org One", "org-one", creator)
            org_member_role = _get_role(session, RoleName.ORG_MEMBER.value)

            token_hash = hash_opaque_token(generate_opaque_token(48))
            expires = utc_now() + timedelta(days=3)

            org_repo = OrganisationRepository(session)
            invitation = org_repo.create_invitation(
                organisation_id=org.id,
                email="invitee@test.com",
                role_id=org_member_role.id,
                token_hash=token_hash,
                invited_by_id=creator.id,
                expires_at=expires,
            )
            session.commit()

            # Verify fields
            assert invitation.project_id is None
            assert invitation.project_role_id is None
            assert invitation.status == InvitationStatus.PENDING.value
            assert invitation.project is None
            assert invitation.project_role is None

            # Verify summary schema projection
            summary = InvitationSummaryResponse(
                id=invitation.id,
                organisation_id=invitation.organisation_id,
                email=invitation.email,
                role_name=org_member_role.name,
                project_id=invitation.project_id,
                project_role_name=None,
                status=invitation.status,
                invited_by_id=invitation.invited_by_id,
                expires_at=invitation.expires_at,
                accepted_at=invitation.accepted_at,
                revoked_at=invitation.revoked_at,
                created_at=invitation.created_at,
            )
            assert summary.project_id is None
            assert summary.project_role_name is None


# -----------------------------------------------------------------------------
# Part E, Item 3: Project Invitation Can Reference Valid Projects
# -----------------------------------------------------------------------------

def test_project_invitation_references_valid_project(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify project invitations store and load project and project_role relationships."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            creator = _create_user(session, "creator@test.com", "Creator")
            org = _create_org(session, "Org One", "org-one", creator)
            project = _create_project(session, org, "Alpha Project", "alpha", creator)

            org_member_role = _get_role(session, RoleName.ORG_MEMBER.value)
            proj_member_role = _get_role(session, RoleName.PROJECT_MEMBER.value)

            token_hash = hash_opaque_token(generate_opaque_token(48))
            expires = utc_now() + timedelta(days=3)

            org_repo = OrganisationRepository(session)
            invitation = org_repo.create_invitation(
                organisation_id=org.id,
                email="dev@test.com",
                role_id=org_member_role.id,
                token_hash=token_hash,
                invited_by_id=creator.id,
                expires_at=expires,
                project_id=project.id,
                project_role_id=proj_member_role.id,
            )
            session.commit()

            # Retrieve with update lock method to verify eager options
            loaded = org_repo.get_invitation_by_token_hash_for_update(token_hash)
            assert loaded is not None
            assert loaded.project_id == project.id
            assert loaded.project_role_id == proj_member_role.id
            assert loaded.project is not None
            assert loaded.project.name == "Alpha Project"
            assert loaded.project_role is not None
            assert loaded.project_role.name == RoleName.PROJECT_MEMBER.value


# -----------------------------------------------------------------------------
# Part E, Item 4: Project Invitation Organisation Must Match Project Organisation
# -----------------------------------------------------------------------------

def test_project_invitation_rejects_mismatched_organisation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enforce composite FK: project_id's parent organisation must match organisation_id."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            creator = _create_user(session, "creator@test.com", "Creator")
            org1 = _create_org(session, "Org One", "org-one", creator)
            org2 = _create_org(session, "Org Two", "org-two", creator)
            proj1 = _create_project(session, org1, "Alpha Project", "alpha", creator)

            org_member_role = _get_role(session, RoleName.ORG_MEMBER.value)
            proj_member_role = _get_role(session, RoleName.PROJECT_MEMBER.value)

            token_hash = hash_opaque_token(generate_opaque_token(48))
            expires = utc_now() + timedelta(days=3)

            # Attempt to create invitation in org2 referencing a project that belongs to org1
            invitation = OrganisationInvitation(
                organisation_id=org2.id,  # Mismatched!
                email="infiltrator@test.com",
                role_id=org_member_role.id,
                project_id=proj1.id,  # belongs to org1!
                project_role_id=proj_member_role.id,
                token_hash=token_hash,
                invited_by_id=creator.id,
                status=InvitationStatus.PENDING.value,
                expires_at=expires,
            )
            session.add(invitation)
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()


# -----------------------------------------------------------------------------
# Part E, Items 5 & 6: Pair Invariant - Both Project Fields Populated or Both Null
# -----------------------------------------------------------------------------

def test_project_invitation_pair_check_constraint_rejects_partial_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify check constraint rejects partial project fields in either direction."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            creator = _create_user(session, "creator@test.com", "Creator")
            org = _create_org(session, "Org One", "org-one", creator)
            project = _create_project(session, org, "Alpha Project", "alpha", creator)

            org_member_role = _get_role(session, RoleName.ORG_MEMBER.value)
            proj_member_role = _get_role(session, RoleName.PROJECT_MEMBER.value)
            expires = utc_now() + timedelta(days=3)

            # Case A: project_id populated, project_role_id is None
            token_hash_a = hash_opaque_token(generate_opaque_token(48))
            inv_a = OrganisationInvitation(
                organisation_id=org.id,
                email="partial_a@test.com",
                role_id=org_member_role.id,
                project_id=project.id,
                project_role_id=None,  # Missing!
                token_hash=token_hash_a,
                invited_by_id=creator.id,
                status=InvitationStatus.PENDING.value,
                expires_at=expires,
            )
            session.add(inv_a)
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

            # Case B: project_role_id populated, project_id is None
            token_hash_b = hash_opaque_token(generate_opaque_token(48))
            inv_b = OrganisationInvitation(
                organisation_id=org.id,
                email="partial_b@test.com",
                role_id=org_member_role.id,
                project_id=None,  # Missing!
                project_role_id=proj_member_role.id,
                token_hash=token_hash_b,
                invited_by_id=creator.id,
                status=InvitationStatus.PENDING.value,
                expires_at=expires,
            )
            session.add(inv_b)
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()


# -----------------------------------------------------------------------------
# Part E, Item 7: Duplicate Pending Invitations Prevented for Same Project & Email
# -----------------------------------------------------------------------------

def test_duplicate_pending_project_invitations_prevented(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify partial unique index prevents duplicate pending invites to same project."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            creator = _create_user(session, "creator@test.com", "Creator")
            org = _create_org(session, "Org One", "org-one", creator)
            project = _create_project(session, org, "Alpha Project", "alpha", creator)

            org_member_role = _get_role(session, RoleName.ORG_MEMBER.value)
            proj_member_role = _get_role(session, RoleName.PROJECT_MEMBER.value)
            expires = utc_now() + timedelta(days=3)

            org_repo = OrganisationRepository(session)
            # First invite to project
            org_repo.create_invitation(
                organisation_id=org.id,
                email="duplicate@test.com",
                role_id=org_member_role.id,
                project_id=project.id,
                project_role_id=proj_member_role.id,
                token_hash=hash_opaque_token(generate_opaque_token(48)),
                invited_by_id=creator.id,
                expires_at=expires,
            )
            session.commit()

            # Verify pending project lookup finds it
            pending = org_repo.get_pending_project_invitation(
                project_id=project.id,
                normalised_email="duplicate@test.com",
            )
            assert pending is not None

            # Attempt duplicate invite to the same project
            with pytest.raises(IntegrityError):
                org_repo.create_invitation(
                    organisation_id=org.id,
                    email="duplicate@test.com",
                    role_id=org_member_role.id,
                    project_id=project.id,
                    project_role_id=proj_member_role.id,
                    token_hash=hash_opaque_token(generate_opaque_token(48)),
                    invited_by_id=creator.id,
                    expires_at=expires,
                )
            session.rollback()


# -----------------------------------------------------------------------------
# Part E, Item 8: Invitations to Different Projects in Same Org Can Coexist
# -----------------------------------------------------------------------------

def test_pending_invitations_to_different_projects_can_coexist(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify an email can have pending invitations to different projects and org-level simultaneously."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            creator = _create_user(session, "creator@test.com", "Creator")
            org = _create_org(session, "Org One", "org-one", creator)
            p1 = _create_project(session, org, "Project 1", "proj-1", creator)
            p2 = _create_project(session, org, "Project 2", "proj-2", creator)

            org_member_role = _get_role(session, RoleName.ORG_MEMBER.value)
            proj_member_role = _get_role(session, RoleName.PROJECT_MEMBER.value)
            expires = utc_now() + timedelta(days=3)

            org_repo = OrganisationRepository(session)

            # 1. Invite to project 1
            inv_p1 = org_repo.create_invitation(
                organisation_id=org.id,
                email="multitasker@test.com",
                role_id=org_member_role.id,
                project_id=p1.id,
                project_role_id=proj_member_role.id,
                token_hash=hash_opaque_token(generate_opaque_token(48)),
                invited_by_id=creator.id,
                expires_at=expires,
            )

            # 2. Invite to project 2
            inv_p2 = org_repo.create_invitation(
                organisation_id=org.id,
                email="multitasker@test.com",
                role_id=org_member_role.id,
                project_id=p2.id,
                project_role_id=proj_member_role.id,
                token_hash=hash_opaque_token(generate_opaque_token(48)),
                invited_by_id=creator.id,
                expires_at=expires,
            )

            # 3. Org-level invite (project_id=None)
            inv_org = org_repo.create_invitation(
                organisation_id=org.id,
                email="multitasker@test.com",
                role_id=org_member_role.id,
                token_hash=hash_opaque_token(generate_opaque_token(48)),
                invited_by_id=creator.id,
                expires_at=expires,
            )
            session.commit()

            # All three co-exist peacefully
            assert inv_p1.id != inv_p2.id != inv_org.id
            assert org_repo.get_pending_project_invitation(project_id=p1.id, normalised_email="multitasker@test.com") is not None
            assert org_repo.get_pending_project_invitation(project_id=p2.id, normalised_email="multitasker@test.com") is not None
            assert org_repo.get_pending_invitation(organisation_id=org.id, normalised_email="multitasker@test.com") is not None


# -----------------------------------------------------------------------------
# Part E, Item 9: Existing Org Invitation Uniqueness Remains Intact
# -----------------------------------------------------------------------------

def test_existing_org_invitation_uniqueness_remains_intact(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify duplicate pending organisation-only invitations are still rejected."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            creator = _create_user(session, "creator@test.com", "Creator")
            org = _create_org(session, "Org One", "org-one", creator)
            org_member_role = _get_role(session, RoleName.ORG_MEMBER.value)
            expires = utc_now() + timedelta(days=3)

            org_repo = OrganisationRepository(session)

            # First org invite
            org_repo.create_invitation(
                organisation_id=org.id,
                email="single_org@test.com",
                role_id=org_member_role.id,
                token_hash=hash_opaque_token(generate_opaque_token(48)),
                invited_by_id=creator.id,
                expires_at=expires,
            )
            session.commit()

            # Second org invite to same email and org
            with pytest.raises(IntegrityError):
                org_repo.create_invitation(
                    organisation_id=org.id,
                    email="single_org@test.com",
                    role_id=org_member_role.id,
                    token_hash=hash_opaque_token(generate_opaque_token(48)),
                    invited_by_id=creator.id,
                    expires_at=expires,
                )
            session.rollback()


# -----------------------------------------------------------------------------
# Part E, Items 11, 12, 13: RBAC Service Project Role Authority Checks
# -----------------------------------------------------------------------------

def test_project_manager_can_manage_project_invitations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Project Manager can manage invitations and grant allowed project roles."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            creator = _create_user(session, "creator@test.com", "Creator")
            pm_user = _create_user(session, "pm@test.com", "Project Manager User")
            org = _create_org(session, "Org One", "org-one", creator)
            project = _create_project(session, org, "Alpha Project", "alpha", creator)

            org_member_role = _get_role(session, RoleName.ORG_MEMBER.value)
            pm_role = _get_role(session, RoleName.PROJECT_MANAGER.value)

            # Add pm_user as org member
            session.add(OrganisationMembership(
                organisation_id=org.id,
                user_id=pm_user.id,
                role_id=org_member_role.id,
            ))
            # Add pm_user as project manager
            session.add(ProjectMembership(
                project_id=project.id,
                user_id=pm_user.id,
                role_id=pm_role.id,
            ))
            session.commit()

            rbac = RbacService(
                db_session=session,
                rbac_repository=RbacRepository(session),
                user_repository=UserRepository(session),
            )
            principal = AuthenticatedPrincipal(
                user=pm_user,
                session_family_id=uuid.uuid4(),
                roles=(RoleName.STANDARD_USER.value,),
                permissions=frozenset(),
            )

            p_ctx = rbac.resolve_project_context(project_id=project.id, principal=principal)

            # Assert permissions
            assert p_ctx.has_permission("project.invitations.read") is True
            assert p_ctx.has_permission("project.invitations.manage") is True

            # PM (rank 2) can assign Project Member (rank 1), Reviewer (rank 1), and Project Manager (rank 2)
            rbac.require_project_role_authority(
                actor_role_name=pm_role.name,
                target_role_name=RoleName.PROJECT_MEMBER.value,
                actor_user_id=pm_user.id,
                project_id=project.id,
                organisation_id=org.id,
                action_label="invite",
            )
            rbac.require_project_role_authority(
                actor_role_name=pm_role.name,
                target_role_name=RoleName.REVIEWER.value,
                actor_user_id=pm_user.id,
                project_id=project.id,
                organisation_id=org.id,
                action_label="invite",
            )
            rbac.require_project_role_authority(
                actor_role_name=pm_role.name,
                target_role_name=RoleName.PROJECT_MANAGER.value,
                actor_user_id=pm_user.id,
                project_id=project.id,
                organisation_id=org.id,
                action_label="invite",
            )


def test_project_member_cannot_manage_project_invitations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Project Member has no invitation manage permissions and cannot escalate roles."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            creator = _create_user(session, "creator@test.com", "Creator")
            member_user = _create_user(session, "member@test.com", "Member User")
            org = _create_org(session, "Org One", "org-one", creator)
            project = _create_project(session, org, "Alpha Project", "alpha", creator)

            org_member_role = _get_role(session, RoleName.ORG_MEMBER.value)
            proj_member_role = _get_role(session, RoleName.PROJECT_MEMBER.value)

            session.add(OrganisationMembership(
                organisation_id=org.id,
                user_id=member_user.id,
                role_id=org_member_role.id,
            ))
            session.add(ProjectMembership(
                project_id=project.id,
                user_id=member_user.id,
                role_id=proj_member_role.id,
            ))
            session.commit()

            rbac = RbacService(
                db_session=session,
                rbac_repository=RbacRepository(session),
                user_repository=UserRepository(session),
            )
            principal = AuthenticatedPrincipal(
                user=member_user,
                session_family_id=uuid.uuid4(),
                roles=(RoleName.STANDARD_USER.value,),
                permissions=frozenset(),
            )

            p_ctx = rbac.resolve_project_context(project_id=project.id, principal=principal)

            # Assert permissions
            assert p_ctx.has_permission("project.invitations.manage") is False

            # Project Member (rank 1) cannot assign Project Manager (rank 2)
            with pytest.raises(ForbiddenError) as exc_info:
                rbac.require_project_role_authority(
                    actor_role_name=proj_member_role.name,
                    target_role_name=RoleName.PROJECT_MANAGER.value,
                    actor_user_id=member_user.id,
                    project_id=project.id,
                    organisation_id=org.id,
                    action_label="invite",
                )
            assert exc_info.value.code == "INSUFFICIENT_ROLE_AUTHORITY"


def test_reviewer_cannot_manage_project_invitations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Reviewer has no invitation manage permissions and cannot escalate roles."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            creator = _create_user(session, "creator@test.com", "Creator")
            reviewer_user = _create_user(session, "reviewer@test.com", "Reviewer User")
            org = _create_org(session, "Org One", "org-one", creator)
            project = _create_project(session, org, "Alpha Project", "alpha", creator)

            org_member_role = _get_role(session, RoleName.ORG_MEMBER.value)
            reviewer_role = _get_role(session, RoleName.REVIEWER.value)

            session.add(OrganisationMembership(
                organisation_id=org.id,
                user_id=reviewer_user.id,
                role_id=org_member_role.id,
            ))
            session.add(ProjectMembership(
                project_id=project.id,
                user_id=reviewer_user.id,
                role_id=reviewer_role.id,
            ))
            session.commit()

            rbac = RbacService(
                db_session=session,
                rbac_repository=RbacRepository(session),
                user_repository=UserRepository(session),
            )
            principal = AuthenticatedPrincipal(
                user=reviewer_user,
                session_family_id=uuid.uuid4(),
                roles=(RoleName.STANDARD_USER.value,),
                permissions=frozenset(),
            )

            p_ctx = rbac.resolve_project_context(project_id=project.id, principal=principal)

            # Assert permissions
            assert p_ctx.has_permission("project.invitations.manage") is False

            # Reviewer (rank 1) cannot assign Project Manager (rank 2)
            with pytest.raises(ForbiddenError) as exc_info:
                rbac.require_project_role_authority(
                    actor_role_name=reviewer_role.name,
                    target_role_name=RoleName.PROJECT_MANAGER.value,
                    actor_user_id=reviewer_user.id,
                    project_id=project.id,
                    organisation_id=org.id,
                    action_label="invite",
                )
            assert exc_info.value.code == "INSUFFICIENT_ROLE_AUTHORITY"


def test_org_owner_and_admin_have_project_invitation_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Org Owner and Org Admin possess project invitation permissions and role authority."""
    with isolated_auth_app(monkeypatch) as ctx:
        with ctx.session_factory() as session:
            creator = _create_user(session, "owner@test.com", "Org Owner")
            admin_user = _create_user(session, "admin@test.com", "Org Admin")
            org = _create_org(session, "Org One", "org-one", creator)
            project = _create_project(session, org, "Alpha Project", "alpha", creator)

            owner_role = _get_role(session, RoleName.ORG_OWNER.value)
            admin_role = _get_role(session, RoleName.ORG_ADMIN.value)

            session.add(OrganisationMembership(
                organisation_id=org.id,
                user_id=creator.id,
                role_id=owner_role.id,
            ))
            session.add(OrganisationMembership(
                organisation_id=org.id,
                user_id=admin_user.id,
                role_id=admin_role.id,
            ))
            session.commit()

            rbac = RbacService(
                db_session=session,
                rbac_repository=RbacRepository(session),
                user_repository=UserRepository(session),
            )

            # Check Org Owner context
            owner_principal = AuthenticatedPrincipal(
                user=creator,
                session_family_id=uuid.uuid4(),
                roles=(RoleName.STANDARD_USER.value,),
                permissions=frozenset(),
            )
            owner_p_ctx = rbac.resolve_project_context(project_id=project.id, principal=owner_principal)
            assert owner_p_ctx.has_permission("project.invitations.read") is True
            assert owner_p_ctx.has_permission("project.invitations.manage") is True

            # Org Owner can assign any project role
            rbac.require_project_role_authority(
                actor_role_name=owner_role.name,
                target_role_name=RoleName.PROJECT_MANAGER.value,
                actor_user_id=creator.id,
                project_id=project.id,
                organisation_id=org.id,
                action_label="invite",
            )

            # Check Org Admin context
            admin_principal = AuthenticatedPrincipal(
                user=admin_user,
                session_family_id=uuid.uuid4(),
                roles=(RoleName.STANDARD_USER.value,),
                permissions=frozenset(),
            )
            admin_p_ctx = rbac.resolve_project_context(project_id=project.id, principal=admin_principal)
            assert admin_p_ctx.has_permission("project.invitations.read") is True
            assert admin_p_ctx.has_permission("project.invitations.manage") is True

            # Org Admin can assign any project role
            rbac.require_project_role_authority(
                actor_role_name=admin_role.name,
                target_role_name=RoleName.PROJECT_MANAGER.value,
                actor_user_id=admin_user.id,
                project_id=project.id,
                organisation_id=org.id,
                action_label="invite",
            )
