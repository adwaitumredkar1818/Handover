"""Add Slack to integrations, document categories, notifications, roster and attributions.

Revision ID: 0019_sources_and_evidence
Revises: 0018_project_invitations
Create Date: 2026-11-16 09:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_sources_and_evidence"
down_revision: str | None = "0018_project_invitations"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # 1. Update source_connections check constraint for Slack
    op.drop_constraint("source_connection_provider", "source_connections", type_="check")
    op.create_check_constraint(
        "source_connection_provider",
        "source_connections",
        "provider IN ('github', 'jira', 'slack')",
    )

    # 2. Update user_source_authorisations check constraint for Slack
    op.drop_constraint("user_source_auth_provider", "user_source_authorisations", type_="check")
    op.create_check_constraint(
        "user_source_auth_provider",
        "user_source_authorisations",
        "provider IN ('github', 'jira', 'slack')",
    )

    # 3. Update oauth_states check constraint for Slack
    op.drop_constraint("oauth_state_provider", "oauth_states", type_="check")
    op.create_check_constraint(
        "oauth_state_provider",
        "oauth_states",
        "provider IN ('github', 'jira', 'slack')",
    )

    # 4. Update source_access_policies check constraint for Slack
    op.drop_constraint("source_access_policy_provider", "source_access_policies", type_="check")
    op.create_check_constraint(
        "source_access_policy_provider",
        "source_access_policies",
        "provider IN ('github', 'jira', 'slack')",
    )

    # 5. Update project_source_mappings check constraints for Slack and slack_channel
    op.drop_constraint("project_source_mapping_provider", "project_source_mappings", type_="check")
    op.create_check_constraint(
        "project_source_mapping_provider",
        "project_source_mappings",
        "provider IN ('github', 'jira', 'slack')",
    )
    op.drop_constraint(
        "project_source_mapping_resource_type", "project_source_mappings", type_="check"
    )
    op.create_check_constraint(
        "project_source_mapping_resource_type",
        "project_source_mappings",
        "resource_type IN ('github_repository', 'jira_project', 'slack_channel')",
    )

    # 6. Update source_sync_runs check constraint for Slack
    op.drop_constraint("source_sync_run_provider", "source_sync_runs", type_="check")
    op.create_check_constraint(
        "source_sync_run_provider",
        "source_sync_runs",
        "provider IN ('github', 'jira', 'slack')",
    )

    # 7. Update evidence_items category check constraint
    op.drop_constraint("evidence_category", "evidence_items", type_="check")
    op.create_check_constraint(
        "evidence_category",
        "evidence_items",
        "category IN ("
        "'pdf_document', 'docx_document', 'issue', 'pull_request', "
        "'commit', 'discussion_thread', 'design_document', "
        "'team_roster', 'meeting_notes', 'project_document', 'source_code', 'other'"
        ")",
    )

    # 8. Add document_category and document_subtype to evidence_items
    op.add_column("evidence_items", sa.Column("document_category", sa.String(length=64), nullable=True))
    op.add_column("evidence_items", sa.Column("document_subtype", sa.String(length=64), nullable=True))

    # 9. Create notifications table
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("organisation_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("notification_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=32), server_default="info", nullable=False),
        sa.Column("is_read", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'success', 'warning', 'error')",
            name="notification_severity_check",
        ),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notifications_user_read_created",
        "notifications",
        ["user_id", "is_read", "created_at"],
    )
    op.create_index("ix_notifications_project_created", "notifications", ["project_id", "created_at"])
    op.create_index("ix_notifications_organisation_id", "notifications", ["organisation_id"])

    # 10. Create team_roster_members table
    op.create_table(
        "team_roster_members",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("evidence_item_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("member_id_in_roster", sa.String(length=64), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("role_name", sa.String(length=128), nullable=True),
        sa.Column(
            "primary_responsibilities",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "component_ownership",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("github_username", sa.String(length=128), nullable=True),
        sa.Column("git_commit_email", sa.String(length=255), nullable=True),
        sa.Column("jira_account_id", sa.String(length=128), nullable=True),
        sa.Column("slack_user_id", sa.String(length=128), nullable=True),
        sa.Column(
            "reconciliation_status",
            sa.String(length=32),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("matched_project_membership_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("reconciliation_confidence", sa.Float(), nullable=True),
        sa.Column("reconciliation_notes", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "reconciliation_status IN ("
            "'pending', 'matched', 'possible_match', 'new_candidate', "
            "'ambiguous', 'conflict', 'rejected'"
            ")",
            name="team_roster_member_reconciliation_status",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_item_id"], ["evidence_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["matched_project_membership_id"], ["project_memberships.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_team_roster_project_evidence", "team_roster_members", ["project_id", "evidence_item_id"]
    )
    op.create_index(
        "ix_team_roster_status", "team_roster_members", ["project_id", "reconciliation_status"]
    )

    # 11. Create contribution_attributions table
    op.create_table(
        "contribution_attributions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("evidence_item_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("contributor_identifier", sa.String(length=255), nullable=False),
        sa.Column("identifier_type", sa.String(length=32), nullable=False),
        sa.Column("matched_roster_member_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("matched_project_membership_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("match_method", sa.String(length=64), nullable=True),
        sa.Column("match_confidence", sa.Float(), nullable=True),
        sa.Column("contribution_category", sa.String(length=64), nullable=True),
        sa.Column("responsibility_alignment", sa.String(length=64), nullable=True),
        sa.Column("alignment_explanation", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_item_id"], ["evidence_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["matched_roster_member_id"], ["team_roster_members.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["matched_project_membership_id"], ["project_memberships.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_contribution_attributions_project", "contribution_attributions", ["project_id"]
    )
    op.create_index(
        "ix_contribution_attributions_evidence", "contribution_attributions", ["evidence_item_id"]
    )


def downgrade() -> None:
    op.drop_table("contribution_attributions")
    op.drop_table("team_roster_members")
    op.drop_table("notifications")
    op.drop_column("evidence_items", "document_subtype")
    op.drop_column("evidence_items", "document_category")

    op.drop_constraint("evidence_category", "evidence_items", type_="check")
    op.create_check_constraint(
        "evidence_category",
        "evidence_items",
        "category IN ("
        "'pdf_document', 'docx_document', 'issue', 'pull_request', "
        "'commit', 'discussion_thread', 'design_document', 'other'"
        ")",
    )

    op.drop_constraint("source_sync_run_provider", "source_sync_runs", type_="check")
    op.create_check_constraint(
        "source_sync_run_provider",
        "source_sync_runs",
        "provider IN ('github', 'jira')",
    )

    op.drop_constraint(
        "project_source_mapping_resource_type", "project_source_mappings", type_="check"
    )
    op.create_check_constraint(
        "project_source_mapping_resource_type",
        "project_source_mappings",
        "resource_type IN ('github_repository', 'jira_project')",
    )
    op.drop_constraint("project_source_mapping_provider", "project_source_mappings", type_="check")
    op.create_check_constraint(
        "project_source_mapping_provider",
        "project_source_mappings",
        "provider IN ('github', 'jira')",
    )

    op.drop_constraint("source_access_policy_provider", "source_access_policies", type_="check")
    op.create_check_constraint(
        "source_access_policy_provider",
        "source_access_policies",
        "provider IN ('github', 'jira')",
    )

    op.drop_constraint("oauth_state_provider", "oauth_states", type_="check")
    op.create_check_constraint(
        "oauth_state_provider",
        "oauth_states",
        "provider IN ('github', 'jira')",
    )

    op.drop_constraint("user_source_auth_provider", "user_source_authorisations", type_="check")
    op.create_check_constraint(
        "user_source_auth_provider",
        "user_source_authorisations",
        "provider IN ('github', 'jira')",
    )

    op.drop_constraint("source_connection_provider", "source_connections", type_="check")
    op.create_check_constraint(
        "source_connection_provider",
        "source_connections",
        "provider IN ('github', 'jira')",
    )
