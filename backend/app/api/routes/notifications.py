"""FastAPI routes for persistent user notifications and active background jobs."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_principal,
    get_db_session,
    require_project_permission,
    resolve_project_context,
)
from app.core.exceptions import NotFoundError
from app.core.security import utc_now
from app.models.enums import BackgroundJobStatus
from app.models.job import BackgroundJob
from app.models.notification import NotificationItem
from app.schemas.notification import (
    ActiveSyncJobResponse,
    NotificationListResponse,
    NotificationResponse,
)
from app.services.rbac import AuthenticatedPrincipal, ProjectContext

router = APIRouter(tags=["Notifications & Tasks"])


@router.get(
    "/notifications",
    response_model=NotificationListResponse,
    status_code=status.HTTP_200_OK,
    summary="List persistent notifications for the calling user",
)
def list_user_notifications(
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
    session: Annotated[Session, Depends(get_db_session)],
    project_id: Annotated[uuid.UUID | None, Query()] = None,
    unread_only: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> NotificationListResponse:
    """Fetch user-targeted notifications and project broadcasts."""
    user_id = principal.user.id

    base_filter = or_(
        NotificationItem.user_id == user_id,
        NotificationItem.user_id.is_(None),
    )
    if project_id:
        base_filter = base_filter & (
            or_(
                NotificationItem.project_id == project_id,
                NotificationItem.project_id.is_(None),
            )
        )
    if unread_only:
        base_filter = base_filter & (NotificationItem.is_read.is_(False))

    stmt = (
        select(NotificationItem)
        .where(base_filter)
        .order_by(NotificationItem.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    items = session.execute(stmt).scalars().all()

    # Unread count
    unread_filter = or_(
        NotificationItem.user_id == user_id,
        NotificationItem.user_id.is_(None),
    ) & (NotificationItem.is_read.is_(False))
    if project_id:
        unread_filter = unread_filter & (
            or_(
                NotificationItem.project_id == project_id,
                NotificationItem.project_id.is_(None),
            )
        )
    unread_count = (
        session.execute(select(func.count(NotificationItem.id)).where(unread_filter)).scalar_one()
        or 0
    )

    total_count = (
        session.execute(select(func.count(NotificationItem.id)).where(base_filter)).scalar_one()
        or 0
    )

    return NotificationListResponse(
        items=[
            NotificationResponse(
                id=item.id,
                organisation_id=item.organisation_id,
                project_id=item.project_id,
                user_id=item.user_id,
                notification_type=item.notification_type,
                title=item.title,
                body=item.body,
                severity=item.severity,
                is_read=item.is_read,
                read_at=item.read_at,
                metadata_json=dict(item.metadata_json or {}),
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in items
        ],
        unread_count=unread_count,
        total=total_count,
    )


@router.patch(
    "/notifications/{notification_id}/read",
    response_model=NotificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark a notification as read",
)
def mark_notification_read(
    notification_id: uuid.UUID,
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
    session: Annotated[Session, Depends(get_db_session)],
) -> NotificationResponse:
    item = session.get(NotificationItem, notification_id)
    if item is None:
        raise NotFoundError("Notification not found.", code="NOTIFICATION_NOT_FOUND")

    now = utc_now()
    item.is_read = True
    item.read_at = now
    session.commit()
    session.refresh(item)

    return NotificationResponse(
        id=item.id,
        organisation_id=item.organisation_id,
        project_id=item.project_id,
        user_id=item.user_id,
        notification_type=item.notification_type,
        title=item.title,
        body=item.body,
        severity=item.severity,
        is_read=item.is_read,
        read_at=item.read_at,
        metadata_json=dict(item.metadata_json or {}),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.post(
    "/notifications/mark-all-read",
    status_code=status.HTTP_200_OK,
    summary="Mark all unread notifications as read",
)
def mark_all_notifications_read(
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, int]:
    now = utc_now()
    stmt = (
        update(NotificationItem)
        .where(
            or_(
                NotificationItem.user_id == principal.user.id,
                NotificationItem.user_id.is_(None),
            ),
            NotificationItem.is_read.is_(False),
        )
        .values(is_read=True, read_at=now)
    )
    result = session.execute(stmt)
    session.commit()
    return {"marked_read": result.rowcount}


@router.get(
    "/projects/{project_id}/jobs/active",
    response_model=list[ActiveSyncJobResponse],
    status_code=status.HTTP_200_OK,
    summary="List active background sync and extraction tasks for a project",
)
def list_active_project_jobs(
    project_ctx: Annotated[ProjectContext, Depends(resolve_project_context)],
    session: Annotated[Session, Depends(get_db_session)],
) -> list[ActiveSyncJobResponse]:
    """Retrieve queued or running background jobs for persistent UI indicators."""
    stmt = (
        select(BackgroundJob)
        .where(
            BackgroundJob.project_id == project_ctx.project.id,
            BackgroundJob.status.in_(
                [BackgroundJobStatus.QUEUED.value, BackgroundJobStatus.RUNNING.value]
            ),
        )
        .order_by(BackgroundJob.created_at.desc())
        .limit(20)
    )
    jobs = session.execute(stmt).scalars().all()

    active_jobs: list[ActiveSyncJobResponse] = []
    for job in jobs:
        payload = job.payload_json or {}
        progress = int(payload.get("progress_percent") or 0)
        stage = payload.get("stage") or job.status
        active_jobs.append(
            ActiveSyncJobResponse(
                id=job.id,
                project_id=job.project_id or project_ctx.project.id,
                job_type=job.job_type,
                status=job.status,
                stage=stage,
                progress_percent=progress,
                attempt_count=job.attempt_count,
                total_steps=payload.get("total_steps"),
                completed_steps=payload.get("completed_steps"),
                message=payload.get("current_item") or job.error_message,
                created_at=job.created_at,
                started_at=job.started_at,
            )
        )
    return active_jobs
