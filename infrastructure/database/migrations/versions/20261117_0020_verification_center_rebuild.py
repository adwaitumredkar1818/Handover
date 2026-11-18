"""Additive schema rebuild for Verification Center Phase 1.

Revision ID: 0020_verification_rebuild
Revises: 0019_sources_and_evidence
Create Date: 2026-11-17 02:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_verification_rebuild"
down_revision: str | None = "0019_sources_and_evidence"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # 1. Extend verification_cases with canonical claim, provenance, and uncertainty fields
    op.add_column(
        "verification_cases",
        sa.Column("domain", sa.String(length=64), server_default="general", nullable=False),
    )
    op.add_column(
        "verification_cases",
        sa.Column("title", sa.String(length=512), server_default="", nullable=False),
    )
    op.add_column(
        "verification_cases",
        sa.Column("original_ai_claim", sa.Text(), server_default="", nullable=False),
    )
    op.add_column(
        "verification_cases",
        sa.Column("current_claim", sa.Text(), server_default="", nullable=False),
    )
    op.add_column(
        "verification_cases",
        sa.Column("person_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "verification_cases",
        sa.Column("source_provider", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "verification_cases",
        sa.Column("model_confidence", sa.Float(), nullable=True),
    )
    op.add_column(
        "verification_cases",
        sa.Column("uncertainty_note", sa.Text(), nullable=True),
    )
    op.add_column(
        "verification_cases",
        sa.Column("evidence_completeness", sa.String(length=32), nullable=True),
    )

    # 2. Extend verification_issues with the 6 canonical PDF review categories
    op.add_column(
        "verification_issues",
        sa.Column(
            "verification_category",
            sa.String(length=64),
            server_default="extracted_finding_verification",
            nullable=False,
        ),
    )

    # 3. Extend verification_review_events with case_version and decision_reason
    op.add_column(
        "verification_review_events",
        sa.Column("case_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "verification_review_events",
        sa.Column("decision_reason", sa.Text(), nullable=True),
    )

    # 4. Create verification_evidence_refs
    op.create_table(
        "verification_evidence_refs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organisation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organisations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("verification_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "evidence_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evidence_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "evidence_chunk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evidence_chunks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "relationship_to_finding",
            sa.String(length=32),
            server_default="supports",
            nullable=False,
        ),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("location_label", sa.String(length=255), nullable=True),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_ver_case_evidence",
        "verification_evidence_refs",
        ["case_id", "evidence_item_id"],
    )
    op.create_index(
        "ix_ver_project_rel",
        "verification_evidence_refs",
        ["project_id", "relationship_to_finding"],
    )

    # 5. Create verification_finding_revisions
    op.create_table(
        "verification_finding_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organisation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organisations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("verification_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(length=64), nullable=False),
        sa.Column(
            "is_ai_original",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "edited_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("edit_reason", sa.Text(), nullable=True),
        sa.Column(
            "evidence_snapshot_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_vfr_case_rev",
        "verification_finding_revisions",
        ["case_id", "revision_number"],
    )


def downgrade() -> None:
    op.drop_index("ix_vfr_case_rev", table_name="verification_finding_revisions")
    op.drop_table("verification_finding_revisions")

    op.drop_index("ix_ver_project_rel", table_name="verification_evidence_refs")
    op.drop_index("ix_ver_case_evidence", table_name="verification_evidence_refs")
    op.drop_table("verification_evidence_refs")

    op.drop_column("verification_review_events", "decision_reason")
    op.drop_column("verification_review_events", "case_version")

    op.drop_column("verification_issues", "verification_category")

    op.drop_column("verification_cases", "evidence_completeness")
    op.drop_column("verification_cases", "uncertainty_note")
    op.drop_column("verification_cases", "model_confidence")
    op.drop_column("verification_cases", "source_provider")
    op.drop_column("verification_cases", "person_name")
    op.drop_column("verification_cases", "current_claim")
    op.drop_column("verification_cases", "original_ai_claim")
    op.drop_column("verification_cases", "title")
    op.drop_column("verification_cases", "domain")
