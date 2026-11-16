"""Team roster member extraction, reconciliation, and contribution attribution models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    ContributionCategory,
    ContributorReviewStatus,
    ContributorType,
    IdentityMatchMethod,
    ReconciliationStatus,
    ResponsibilityAlignment,
)

if TYPE_CHECKING:
    from app.models.evidence import EvidenceItem
    from app.models.project import Project, ProjectMembership

_JSON_VARIANT = JSON().with_variant(JSONB(astext_type=Text()), "postgresql")


class TeamRosterMember(Base):
    """Structured member extracted from uploaded team roster documents."""

    __tablename__ = "team_roster_members"
    __table_args__ = (
        CheckConstraint(
            "reconciliation_status IN ("
            "'pending', 'matched', 'possible_match', 'new_candidate', "
            "'ambiguous', 'conflict', 'rejected'"
            ")",
            name="team_roster_member_reconciliation_status",
        ),
        Index("ix_team_roster_project_evidence", "project_id", "evidence_item_id"),
        Index("ix_team_roster_status", "project_id", "reconciliation_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("evidence_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    member_id_in_roster: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    primary_responsibilities: Mapped[list[str]] = mapped_column(
        _JSON_VARIANT,
        nullable=False,
        default=list,
    )
    component_ownership: Mapped[list[str]] = mapped_column(
        _JSON_VARIANT,
        nullable=False,
        default=list,
    )
    github_username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    git_commit_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    jira_account_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    slack_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    reconciliation_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ReconciliationStatus.PENDING.value,
    )
    matched_project_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("project_memberships.id", ondelete="SET NULL"),
        nullable=True,
    )
    reconciliation_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reconciliation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        _JSON_VARIANT,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    project: Mapped[Project] = relationship(foreign_keys=[project_id])
    evidence_item: Mapped[EvidenceItem] = relationship(foreign_keys=[evidence_item_id])
    matched_membership: Mapped[ProjectMembership | None] = relationship(
        foreign_keys=[matched_project_membership_id]
    )


class ContributionAttribution(Base):
    """Attribution and alignment classification for commit and PR author contributions."""

    __tablename__ = "contribution_attributions"
    __table_args__ = (
        Index("ix_contribution_attributions_project", "project_id"),
        Index("ix_contribution_attributions_evidence", "evidence_item_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("evidence_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contributor_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    identifier_type: Mapped[str] = mapped_column(String(32), nullable=False)
    matched_roster_member_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("team_roster_members.id", ondelete="SET NULL"),
        nullable=True,
    )
    matched_project_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("project_memberships.id", ondelete="SET NULL"),
        nullable=True,
    )
    match_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    contribution_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    responsibility_alignment: Mapped[str | None] = mapped_column(String(64), nullable=True)
    alignment_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    contributor_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ContributorType.UNIDENTIFIED.value,
        server_default=ContributorType.UNIDENTIFIED.value,
    )
    review_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ContributorReviewStatus.PENDING.value,
        server_default=ContributorReviewStatus.PENDING.value,
    )
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        _JSON_VARIANT,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    project: Mapped[Project] = relationship(foreign_keys=[project_id])
    evidence_item: Mapped[EvidenceItem] = relationship(foreign_keys=[evidence_item_id])
    matched_roster_member: Mapped[TeamRosterMember | None] = relationship(
        foreign_keys=[matched_roster_member_id]
    )
    matched_membership: Mapped[ProjectMembership | None] = relationship(
        foreign_keys=[matched_project_membership_id]
    )
