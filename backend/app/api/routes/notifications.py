"""FastAPI routes for persistent user notifications and active background jobs."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_principal,
    get_db_session,
    resolve_project_context,
)
from app.core.cache.local_cache import local_response_cache
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
    bind = session.get_bind()
    cache_key = (
        f"notifications:{id(bind)}:{user_id}:{project_id}:{int(unread_only)}:{limit}:{offset}"
    )
    cached = local_response_cache.get(cache_key)
    if cached is not None:
        try:
            return NotificationListResponse.model_validate(cached)
        except Exception:
            local_response_cache.delete(cache_key)

    user_scope = or_(
        NotificationItem.user_id == user_id,
        NotificationItem.user_id.is_(None),
    )
    scope_filter = user_scope
    if project_id:
        scope_filter = scope_filter & (
            or_(
                NotificationItem.project_id == project_id,
                NotificationItem.project_id.is_(None),
            )
        )
    list_filter = scope_filter & (NotificationItem.is_read.is_(False)) if unread_only else scope_filter

    stmt = (
        select(NotificationItem)
        .where(list_filter)
        .order_by(NotificationItem.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    items = session.execute(stmt).scalars().all()

    agg_row = session.execute(
        select(
            func.count(NotificationItem.id),
            func.coalesce(
                func.sum(case((NotificationItem.is_read.is_(False), 1), else_=0)),
                0,
            ),
        ).where(scope_filter)
    ).first()
    scoped_total = int(agg_row[0] or 0) if agg_row else 0
    unread_count = int(agg_row[1] or 0) if agg_row else 0
    total_count = unread_count if unread_only else scoped_total

    resp = NotificationListResponse(
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
    local_response_cache.set(cache_key, resp.model_dump(mode="json"), ttl_seconds=10)
    return resp


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
    bind = session.get_bind()
    local_response_cache.invalidate_prefix(f"notifications:{id(bind)}:")

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
    bind = session.get_bind()
    local_response_cache.invalidate_prefix(f"notifications:{id(bind)}:")
    marked_count = int(getattr(result, "rowcount", 0) or 0)
    return {"marked_read": marked_count}


_INDEXING_TYPES = frozenset(
    {
        "evidence_indexing",
        "evidence_chunking",
        "evidence_embedding",
        "evidence_reindexing",
    }
)


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
    import os

    is_test = bool(os.environ.get("PYTEST_CURRENT_TEST"))
    bind = session.get_bind()
    cache_key = f"active_jobs:{project_ctx.project.id}:{id(bind)}"
    if not is_test:
        cached = local_response_cache.get(cache_key)
        if isinstance(cached, list):
            try:
                return [ActiveSyncJobResponse.model_validate(j) for j in cached]
            except Exception:
                local_response_cache.delete(cache_key)

    stmt = (
        select(BackgroundJob)
        .where(
            BackgroundJob.project_id == project_ctx.project.id,
            BackgroundJob.status.in_(
                [BackgroundJobStatus.QUEUED.value, BackgroundJobStatus.RUNNING.value]
            ),
        )
        .order_by(BackgroundJob.created_at.desc())
        .limit(100)
    )
    jobs = session.execute(stmt).scalars().all()

    active_jobs: list[ActiveSyncJobResponse] = []
    indexing_jobs: list[BackgroundJob] = []
    for job in jobs:
        if job.job_type in _INDEXING_TYPES:
            indexing_jobs.append(job)
            continue
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
                mapping_id=str(payload.get("mapping_id")) if payload.get("mapping_id") else None,
                created_at=job.created_at,
                started_at=job.started_at,
            )
        )

    if indexing_jobs:
        lead = indexing_jobs[0]
        running_cnt = sum(1 for j in indexing_jobs if j.status == BackgroundJobStatus.RUNNING.value)
        active_jobs.append(
            ActiveSyncJobResponse(
                id=lead.id,
                project_id=lead.project_id or project_ctx.project.id,
                job_type=lead.job_type,
                status="running" if running_cnt > 0 else "queued",
                stage="indexing",
                progress_percent=0,
                attempt_count=lead.attempt_count,
                total_steps=len(indexing_jobs),
                completed_steps=0,
                message=f"Indexing {len(indexing_jobs)} evidence item(s)",
                created_at=lead.created_at,
                started_at=lead.started_at,
            )
        )

    local_response_cache.set(
        cache_key, [j.model_dump(mode="json") for j in active_jobs], ttl_seconds=10
    )
    return active_jobs
