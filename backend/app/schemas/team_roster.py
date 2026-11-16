"""Pydantic v2 schemas for team roster members and contribution attributions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.schemas.common import BaseSchema


class TeamRosterMemberResponse(BaseSchema):
    """Extracted team roster member record."""

    id: uuid.UUID
    project_id: uuid.UUID
    evidence_item_id: uuid.UUID
    member_id_in_roster: str | None = None
    full_name: str
    email: str | None = None
    role_name: str | None = None
    primary_responsibilities: list[str] = Field(default_factory=list)
    component_ownership: list[str] = Field(default_factory=list)
    github_username: str | None = None
    git_commit_email: str | None = None
    jira_account_id: str | None = None
    slack_user_id: str | None = None
    reconciliation_status: str
    matched_project_membership_id: uuid.UUID | None = None
    matched_member_name: str | None = None
    reconciliation_confidence: float | None = None
    reconciliation_notes: str | None = None
    created_at: datetime
    updated_at: datetime


class ReconcileRosterMemberRequest(BaseSchema):
    """Payload for human verification of extracted roster member."""

    reconciliation_status: str = Field(pattern="^(matched|possible_match|new_candidate|ambiguous|conflict|rejected)$")
    matched_project_membership_id: uuid.UUID | None = None
    reconciliation_notes: str | None = None


class ContributionAttributionResponse(BaseSchema):
    """Attributed commit or PR contribution with domain classification and alignment."""

    id: uuid.UUID
    project_id: uuid.UUID
    evidence_item_id: uuid.UUID
    contributor_identifier: str
    identifier_type: str
    matched_roster_member_id: uuid.UUID | None = None
    matched_roster_name: str | None = None
    matched_project_membership_id: uuid.UUID | None = None
    match_method: str | None = None
    match_confidence: float | None = None
    contribution_category: str | None = None
    responsibility_alignment: str | None = None
    alignment_explanation: str | None = None
    created_at: datetime
    updated_at: datetime
