"""Add project_onboarding_progress table for guided successor onboarding persistence.

Revision ID: 20261119_0024
Revises: 763d76529160
Create Date: 2026-11-19 23:35:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261119_0024"
down_revision = "763d76529160"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_onboarding_progress",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organisation_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("step_id", sa.String(length=64), nullable=False),
        sa.Column("is_completed", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "user_id", "step_id", name="uq_onboarding_proj_user_step"),
    )
    op.create_index(
        "ix_onboarding_progress_proj_user",
        "project_onboarding_progress",
        ["project_id", "user_id"],
        unique=False,
    )
    op.create_index(
        "ix_project_onboarding_progress_organisation_id",
        "project_onboarding_progress",
        ["organisation_id"],
        unique=False,
    )
    op.create_index(
        "ix_project_onboarding_progress_project_id",
        "project_onboarding_progress",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_project_onboarding_progress_user_id",
        "project_onboarding_progress",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_project_onboarding_progress_user_id", table_name="project_onboarding_progress")
    op.drop_index("ix_project_onboarding_progress_project_id", table_name="project_onboarding_progress")
    op.drop_index("ix_project_onboarding_progress_organisation_id", table_name="project_onboarding_progress")
    op.drop_index("ix_onboarding_progress_proj_user", table_name="project_onboarding_progress")
    op.drop_table("project_onboarding_progress")
