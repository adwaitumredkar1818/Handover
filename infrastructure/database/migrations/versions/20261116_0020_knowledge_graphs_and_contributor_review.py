"""Enable RLS on 0019 tables and add contributor identity review fields.

Revision ID: 0020_graphs_and_contributors
Revises: 0019_sources_and_evidence
Create Date: 2026-11-16 18:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_graphs_and_contributors"
down_revision: str | None = "0019_sources_and_evidence"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_RLS_TABLES_0019: tuple[str, ...] = (
    "notifications",
    "team_roster_members",
    "contribution_attributions",
)


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        # Execute RLS + additive contributor review schema changes in a single roundtrip.
        op.execute(
            """
            DO $$
            BEGIN
                ALTER TABLE public."notifications" ENABLE ROW LEVEL SECURITY;
                ALTER TABLE public."team_roster_members" ENABLE ROW LEVEL SECURITY;
                ALTER TABLE public."contribution_attributions"
                    ENABLE ROW LEVEL SECURITY,
                    ADD COLUMN IF NOT EXISTS contributor_type VARCHAR(32) NOT NULL DEFAULT 'unidentified',
                    ADD COLUMN IF NOT EXISTS review_status VARCHAR(32) NOT NULL DEFAULT 'pending',
                    ADD COLUMN IF NOT EXISTS reviewed_by_user_id UUID NULL,
                    ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ NULL,
                    ADD COLUMN IF NOT EXISTS review_notes TEXT NULL;

                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'fk_contribution_attributions_reviewed_by_user_id'
                ) THEN
                    ALTER TABLE public."contribution_attributions"
                        ADD CONSTRAINT fk_contribution_attributions_reviewed_by_user_id
                        FOREIGN KEY (reviewed_by_user_id) REFERENCES public."users"(id) ON DELETE SET NULL;
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'ck_contribution_attribution_contributor_type'
                ) THEN
                    ALTER TABLE public."contribution_attributions"
                        ADD CONSTRAINT ck_contribution_attribution_contributor_type
                        CHECK (contributor_type IN ('confirmed_member', 'external_contributor', 'unidentified', 'bot'));
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'ck_contribution_attribution_review_status'
                ) THEN
                    ALTER TABLE public."contribution_attributions"
                        ADD CONSTRAINT ck_contribution_attribution_review_status
                        CHECK (review_status IN ('pending', 'confirmed', 'marked_external', 'marked_bot', 'rejected', 'reverted'));
                END IF;

                CREATE INDEX IF NOT EXISTS ix_contribution_attributions_project_type_status
                    ON public."contribution_attributions" (project_id, contributor_type, review_status);
                CREATE INDEX IF NOT EXISTS ix_contribution_attributions_project_identifier
                    ON public."contribution_attributions" (project_id, contributor_identifier);

                ALTER TABLE public."knowledge_entities"
                    DROP CONSTRAINT IF EXISTS ck_knowledge_entities_ck_entity_type_valid;
                ALTER TABLE public."knowledge_entities"
                    ADD CONSTRAINT ck_knowledge_entities_ck_entity_type_valid
                    CHECK (entity_type IN (
                        'project', 'person', 'organisation', 'decision', 'requirement',
                        'task', 'feature', 'technical_component', 'architecture_component',
                        'technology', 'work_cluster', 'service', 'api', 'database',
                        'framework', 'library', 'repository', 'pull_request', 'commit',
                        'issue', 'document', 'risk', 'blocker', 'dependency', 'milestone',
                        'operational_procedure', 'team', 'discussion', 'discussion_thread',
                        'work_item', 'meeting_note', 'component', 'bug', 'procedure'
                    ));

                ALTER TABLE public."knowledge_relationships"
                    DROP CONSTRAINT IF EXISTS ck_relationship_type_valid;
                ALTER TABLE public."knowledge_relationships"
                    ADD CONSTRAINT ck_relationship_type_valid
                    CHECK (relationship_type IN (
                        'DECIDED_BY', 'INFLUENCED_BY', 'IMPLEMENTED_BY', 'SUPERSEDES',
                        'ARCHITECTURAL_DEPENDENCY', 'AFFECTS_COMPONENT', 'IMPLEMENTS', 'FIXES',
                        'PART_OF', 'BLOCKS', 'BLOCKED_BY', 'DEPENDS_ON', 'MERGED_IN',
                        'BRANCHED_FROM', 'OWNS', 'MAINTAINS', 'ASSIGNED_TO', 'AUTHORED_BY',
                        'REVIEWED_BY', 'REPORTED_BY', 'DISCUSSED_IN', 'DOCUMENTED_IN',
                        'REFERENCES', 'DERIVED_FROM', 'RESOLVED_BY', 'INTRODUCES_RISK',
                        'MITIGATES_RISK', 'CAUSED_BY', 'DECISION_REFERENCED_IN_DISCUSSION',
                        'DECISION_RECORDED_IN_DOCUMENT', 'DECISION_IMPLEMENTED_BY',
                        'DECISION_AFFECTS_COMPONENT', 'DECISION_SUPERSEDES', 'DECISION_CONFLICTS_WITH',
                        'WORK_ITEM_TRACKED_BY', 'WORK_ITEM_IMPLEMENTED_BY', 'WORK_ITEM_BLOCKED_BY',
                        'WORK_ITEM_DEPENDS_ON', 'WORK_ITEM_RELATED_TO', 'WORK_ITEM_ADDRESSED_BY_COMMIT',
                        'COMMIT_BELONGS_TO_PULL_REQUEST', 'PULL_REQUEST_REFERENCES_ISSUE',
                        'PULL_REQUEST_MODIFIES_COMPONENT', 'COMMIT_MODIFIES_COMPONENT',
                        'PULL_REQUEST_REVIEWED_BY', 'PULL_REQUEST_AUTHORED_BY', 'PERSON_AUTHORED',
                        'PERSON_REVIEWED', 'PERSON_ASSIGNED_TO', 'PERSON_RESPONSIBLE_FOR',
                        'PERSON_DISCUSSIONS_PARTICIPANT', 'PERSON_CONTRIBUTED_TO',
                        'COMPONENT_DEPENDS_ON', 'COMPONENT_CALLS_COMPONENT', 'COMPONENT_USES_SERVICE',
                        'COMPONENT_STORES_DATA_IN', 'COMPONENT_EXPOSES_API',
                        'DOCUMENT_DESCRIBES_COMPONENT', 'DOCUMENT_DESCRIBES_DECISION',
                        'RISK_AFFECTS_COMPONENT', 'BUG_FOUND_IN_COMPONENT', 'RISK_BLOCKS_WORK_ITEM',
                        'BUG_RELATED_TO_WORK_ITEM', 'RISK_DEPENDS_ON_EXTERNAL_FACTOR',
                        'KNOWLEDGE_SUPPORTED_BY_EVIDENCE', 'KNOWLEDGE_CORROBORATED_BY',
                        'DOCUMENT_REFERENCES_EVIDENCE', 'DISCUSSION_REFERENCES_WORK_ITEM',
                        'proposed_by', 'approved_by', 'motivated_by', 'contradicts', 'revises',
                        'requires', 'uses', 'integrates_with', 'extends', 'replaces',
                        'deployed_as', 'configured_by', 'supported_by', 'mentioned_in',
                        'corroborated_by', 'conflicts_with', 'belongs_to', 'completed_in',
                        'USES_TECHNOLOGY', 'CONFIGURED_IN', 'CALLS', 'READS_FROM', 'WRITES_TO',
                        'STORES_IN', 'AUTHENTICATES_WITH', 'USES_MODEL', 'HAS_REQUIREMENT',
                        'TRACKED_BY', 'USES_COMPONENT', 'HAS_WORKFLOW_STEP', 'TESTED_BY',
                        'BELONGS_TO_WORK_CLUSTER', 'CONTRIBUTED_TO', 'MODIFIED',
                        'CONTAINS_COMMIT', 'RESPONSIBLE_FOR'
                    ));
            END
            $$;
            """
        )
        return

    # SQLite / non-PostgreSQL path (used by unit tests)
    op.add_column(
        "contribution_attributions",
        sa.Column(
            "contributor_type",
            sa.String(length=32),
            server_default="unidentified",
            nullable=False,
        ),
    )
    op.add_column(
        "contribution_attributions",
        sa.Column(
            "review_status",
            sa.String(length=32),
            server_default="pending",
            nullable=False,
        ),
    )
    op.add_column(
        "contribution_attributions",
        sa.Column("reviewed_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "contribution_attributions",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "contribution_attributions",
        sa.Column("review_notes", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_contribution_attributions_reviewed_by_user_id",
        "contribution_attributions",
        "users",
        ["reviewed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_contribution_attribution_contributor_type",
        "contribution_attributions",
        "contributor_type IN ('confirmed_member', 'external_contributor', 'unidentified', 'bot')",
    )
    op.create_check_constraint(
        "ck_contribution_attribution_review_status",
        "contribution_attributions",
        "review_status IN ('pending', 'confirmed', 'marked_external', 'marked_bot', 'rejected', 'reverted')",
    )
    op.create_index(
        "ix_contribution_attributions_project_type_status",
        "contribution_attributions",
        ["project_id", "contributor_type", "review_status"],
    )
    op.create_index(
        "ix_contribution_attributions_project_identifier",
        "contribution_attributions",
        ["project_id", "contributor_identifier"],
    )


def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        op.execute(
            """
            DO $$
            BEGIN
                DROP INDEX IF EXISTS ix_contribution_attributions_project_identifier;
                DROP INDEX IF EXISTS ix_contribution_attributions_project_type_status;
                ALTER TABLE public."contribution_attributions"
                    DROP CONSTRAINT IF EXISTS ck_contribution_attribution_review_status,
                    DROP CONSTRAINT IF EXISTS ck_contribution_attribution_contributor_type,
                    DROP CONSTRAINT IF EXISTS fk_contribution_attributions_reviewed_by_user_id,
                    DROP COLUMN IF EXISTS review_notes,
                    DROP COLUMN IF EXISTS reviewed_at,
                    DROP COLUMN IF EXISTS reviewed_by_user_id,
                    DROP COLUMN IF EXISTS review_status,
                    DROP COLUMN IF EXISTS contributor_type;
                ALTER TABLE public."notifications" DISABLE ROW LEVEL SECURITY;
                ALTER TABLE public."team_roster_members" DISABLE ROW LEVEL SECURITY;
                ALTER TABLE public."contribution_attributions" DISABLE ROW LEVEL SECURITY;
            END
            $$;
            """
        )
        return

    op.drop_index(
        "ix_contribution_attributions_project_identifier",
        table_name="contribution_attributions",
    )
    op.drop_index(
        "ix_contribution_attributions_project_type_status",
        table_name="contribution_attributions",
    )
    op.drop_constraint(
        "ck_contribution_attribution_review_status",
        "contribution_attributions",
        type_="check",
    )
    op.drop_constraint(
        "ck_contribution_attribution_contributor_type",
        "contribution_attributions",
        type_="check",
    )
    op.drop_constraint(
        "fk_contribution_attributions_reviewed_by_user_id",
        "contribution_attributions",
        type_="foreignkey",
    )
    op.drop_column("contribution_attributions", "review_notes")
    op.drop_column("contribution_attributions", "reviewed_at")
    op.drop_column("contribution_attributions", "reviewed_by_user_id")
    op.drop_column("contribution_attributions", "review_status")
    op.drop_column("contribution_attributions", "contributor_type")

    if bind.dialect.name == "postgresql":
        for table in _RLS_TABLES_0019:
            op.execute(f'ALTER TABLE public."{table}" DISABLE ROW LEVEL SECURITY;')
