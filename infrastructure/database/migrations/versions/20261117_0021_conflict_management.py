"""Conflict Management Workspace migration.

Revision ID: 0021_conflict_management
Revises: 0020_verification_rebuild
Create Date: 2026-11-17 19:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_conflict_management"
down_revision: str | None = "0020_verification_rebuild"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # 1. Allow nullable evidence references for claim A / claim B (e.g. cross-finding contradictions)
    op.alter_column("verification_conflicts", "claim_a_source_evidence_id", nullable=True)
    op.alter_column("verification_conflicts", "claim_b_source_evidence_id", nullable=True)

    # 2. Add assignment, priority, investigation notes and metadata
    op.add_column(
        "verification_conflicts",
        sa.Column("assigned_reviewer_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_verification_conflicts_assigned_reviewer",
        "verification_conflicts",
        "users",
        ["assigned_reviewer_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "verification_conflicts",
        sa.Column("priority", sa.String(length=32), server_default="medium", nullable=False),
    )

    op.add_column(
        "verification_conflicts",
        sa.Column("investigation_notes", sa.Text(), nullable=True),
    )

    op.add_column(
        "verification_conflicts",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.add_column(
        "verification_conflicts",
        sa.Column("related_finding_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_verification_conflicts_related_finding",
        "verification_conflicts",
        "verification_cases",
        ["related_finding_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "verification_conflicts",
        sa.Column("side_a_source_title", sa.Text(), nullable=True),
    )
    op.add_column(
        "verification_conflicts",
        sa.Column("side_a_provider", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "verification_conflicts",
        sa.Column("side_b_source_title", sa.Text(), nullable=True),
    )
    op.add_column(
        "verification_conflicts",
        sa.Column("side_b_provider", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "verification_conflicts",
        sa.Column("resolution_strategy", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "verification_conflicts",
        sa.Column("authoritative_claim_text", sa.Text(), nullable=True),
    )

    # 3. Create helpful indexes
    op.create_index(
        "ix_vc_conflicts_priority",
        "verification_conflicts",
        ["project_id", "priority"],
    )
    op.create_index(
        "ix_vc_conflicts_assigned",
        "verification_conflicts",
        ["project_id", "assigned_reviewer_id"],
    )
    op.create_index(
        "ix_vc_conflicts_status",
        "verification_conflicts",
        ["project_id", "resolution_state"],
    )


def downgrade() -> None:
    op.drop_index("ix_vc_conflicts_status", table_name="verification_conflicts")
    op.drop_index("ix_vc_conflicts_assigned", table_name="verification_conflicts")
    op.drop_index("ix_vc_conflicts_priority", table_name="verification_conflicts")

    op.drop_column("verification_conflicts", "authoritative_claim_text")
    op.drop_column("verification_conflicts", "resolution_strategy")
    op.drop_column("verification_conflicts", "side_b_provider")
    op.drop_column("verification_conflicts", "side_b_source_title")
    op.drop_column("verification_conflicts", "side_a_provider")
    op.drop_column("verification_conflicts", "side_a_source_title")

    op.drop_constraint("fk_verification_conflicts_related_finding", "verification_conflicts", type_="foreignkey")
    op.drop_column("verification_conflicts", "related_finding_id")

    op.drop_column("verification_conflicts", "updated_at")
    op.drop_column("verification_conflicts", "investigation_notes")
    op.drop_column("verification_conflicts", "priority")

    op.drop_constraint("fk_verification_conflicts_assigned_reviewer", "verification_conflicts", type_="foreignkey")
    op.drop_column("verification_conflicts", "assigned_reviewer_id")

    op.alter_column("verification_conflicts", "claim_b_source_evidence_id", nullable=False)
    op.alter_column("verification_conflicts", "claim_a_source_evidence_id", nullable=False)
