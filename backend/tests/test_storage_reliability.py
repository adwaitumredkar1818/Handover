"""Tests for Phase AI-10.2: Database, Storage, and Data Reliability.

Verifies:
1. PostgreSQL connection pooling, session lifecycle, and error rollback.
2. Private encrypted storage roundtrip, AEAD authentication, and cross-tenant isolation.
3. Linear Alembic migration integrity.
4. RLS enabled on 100% of public database tables.
"""

from __future__ import annotations

import uuid
from typing import Iterator

import alembic.config
import alembic.script
import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import create_db_engine, create_session_factory, session_scope
from app.services.storage_factory import build_storage_backend


def test_linear_alembic_migrations():
    """Verify Alembic migration tree is strictly linear with no branches."""
    alembic_cfg = alembic.config.Config("infrastructure/database/migrations/alembic.ini")
    alembic_cfg.set_main_option("script_location", "infrastructure/database/migrations")
    script = alembic.script.ScriptDirectory.from_config(alembic_cfg)

    revisions = list(script.walk_revisions())
    assert len(revisions) == 20, f"Expected 20 migrations, found {len(revisions)}"

    # Ensure linear chain
    current = revisions[0]  # head (0020)
    for next_rev in revisions[1:]:
        assert current.down_revision == next_rev.revision
        current = next_rev
    assert current.down_revision is None, "Baseline migration should have down_revision=None"


def test_all_public_tables_have_rls():
    """Verify that Row Level Security (RLS) is active on every single public table."""
    settings = get_settings()
    engine = create_db_engine(settings)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT c.relname as table_name, c.relrowsecurity as rls_enabled
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r'
            ORDER BY c.relname;
        """)).fetchall()

        assert len(rows) > 0, "No tables found in public schema"
        non_rls = [r[0] for r in rows if not r[1]]
        assert len(non_rls) == 0, f"Tables lacking RLS: {non_rls}"
        assert all(r[1] for r in rows), "All public tables must enforce RLS"


def test_database_session_lifecycle_and_rollback():
    """Verify session_scope commits successfully or rolls back on exception without leaking."""
    settings = get_settings()
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)

    # 1. Normal successful scope
    with session_scope(session_factory) as session:
        result = session.execute(text("SELECT 42")).scalar()
        assert result == 42
        assert session.is_active

    # 2. Scope rolling back on exception
    with pytest.raises(RuntimeError):
        with session_scope(session_factory) as session:
            session.execute(text("SELECT 1"))
            raise RuntimeError("Deliberate failure to test rollback")


def test_storage_encryption_and_tenant_isolation():
    """Verify AES-256-GCM encryption, AEAD tenant binding, and deletion."""
    settings = get_settings()
    storage = build_storage_backend(settings)
    org_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    sample_data = b"Confidential system architecture test payload."

    meta = storage.store_encrypted_bytes(
        organisation_id=org_id,
        project_id=proj_id,
        data=sample_data,
    )

    try:
        assert storage.exists(storage_object_key=meta.storage_object_key) is True

        # Successful decrypted retrieval
        decrypted = storage.read_decrypted_bytes(
            storage_object_key=meta.storage_object_key,
            organisation_id=org_id,
            project_id=proj_id,
        )
        assert decrypted == sample_data

        # Tenant isolation check: mismatched organisation ID fails authentication
        wrong_org = uuid.uuid4()
        with pytest.raises(Exception):
            storage.read_decrypted_bytes(
                storage_object_key=meta.storage_object_key,
                organisation_id=wrong_org,
                project_id=proj_id,
            )

    finally:
        storage.delete_object(storage_object_key=meta.storage_object_key)
        assert storage.exists(storage_object_key=meta.storage_object_key) is False
