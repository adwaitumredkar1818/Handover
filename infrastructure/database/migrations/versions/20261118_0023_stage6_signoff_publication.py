"""Stage 6 Signoff, Approval, Publication & Recipient Acknowledgement columns.

Revision ID: 0023_stage6_signoff_pub
Revises: 0022_stage5_checklists_resp
Create Date: 2026-11-18 03:02:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_stage6_signoff_pub"
down_revision: str | None = "0022_stage5_checklists_resp"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # 1. Dedicated assigned reviewer on handover_cases
    op.add_column(
        "handover_cases",
        sa.Column("assigned_reviewer_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_hc_assigned_reviewer",
        "handover_cases",
        "users",
        ["assigned_reviewer_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_hc_assigned_reviewer_id", "handover_cases", ["assigned_reviewer_id"])

    # 2. Package hash binding, affected sections & superseding flag on handover_signoffs
    op.add_column(
        "handover_signoffs",
        sa.Column("package_content_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "handover_signoffs",
        sa.Column(
            "affected_sections_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column(
        "handover_signoffs",
        sa.Column("is_superseded", sa.Boolean(), server_default="false", nullable=False),
    )

    # 3. Publication message & recipient clarification history on handover_deliveries
    op.add_column(
        "handover_deliveries",
        sa.Column("message", sa.Text(), nullable=True),
    )
    op.add_column(
        "handover_deliveries",
        sa.Column(
            "clarifications_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("handover_deliveries", "clarifications_json")
    op.drop_column("handover_deliveries", "message")
    op.drop_column("handover_signoffs", "is_superseded")
    op.drop_column("handover_signoffs", "affected_sections_json")
    op.drop_column("handover_signoffs", "package_content_hash")
    op.drop_index("ix_hc_assigned_reviewer_id", table_name="handover_cases")
    op.drop_constraint("fk_hc_assigned_reviewer", "handover_cases", type_="foreignkey")
    op.drop_column("handover_cases", "assigned_reviewer_id")
