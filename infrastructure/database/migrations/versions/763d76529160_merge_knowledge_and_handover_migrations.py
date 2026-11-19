"""merge_knowledge_and_handover_migrations

Revision ID: 763d76529160
Revises: 0021_relationship_types, 0023_stage6_signoff_pub
Create Date: 2026-11-18 21:41:04.444061
"""

from __future__ import annotations

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

revision = '763d76529160'
down_revision = ('0021_relationship_types', '0023_stage6_signoff_pub')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
