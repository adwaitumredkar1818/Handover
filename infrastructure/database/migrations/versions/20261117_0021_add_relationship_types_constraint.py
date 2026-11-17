"""Update ck_relationship_type_valid check constraint with all canonical RelationshipType values.

Revision ID: 0021_relationship_types
Revises: 0020_graphs_and_contributors
Create Date: 2026-11-17 06:45:00.000000
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

# Ensure backend root is on sys.path so app models can be safely imported
_backend_path = Path(__file__).resolve().parents[4] / "backend"
if str(_backend_path) not in sys.path:
    sys.path.insert(0, str(_backend_path))

try:
    from app.models.enums import RelationshipType
    _ENUM_TYPES = [rt.value for rt in RelationshipType]
    _LOWER_TYPES = [rt.value.lower() for rt in RelationshipType]
    _UPPER_TYPES = [rt.value.upper() for rt in RelationshipType]
except Exception:
    _ENUM_TYPES = []
    _LOWER_TYPES = []
    _UPPER_TYPES = []

revision: str = "0021_relationship_types"
down_revision: str | None = "0020_graphs_and_contributors"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_VERBOSE_TYPES = [
    "DECISION_REFERENCED_IN_DISCUSSION", "DECISION_RECORDED_IN_DOCUMENT",
    "DECISION_IMPLEMENTED_BY", "DECISION_AFFECTS_COMPONENT", "DECISION_SUPERSEDES",
    "DECISION_CONFLICTS_WITH", "WORK_ITEM_TRACKED_BY", "WORK_ITEM_IMPLEMENTED_BY",
    "WORK_ITEM_BLOCKED_BY", "WORK_ITEM_DEPENDS_ON", "WORK_ITEM_RELATED_TO",
    "WORK_ITEM_ADDRESSED_BY_COMMIT", "COMMIT_BELONGS_TO_PULL_REQUEST",
    "PULL_REQUEST_REFERENCES_ISSUE", "PULL_REQUEST_MODIFIES_COMPONENT",
    "COMMIT_MODIFIES_COMPONENT", "PULL_REQUEST_REVIEWED_BY", "PULL_REQUEST_AUTHORED_BY",
    "PERSON_AUTHORED", "PERSON_REVIEWED", "PERSON_ASSIGNED_TO",
    "PERSON_RESPONSIBLE_FOR", "PERSON_DISCUSSIONS_PARTICIPANT", "PERSON_CONTRIBUTED_TO",
    "COMPONENT_DEPENDS_ON", "COMPONENT_CALLS_COMPONENT", "COMPONENT_USES_SERVICE",
    "COMPONENT_STORES_DATA_IN", "COMPONENT_EXPOSES_API", "DOCUMENT_DESCRIBES_COMPONENT",
    "DOCUMENT_DESCRIBES_DECISION", "RISK_AFFECTS_COMPONENT", "BUG_FOUND_IN_COMPONENT",
    "RISK_BLOCKS_WORK_ITEM", "BUG_RELATED_TO_WORK_ITEM", "RISK_DEPENDS_ON_EXTERNAL_FACTOR",
    "KNOWLEDGE_SUPPORTED_BY_EVIDENCE", "KNOWLEDGE_CORROBORATED_BY",
    "DOCUMENT_REFERENCES_EVIDENCE", "DISCUSSION_REFERENCES_WORK_ITEM",
    "BELONGS_TO_WORK_CLUSTER", "HAS_WORKFLOW_STEP", "HAS_REQUIREMENT",
    "USES_TECHNOLOGY", "USES_COMPONENT", "CONFIGURED_IN", "TRACKED_BY",
    "ASSIGNED_TO", "CONTRIBUTED_TO", "HAS_FEATURE", "SENDS_TO",
]

_ALL_TYPES = sorted(list(set(_VERBOSE_TYPES + _ENUM_TYPES + _LOWER_TYPES + _UPPER_TYPES)))
_QUOTED_TYPES = ", ".join(f"'{t}'" for t in _ALL_TYPES)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text("ALTER TABLE knowledge_relationships DROP CONSTRAINT IF EXISTS ck_relationship_type_valid;")
        )
        op.execute(
            sa.text(
                f"ALTER TABLE knowledge_relationships ADD CONSTRAINT ck_relationship_type_valid "
                f"CHECK (relationship_type IN ({_QUOTED_TYPES}));"
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        quoted_verbose = ", ".join(f"'{t}'" for t in _VERBOSE_TYPES)
        op.execute(
            sa.text("ALTER TABLE knowledge_relationships DROP CONSTRAINT IF EXISTS ck_relationship_type_valid;")
        )
        op.execute(
            sa.text(
                f"ALTER TABLE knowledge_relationships ADD CONSTRAINT ck_relationship_type_valid "
                f"CHECK (relationship_type IN ({quoted_verbose}));"
            )
        )
