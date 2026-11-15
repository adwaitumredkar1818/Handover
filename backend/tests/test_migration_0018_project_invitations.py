"""Automated unit and offline SQL generation contract tests for migration 0018 (Project Invitations)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from alembic import command
from alembic.config import Config

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _PROJECT_ROOT / "backend" / "alembic.ini"
_MIGRATION_PATH = (
    _PROJECT_ROOT
    / "infrastructure"
    / "database"
    / "migrations"
    / "versions"
    / "20261115_0018_project_invitations.py"
)


def _load_migration_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0018", _MIGRATION_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load migration module from {_MIGRATION_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_0018_metadata_and_revision_chain() -> None:
    """Verify revision chain, down_revision, and permission specs."""
    mod = _load_migration_module()
    assert mod.revision == "0018_project_invitations"
    assert mod.down_revision == "0017_password_reset_tokens"

    # Check permission specs
    perm_codes = {p[0] for p in mod._NEW_PERMISSIONS}
    assert "project.invitations.read" in perm_codes
    assert "project.invitations.manage" in perm_codes

    # Check role permission pairs
    pairs = set(mod._NEW_ROLE_PERMISSION_PAIRS)
    assert ("org_owner", "project.invitations.read") in pairs
    assert ("org_owner", "project.invitations.manage") in pairs
    assert ("org_admin", "project.invitations.read") in pairs
    assert ("org_admin", "project.invitations.manage") in pairs
    assert ("project_manager", "project.invitations.read") in pairs
    assert ("project_manager", "project.invitations.manage") in pairs

    # Ensure project_member and reviewer are NOT assigned manage permission
    assert ("project_member", "project.invitations.manage") not in pairs
    assert ("reviewer", "project.invitations.manage") not in pairs


def test_migration_0018_offline_sql_generation_contract(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify offline SQL generation produces expected DDL and reversible operations."""
    alembic_cfg = Config(str(_ALEMBIC_INI))

    # Capture upgrade --sql output
    command.upgrade(alembic_cfg, "0017_password_reset_tokens:0018_project_invitations", sql=True)
    captured_upgrade = capsys.readouterr()
    upgrade_sql = captured_upgrade.out

    assert "ALTER TABLE projects ADD CONSTRAINT uq_projects_id_organisation_id UNIQUE (id, organisation_id);" in upgrade_sql
    assert "ALTER TABLE organisation_invitations ADD COLUMN project_id UUID;" in upgrade_sql
    assert "ALTER TABLE organisation_invitations ADD COLUMN project_role_id UUID;" in upgrade_sql
    assert "fk_organisation_invitations_project_role_id" in upgrade_sql
    assert "fk_organisation_invitations_project_organisation" in upgrade_sql
    assert "uq_org_invitations_pending_org_email" in upgrade_sql
    assert "uq_project_invitations_pending_project_email" in upgrade_sql
    assert "ix_organisation_invitations_project_status" in upgrade_sql
    assert "project.invitations.read" in upgrade_sql
    assert "project.invitations.manage" in upgrade_sql

    # Capture downgrade --sql output
    command.downgrade(alembic_cfg, "0018_project_invitations:0017_password_reset_tokens", sql=True)
    captured_downgrade = capsys.readouterr()
    downgrade_sql = captured_downgrade.out

    assert "DELETE FROM role_permissions" in downgrade_sql
    assert "DELETE FROM permissions" in downgrade_sql
    assert "DROP INDEX ix_organisation_invitations_project_status;" in downgrade_sql
    assert "DROP INDEX uq_project_invitations_pending_project_email;" in downgrade_sql
    assert "ALTER TABLE organisation_invitations DROP COLUMN project_role_id;" in downgrade_sql
    assert "ALTER TABLE organisation_invitations DROP COLUMN project_id;" in downgrade_sql
    assert "ALTER TABLE projects DROP CONSTRAINT uq_projects_id_organisation_id;" in downgrade_sql
