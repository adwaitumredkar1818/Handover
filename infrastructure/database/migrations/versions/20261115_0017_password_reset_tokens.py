"""create_password_reset_tokens_table

Revision ID: 0017_password_reset_tokens
Revises: 0016_rls_hardening
Create Date: 2026-11-15 03:25:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_password_reset_tokens"
down_revision: str | None = "0016_rls_hardening"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "request_metadata",
            sa.JSON(),
            nullable=True,
        ),
        sa.CheckConstraint(
            "length(token_hash) = 64",
            name="password_reset_token_hash_sha256_len",
        ),
    )
    op.create_index(
        "ix_password_reset_tokens_user_id",
        "password_reset_tokens",
        ["user_id"],
    )
    op.create_index(
        "ix_password_reset_tokens_token_hash",
        "password_reset_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_password_reset_tokens_expires_at",
        "password_reset_tokens",
        ["expires_at"],
    )
    op.create_index(
        "ix_password_reset_tokens_active",
        "password_reset_tokens",
        ["user_id", "used_at", "expires_at"],
    )

    # Enable Row Level Security consistent with 0016_rls_hardening
    op.execute("ALTER TABLE password_reset_tokens ENABLE ROW LEVEL SECURITY;")


def downgrade() -> None:
    op.drop_table("password_reset_tokens")
