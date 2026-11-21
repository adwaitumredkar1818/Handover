"""Focused tests for scoped Successor Handover Onboarding progress endpoints."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_principal, get_db_session
from app.core.rbac_catalog import deterministic_rbac_id
from app.services.auth import AuthenticatedPrincipal
from app.main import app
from app.models import Base
from app.models.enums import OrganisationStatus, ProjectStatus, RoleName, UserStatus
from app.models.organisation import Organisation, OrganisationMembership
from app.models.project import Project, ProjectMembership
from app.models.rbac import Permission, Role, RolePermission
from app.models.user import User


@pytest.fixture()
def onboarding_client() -> Generator[dict[str, object], None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_fk_pragma(dbapi_conn, _record) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with SessionLocal() as db:
        perm_read = Permission(
            id=deterministic_rbac_id("permission", "project.read"),
            code="project.read",
            name="Project Read",
            scope_type="project",
        )
        perm_manage = Permission(
            id=deterministic_rbac_id("permission", "project.manage"),
            code="project.manage",
            name="Project Manage",
            scope_type="project",
        )
        role_org_member = Role(
            id=deterministic_rbac_id("role", RoleName.ORG_MEMBER.value),
            name=RoleName.ORG_MEMBER.value,
            display_name="Org Member",
            description="Org Member",
            scope_type="organisation",
            is_system=True,
        )
        role_member = Role(
            id=deterministic_rbac_id("role", RoleName.PROJECT_MEMBER.value),
            name=RoleName.PROJECT_MEMBER.value,
            display_name="Project Member",
            description="Project Member",
            scope_type="project",
            is_system=True,
        )
        role_pm = Role(
            id=deterministic_rbac_id("role", RoleName.PROJECT_MANAGER.value),
            name=RoleName.PROJECT_MANAGER.value,
            display_name="Project Manager",
            description="Project Manager",
            scope_type="project",
            is_system=True,
        )
        db.add_all([perm_read, perm_manage, role_org_member, role_member, role_pm])
        db.flush()
        db.add_all(
            [
                RolePermission(role_id=role_member.id, permission_id=perm_read.id),
                RolePermission(role_id=role_pm.id, permission_id=perm_read.id),
                RolePermission(role_id=role_pm.id, permission_id=perm_manage.id),
            ]
        )

        succ_user = User(
            id=uuid.uuid4(),
            email="successor@example.com",
            full_name="Priya Nair",
            password_hash="x",
            status=UserStatus.ACTIVE,
            is_email_verified=True,
        )
        outsider_user = User(
            id=uuid.uuid4(),
            email="outsider@example.com",
            full_name="Outsider",
            password_hash="x",
            status=UserStatus.ACTIVE,
            is_email_verified=True,
        )
        db.add_all([succ_user, outsider_user])
        db.flush()

        org = Organisation(
            id=uuid.uuid4(),
            name="Onboarding Org",
            slug="onboarding-org",
            status=OrganisationStatus.ACTIVE,
            created_by_id=succ_user.id,
        )
        proj_a = Project(
            id=uuid.uuid4(),
            organisation_id=org.id,
            name="Project A",
            slug="project-a",
            status=ProjectStatus.ACTIVE,
            created_by_id=succ_user.id,
            owner_id=succ_user.id,
        )
        proj_b = Project(
            id=uuid.uuid4(),
            organisation_id=org.id,
            name="Project B",
            slug="project-b",
            status=ProjectStatus.ACTIVE,
            created_by_id=outsider_user.id,
            owner_id=outsider_user.id,
        )
        db.add_all([org, proj_a, proj_b])
        db.flush()

        db.add_all(
            [
                OrganisationMembership(
                    organisation_id=org.id,
                    user_id=succ_user.id,
                    role_id=role_org_member.id,
                    status="active",
                ),
                ProjectMembership(
                    project_id=proj_a.id,
                    user_id=succ_user.id,
                    role_id=role_member.id,
                    status="active",
                ),
                ProjectMembership(
                    project_id=proj_b.id,
                    user_id=outsider_user.id,
                    role_id=role_member.id,
                    status="active",
                ),
            ]
        )
        db.commit()

        active_user = {"user": succ_user}

        def _override_db() -> Generator[Session, None, None]:
            with SessionLocal() as s:
                yield s

        def _override_principal() -> AuthenticatedPrincipal:
            u = active_user["user"]
            return AuthenticatedPrincipal(
                user=u,  # type: ignore[arg-type]
                session_family_id=None,
                roles=(),
                permissions=frozenset(),
            )

        app.dependency_overrides[get_db_session] = _override_db
        app.dependency_overrides[get_current_principal] = _override_principal

        try:
            with TestClient(app) as client:
                yield {
                    "client": client,
                    "proj_a": proj_a,
                    "proj_b": proj_b,
                    "succ_user": succ_user,
                    "outsider_user": outsider_user,
                    "active_user": active_user,
                }
        finally:
            app.dependency_overrides.clear()


def test_onboarding_progress_scoped_by_case_version_and_isolated_cross_project(
    onboarding_client: dict[str, object],
) -> None:
    client: TestClient = onboarding_client["client"]  # type: ignore[assignment]
    proj_a: Project = onboarding_client["proj_a"]  # type: ignore[assignment]
    proj_b: Project = onboarding_client["proj_b"]  # type: ignore[assignment]

    case_1 = str(uuid.uuid4())
    ver_1 = str(uuid.uuid4())
    ver_2 = str(uuid.uuid4())

    # Initially 0 completed for case_1 / ver_1
    r0 = client.get(
        f"/api/v1/projects/{proj_a.id}/handover/onboarding/progress",
        params={"case_id": case_1, "version_id": ver_1},
    )
    assert r0.status_code == 200
    assert r0.json()["completed_steps"] == {}

    # Mark step 'welcome' complete on ver_1
    r1 = client.put(
        f"/api/v1/projects/{proj_a.id}/handover/onboarding/progress/welcome",
        params={"case_id": case_1, "version_id": ver_1},
        json={"is_completed": True},
    )
    assert r1.status_code == 200
    assert r1.json()["step_id"] == "welcome"
    assert r1.json()["is_completed"] is True
    assert r1.json()["completed_at"] is not None

    # ver_2 of same case still starts at 0 completed (preserves ver_1 history)
    r_v2 = client.get(
        f"/api/v1/projects/{proj_a.id}/handover/onboarding/progress",
        params={"case_id": case_1, "version_id": ver_2},
    )
    assert r_v2.status_code == 200
    assert r_v2.json()["completed_steps"] == {}

    # General orientation (no case_id/version_id) also stays separate
    r_gen = client.get(f"/api/v1/projects/{proj_a.id}/handover/onboarding/progress")
    assert r_gen.status_code == 200
    assert r_gen.json()["completed_steps"] == {}

    # ver_1 still retains 'welcome': True
    r_v1_again = client.get(
        f"/api/v1/projects/{proj_a.id}/handover/onboarding/progress",
        params={"case_id": case_1, "version_id": ver_1},
    )
    assert r_v1_again.status_code == 200
    assert r_v1_again.json()["completed_steps"] == {"welcome": True}

    # Toggle back to pending
    r_undo = client.put(
        f"/api/v1/projects/{proj_a.id}/handover/onboarding/progress/welcome",
        params={"case_id": case_1, "version_id": ver_1},
        json={"is_completed": False},
    )
    assert r_undo.status_code == 200
    assert r_undo.json()["is_completed"] is False

    # Cross-project access denied for proj_b where succ_user has no membership
    r_cross = client.get(f"/api/v1/projects/{proj_b.id}/handover/onboarding/progress")
    assert r_cross.status_code in (403, 404)
