"""Stage 5 Transition Checklists & Responsibility Transfer columns.

Revision ID: 0022_stage5_checklists_resp
Revises: 0021_conflict_management
Create Date: 2026-11-18 02:26:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_stage5_checklists_resp"
down_revision: str | None = "0021_conflict_management"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # 1. Enrich handover_checklist_items for Stage 5 checklist lifecycle, review & reopening
    op.add_column("handover_checklist_items", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "handover_checklist_items", sa.Column("completion_criteria", sa.Text(), nullable=True)
    )
    op.add_column(
        "handover_checklist_items",
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "handover_checklist_items", sa.Column("evidence_item_id", sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        "fk_hcli_evidence_item",
        "handover_checklist_items",
        "evidence_items",
        ["evidence_item_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_hcli_evidence_item_id", "handover_checklist_items", ["evidence_item_id"])

    op.add_column(
        "handover_checklist_items", sa.Column("reviewed_by_user_id", sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        "fk_hcli_reviewed_by_user",
        "handover_checklist_items",
        "users",
        ["reviewed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_hcli_reviewed_by_user_id", "handover_checklist_items", ["reviewed_by_user_id"]
    )
    op.add_column(
        "handover_checklist_items",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("handover_checklist_items", sa.Column("review_notes", sa.Text(), nullable=True))

    op.add_column(
        "handover_checklist_items",
        sa.Column("reopened_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "handover_checklist_items", sa.Column("reopened_by_user_id", sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        "fk_hcli_reopened_by_user",
        "handover_checklist_items",
        "users",
        ["reopened_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "handover_checklist_items",
        sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "handover_checklist_items", sa.Column("reopened_reason", sa.Text(), nullable=True)
    )
    op.add_column(
        "handover_checklist_items",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )

    # 2. Enrich handover_responsibility_transfers for Stage 5 transfer governance
    op.add_column(
        "handover_responsibility_transfers",
        sa.Column("title", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "handover_responsibility_transfers",
        sa.Column("component_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "handover_responsibility_transfers",
        sa.Column("priority", sa.String(length=16), server_default="medium", nullable=False),
    )
    op.add_column(
        "handover_responsibility_transfers",
        sa.Column(
            "ownership_certainty", sa.String(length=32), server_default="proposed", nullable=False
        ),
    )
    op.add_column(
        "handover_responsibility_transfers",
        sa.Column("operational_context", sa.Text(), nullable=True),
    )
    op.add_column(
        "handover_responsibility_transfers",
        sa.Column("required_access", sa.Text(), nullable=True),
    )
    op.add_column(
        "handover_responsibility_transfers",
        sa.Column("effective_transfer_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "handover_responsibility_transfers",
        sa.Column("blocker_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "handover_responsibility_transfers",
        sa.Column("related_knowledge_item_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_hrt_related_knowledge_item",
        "handover_responsibility_transfers",
        "knowledge_items",
        ["related_knowledge_item_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_hrt_related_knowledge_item_id",
        "handover_responsibility_transfers",
        ["related_knowledge_item_id"],
    )

    op.add_column(
        "handover_responsibility_transfers",
        sa.Column("outgoing_confirmed_by_user_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_hrt_outgoing_confirmed_by",
        "handover_responsibility_transfers",
        "users",
        ["outgoing_confirmed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "handover_responsibility_transfers",
        sa.Column("outgoing_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "handover_responsibility_transfers",
        sa.Column("outgoing_confirmation_notes", sa.Text(), nullable=True),
    )

    op.add_column(
        "handover_responsibility_transfers",
        sa.Column("successor_acknowledged_by_user_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_hrt_successor_acknowledged_by",
        "handover_responsibility_transfers",
        "users",
        ["successor_acknowledged_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "handover_responsibility_transfers",
        sa.Column("successor_acknowledged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "handover_responsibility_transfers",
        sa.Column("successor_acknowledgement_notes", sa.Text(), nullable=True),
    )

    op.add_column(
        "handover_responsibility_transfers",
        sa.Column("clarification_requested_by_user_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_hrt_clarification_requested_by",
        "handover_responsibility_transfers",
        "users",
        ["clarification_requested_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "handover_responsibility_transfers",
        sa.Column("clarification_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "handover_responsibility_transfers",
        sa.Column("clarification_request_notes", sa.Text(), nullable=True),
    )
    op.add_column(
        "handover_responsibility_transfers",
        sa.Column("clarification_response_notes", sa.Text(), nullable=True),
    )

    op.add_column(
        "handover_responsibility_transfers",
        sa.Column("reopened_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "handover_responsibility_transfers",
        sa.Column("reopened_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "handover_responsibility_transfers",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )


def downgrade() -> None:
    # Drop handover_responsibility_transfers Stage 5 columns
    op.drop_column("handover_responsibility_transfers", "version")
    op.drop_column("handover_responsibility_transfers", "reopened_reason")
    op.drop_column("handover_responsibility_transfers", "reopened_count")
    op.drop_column("handover_responsibility_transfers", "clarification_response_notes")
    op.drop_column("handover_responsibility_transfers", "clarification_request_notes")
    op.drop_column("handover_responsibility_transfers", "clarification_requested_at")
    op.drop_constraint(
        "fk_hrt_clarification_requested_by",
        "handover_responsibility_transfers",
        type_="foreignkey",
    )
    op.drop_column("handover_responsibility_transfers", "clarification_requested_by_user_id")
    op.drop_column("handover_responsibility_transfers", "successor_acknowledgement_notes")
    op.drop_column("handover_responsibility_transfers", "successor_acknowledged_at")
    op.drop_constraint(
        "fk_hrt_successor_acknowledged_by",
        "handover_responsibility_transfers",
        type_="foreignkey",
    )
    op.drop_column("handover_responsibility_transfers", "successor_acknowledged_by_user_id")
    op.drop_column("handover_responsibility_transfers", "outgoing_confirmation_notes")
    op.drop_column("handover_responsibility_transfers", "outgoing_confirmed_at")
    op.drop_constraint(
        "fk_hrt_outgoing_confirmed_by",
        "handover_responsibility_transfers",
        type_="foreignkey",
    )
    op.drop_column("handover_responsibility_transfers", "outgoing_confirmed_by_user_id")
    op.drop_index("ix_hrt_related_knowledge_item_id", table_name="handover_responsibility_transfers")
    op.drop_constraint(
        "fk_hrt_related_knowledge_item",
        "handover_responsibility_transfers",
        type_="foreignkey",
    )
    op.drop_column("handover_responsibility_transfers", "related_knowledge_item_id")
    op.drop_column("handover_responsibility_transfers", "blocker_reason")
    op.drop_column("handover_responsibility_transfers", "effective_transfer_date")
    op.drop_column("handover_responsibility_transfers", "required_access")
    op.drop_column("handover_responsibility_transfers", "operational_context")
    op.drop_column("handover_responsibility_transfers", "ownership_certainty")
    op.drop_column("handover_responsibility_transfers", "priority")
    op.drop_column("handover_responsibility_transfers", "component_name")
    op.drop_column("handover_responsibility_transfers", "title")

    # Drop handover_checklist_items Stage 5 columns
    op.drop_column("handover_checklist_items", "version")
    op.drop_column("handover_checklist_items", "reopened_reason")
    op.drop_column("handover_checklist_items", "reopened_at")
    op.drop_constraint("fk_hcli_reopened_by_user", "handover_checklist_items", type_="foreignkey")
    op.drop_column("handover_checklist_items", "reopened_by_user_id")
    op.drop_column("handover_checklist_items", "reopened_count")
    op.drop_column("handover_checklist_items", "review_notes")
    op.drop_column("handover_checklist_items", "reviewed_at")
    op.drop_index("ix_hcli_reviewed_by_user_id", table_name="handover_checklist_items")
    op.drop_constraint("fk_hcli_reviewed_by_user", "handover_checklist_items", type_="foreignkey")
    op.drop_column("handover_checklist_items", "reviewed_by_user_id")
    op.drop_index("ix_hcli_evidence_item_id", table_name="handover_checklist_items")
    op.drop_constraint("fk_hcli_evidence_item", "handover_checklist_items", type_="foreignkey")
    op.drop_column("handover_checklist_items", "evidence_item_id")
    op.drop_column("handover_checklist_items", "due_date")
    op.drop_column("handover_checklist_items", "completion_criteria")
    op.drop_column("handover_checklist_items", "description")
