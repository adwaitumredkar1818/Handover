"""Add profile and preference columns to users table.

Revision ID: 20261121_0025
Revises: 20261119_0024
Create Date: 2026-11-21 07:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261121_0025"
down_revision = "20261119_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("job_title", sa.String(length=120), nullable=True))
    op.add_column("users", sa.Column("bio", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column("timezone", sa.String(length=64), server_default="UTC", nullable=False),
    )
    op.add_column("users", sa.Column("avatar_storage_key", sa.String(length=512), nullable=True))
    op.add_column("users", sa.Column("avatar_content_type", sa.String(length=64), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "preferences_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "preferences_json")
    op.drop_column("users", "avatar_content_type")
    op.drop_column("users", "avatar_storage_key")
    op.drop_column("users", "timezone")
    op.drop_column("users", "bio")
    op.drop_column("users", "job_title")
