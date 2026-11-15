"""Extend organisation invitations with project-level support and project invitation RBAC.

Revision ID: 0018_project_invitations
Revises: 0017_password_reset_tokens
Create Date: 2026-11-15 23:45:00.000000
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0018_project_invitations"
down_revision: str | None = "0017_password_reset_tokens"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_RBAC_UUID_NAMESPACE = uuid.UUID("6b7c84d4-2c1b-4c6f-9c2a-9a3e4f502100")


def _rbac_id(kind: str, key: str) -> uuid.UUID:
    return uuid.uuid5(_RBAC_UUID_NAMESPACE, f"{kind}:{key}")


_NEW_PERMISSIONS: tuple[tuple[str, str, str, str], ...] = (
    (
        "project.invitations.read",
        "Read Project Invitations",
        "List and inspect invitations issued for an assigned project.",
        "project",
    ),
    (
        "project.invitations.manage",
        "Manage Project Invitations",
        "Create, re-send, or revoke project-scoped invitations.",
        "project",
    ),
)

_NEW_ROLE_PERMISSION_PAIRS: tuple[tuple[str, str], ...] = (
    ("org_owner", "project.invitations.read"),
    ("org_owner", "project.invitations.manage"),
    ("org_admin", "project.invitations.read"),
    ("org_admin", "project.invitations.manage"),
    ("project_manager", "project.invitations.read"),
    ("project_manager", "project.invitations.manage"),
)


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    if is_postgres:
        op.execute("SET LOCAL lock_timeout = '2000ms';")
        op.execute("SET LOCAL statement_timeout = '30000ms';")

    # 1. UniqueConstraint on projects (id, organisation_id) for composite FK reference
    op.create_unique_constraint(
        "uq_projects_id_organisation_id",
        "projects",
        ["id", "organisation_id"],
    )

    # 2. Add nullable project_id and project_role_id columns to organisation_invitations
    op.add_column(
        "organisation_invitations",
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "organisation_invitations",
        sa.Column("project_role_id", sa.Uuid(as_uuid=True), nullable=True),
    )

    # 3. Add foreign key for project_role_id -> roles.id
    op.create_foreign_key(
        "fk_organisation_invitations_project_role_id",
        "organisation_invitations",
        "roles",
        ["project_role_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # 4. Add composite foreign key constraint for (project_id, organisation_id) -> projects(id, organisation_id)
    op.create_foreign_key(
        "fk_organisation_invitations_project_organisation",
        "organisation_invitations",
        "projects",
        ["project_id", "organisation_id"],
        ["id", "organisation_id"],
        ondelete="CASCADE",
    )

    # 5. Add check constraint enforcing that both project fields are either NULL or populated
    op.create_check_constraint(
        "organisation_invitation_project_fields_pair",
        "organisation_invitations",
        "(project_id IS NULL AND project_role_id IS NULL) "
        "OR (project_id IS NOT NULL AND project_role_id IS NOT NULL)",
    )

    # 6. Re-index pending invitations:
    # Drop existing org-level pending index
    op.drop_index(
        "uq_org_invitations_pending_org_email",
        table_name="organisation_invitations",
    )
    # Recreate org-level pending index with project_id IS NULL
    op.create_index(
        "uq_org_invitations_pending_org_email",
        "organisation_invitations",
        ["organisation_id", "email"],
        unique=True,
        postgresql_where=sa.text("status = 'pending' AND project_id IS NULL"),
        sqlite_where=sa.text("status = 'pending' AND project_id IS NULL"),
    )
    # Add project-level pending index with project_id IS NOT NULL
    op.create_index(
        "uq_project_invitations_pending_project_email",
        "organisation_invitations",
        ["project_id", "email"],
        unique=True,
        postgresql_where=sa.text("status = 'pending' AND project_id IS NOT NULL"),
        sqlite_where=sa.text("status = 'pending' AND project_id IS NOT NULL"),
    )
    # Additional query indexes
    op.create_index(
        "ix_organisation_invitations_project_id",
        "organisation_invitations",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_organisation_invitations_project_role_id",
        "organisation_invitations",
        ["project_role_id"],
        unique=False,
    )
    op.create_index(
        "ix_organisation_invitations_project_status",
        "organisation_invitations",
        ["project_id", "status"],
        unique=False,
    )

    # 7. Seed RBAC permissions and role mappings
    now = datetime.now(UTC)
    permissions_table = sa.table(
        "permissions",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("code", sa.String(128)),
        sa.column("name", sa.String(128)),
        sa.column("description", sa.Text()),
        sa.column("scope_type", sa.String(32)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    role_permissions_table = sa.table(
        "role_permissions",
        sa.column("role_id", sa.Uuid(as_uuid=True)),
        sa.column("permission_id", sa.Uuid(as_uuid=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )

    perm_rows = [
        {
            "id": _rbac_id("permission", code),
            "code": code,
            "name": name,
            "description": desc,
            "scope_type": scope,
            "created_at": now,
        }
        for code, name, desc, scope in _NEW_PERMISSIONS
    ]

    link_rows = [
        {
            "role_id": _rbac_id("role", r_name),
            "permission_id": _rbac_id("permission", p_code),
            "created_at": now,
        }
        for r_name, p_code in _NEW_ROLE_PERMISSION_PAIRS
    ]

    if is_postgres:
        from sqlalchemy.dialects import postgresql

        op.execute(
            postgresql.insert(permissions_table)
            .values(perm_rows)
            .on_conflict_do_nothing(index_elements=["code"])
        )
        op.execute(
            postgresql.insert(role_permissions_table)
            .values(link_rows)
            .on_conflict_do_nothing(index_elements=["role_id", "permission_id"])
        )
    else:
        op.bulk_insert(permissions_table, perm_rows)
        op.bulk_insert(role_permissions_table, link_rows)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    if is_postgres:
        op.execute("SET LOCAL lock_timeout = '2000ms';")
        op.execute("SET LOCAL statement_timeout = '30000ms';")

    # 1. Clean RBAC seed records
    role_permissions_table = sa.table(
        "role_permissions",
        sa.column("role_id", sa.Uuid(as_uuid=True)),
        sa.column("permission_id", sa.Uuid(as_uuid=True)),
    )
    permissions_table = sa.table(
        "permissions",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("code", sa.String(128)),
    )

    new_perm_ids = [_rbac_id("permission", code) for code, *_ in _NEW_PERMISSIONS]
    op.execute(
        role_permissions_table.delete().where(
            role_permissions_table.c.permission_id.in_(new_perm_ids)
        )
    )
    op.execute(
        permissions_table.delete().where(
            permissions_table.c.id.in_(new_perm_ids)
        )
    )

    # 2. Drop new indexes
    op.drop_index(
        "ix_organisation_invitations_project_status",
        table_name="organisation_invitations",
    )
    op.drop_index(
        "ix_organisation_invitations_project_role_id",
        table_name="organisation_invitations",
    )
    op.drop_index(
        "ix_organisation_invitations_project_id",
        table_name="organisation_invitations",
    )
    op.drop_index(
        "uq_project_invitations_pending_project_email",
        table_name="organisation_invitations",
    )
    op.drop_index(
        "uq_org_invitations_pending_org_email",
        table_name="organisation_invitations",
    )

    # 3. Recreate original organisation-level index
    op.create_index(
        "uq_org_invitations_pending_org_email",
        "organisation_invitations",
        ["organisation_id", "email"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )

    # 4. Drop check constraint and foreign keys
    op.drop_constraint(
        "organisation_invitation_project_fields_pair",
        "organisation_invitations",
        type_="check",
    )
    op.drop_constraint(
        "fk_organisation_invitations_project_organisation",
        "organisation_invitations",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_organisation_invitations_project_role_id",
        "organisation_invitations",
        type_="foreignkey",
    )

    # 5. Drop added columns
    op.drop_column("organisation_invitations", "project_role_id")
    op.drop_column("organisation_invitations", "project_id")

    # 6. Drop unique constraint on projects
    op.drop_constraint(
        "uq_projects_id_organisation_id",
        "projects",
        type_="unique",
    )
