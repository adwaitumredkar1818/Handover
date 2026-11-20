"""Schemas for in-app notifications and active background task telemetry."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import BaseSchema


class NotificationResponse(BaseSchema):
    """In-app persistent notification item representation."""

    id: uuid.UUID
    organisation_id: uuid.UUID
    project_id: uuid.UUID | None
    user_id: uuid.UUID | None
    notification_type: str
    title: str
    body: str
    severity: str
    is_read: bool
    read_at: datetime | None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class NotificationListResponse(BaseSchema):
    """Paginated list of persistent notifications with unread count."""

    items: list[NotificationResponse]
    unread_count: int
    total: int


class ActiveSyncJobResponse(BaseSchema):
    """Real-time active sync or background job status."""

    id: uuid.UUID
    project_id: uuid.UUID
    job_type: str
    status: str
    stage: str | None = None
    progress_percent: int = 0
    attempt_count: int = 1
    total_steps: int | None = None
    completed_steps: int | None = None
    message: str | None = None
    mapping_id: str | None = None
    created_at: datetime
    started_at: datetime | None = None
