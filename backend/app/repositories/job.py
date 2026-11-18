"""Data-access repository for PostgreSQL-backed background jobs."""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import utc_now
from app.models.enums import BackgroundJobStatus, BackgroundJobType
from app.models.job import BackgroundJob

_heartbeat_logger = logging.getLogger("app.repositories.job")


class BackgroundJobRepository:
    """Repository managing durable background job enqueueing, claiming, and state updates."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, job_id: uuid.UUID) -> BackgroundJob | None:
        return self._session.get(BackgroundJob, job_id)

    def create_job(
        self,
        *,
        organisation_id: uuid.UUID,
        project_id: uuid.UUID,
        evidence_id: uuid.UUID | None,
        triggered_by_user_id: uuid.UUID | None,
        job_type: str,
        max_attempts: int = 3,
        priority: int = 100,
        payload_json: dict[str, Any] | None = None,
        flush: bool = True,
    ) -> BackgroundJob:
        job = BackgroundJob(
            organisation_id=organisation_id,
            project_id=project_id,
            evidence_id=evidence_id,
            triggered_by_user_id=triggered_by_user_id,
            job_type=job_type,
            status=BackgroundJobStatus.QUEUED.value,
            priority=priority,
            attempt_count=0,
            max_attempts=max_attempts,
            payload_json=dict(payload_json or {}),
        )
        self._session.add(job)
        if flush:
            self._session.flush()
        return job

    def list_for_evidence(self, evidence_id: uuid.UUID) -> list[BackgroundJob]:
        stmt = (
            select(BackgroundJob)
            .where(BackgroundJob.evidence_id == evidence_id)
            .order_by(BackgroundJob.created_at.desc(), BackgroundJob.id.desc())
        )
        return list(self._session.execute(stmt).scalars().all())

    def has_active_job_for_evidence(
        self,
        *,
        evidence_id: uuid.UUID,
        job_type: str,
    ) -> bool:
        stmt = (
            select(BackgroundJob.id)
            .where(
                BackgroundJob.evidence_id == evidence_id,
                BackgroundJob.job_type == job_type,
                BackgroundJob.status.in_(
                    (
                        BackgroundJobStatus.QUEUED.value,
                        BackgroundJobStatus.RUNNING.value,
                    )
                ),
            )
            .limit(1)
        )
        return self._session.execute(stmt).scalar_one_or_none() is not None

    def has_active_source_sync_job(
        self,
        *,
        project_id: uuid.UUID,
        mapping_id: uuid.UUID,
    ) -> bool:
        """Check across dialects whether an active source_sync job exists for a mapping."""
        stmt = select(BackgroundJob).where(
            BackgroundJob.project_id == project_id,
            BackgroundJob.job_type == BackgroundJobType.SOURCE_SYNC.value,
            BackgroundJob.status.in_(
                (
                    BackgroundJobStatus.QUEUED.value,
                    BackgroundJobStatus.RUNNING.value,
                )
            ),
        )
        target_id = str(mapping_id)
        for job in self._session.execute(stmt).scalars().all():
            payload = job.payload_json or {}
            if str(payload.get("mapping_id") or "") == target_id:
                return True
        return False

    def cancel_job(
        self,
        *,
        job: BackgroundJob,
        now: datetime,
        error_code: str,
        error_message: str,
    ) -> bool:
        """Cancel a queued or running background job safely without touching terminal jobs."""
        if job.status not in {
            BackgroundJobStatus.QUEUED.value,
            BackgroundJobStatus.RUNNING.value,
        }:
            return False
        job.status = BackgroundJobStatus.CANCELLED.value
        job.completed_at = now
        job.locked_by = None
        job.lease_expires_at = None
        job.error_code = error_code[:64]
        job.error_message = error_message[:500]
        self._session.flush()
        return True

    def cancel_pending_jobs_for_evidence(
        self,
        *,
        evidence_id: uuid.UUID,
        now: datetime,
    ) -> int:
        result = self._session.execute(
            update(BackgroundJob)
            .where(
                BackgroundJob.evidence_id == evidence_id,
                BackgroundJob.status == BackgroundJobStatus.QUEUED.value,
            )
            .values(
                status=BackgroundJobStatus.CANCELLED.value,
                completed_at=now,
                error_code="EVIDENCE_DELETED",
                error_message="Job cancelled because parent evidence item was deleted.",
            )
        )
        self._session.flush()
        return int(getattr(result, "rowcount", 0) or 0)

    def fail_expired_exhausted_jobs(self, *, now: datetime) -> int:
        """Mark stale leased jobs that exhausted retries as failed before claiming."""
        result = self._session.execute(
            update(BackgroundJob)
            .where(
                BackgroundJob.status == BackgroundJobStatus.RUNNING.value,
                BackgroundJob.lease_expires_at.is_not(None),
                BackgroundJob.lease_expires_at < now,
                BackgroundJob.attempt_count >= BackgroundJob.max_attempts,
            )
            .values(
                status=BackgroundJobStatus.FAILED.value,
                completed_at=now,
                locked_by=None,
                lease_expires_at=None,
                error_code="WORKER_LEASE_EXPIRED",
                error_message="Worker lease expired after reaching maximum retry attempts.",
            )
        )
        self._session.flush()
        return int(getattr(result, "rowcount", 0) or 0)

    def recover_orphaned_jobs(self, *, now: datetime | None = None) -> int:
        """Reset jobs left in RUNNING status back to QUEUED on server/worker boot."""
        ts = now or utc_now()
        stmt = (
            update(BackgroundJob)
            .where(
                BackgroundJob.status == BackgroundJobStatus.RUNNING.value,
                BackgroundJob.attempt_count < BackgroundJob.max_attempts,
            )
            .values(
                status=BackgroundJobStatus.QUEUED.value,
                locked_by=None,
                lease_expires_at=None,
                next_retry_at=ts,
            )
        )
        res = self._session.execute(stmt)
        # Also reset any running sync runs whose jobs were orphaned
        from app.models.enums import SourceSyncRunStatus
        from app.models.integration import SourceSyncRun

        self._session.execute(
            update(SourceSyncRun)
            .where(
                SourceSyncRun.status == SourceSyncRunStatus.RUNNING.value,
            )
            .values(
                status=SourceSyncRunStatus.QUEUED.value,
            )
        )
        self._session.flush()
        return int(getattr(res, "rowcount", 0) or 0)

    def has_active_job_for_project(
        self,
        *,
        project_id: uuid.UUID,
        job_types: Sequence[str],
    ) -> BackgroundJob | None:
        """Return an active (queued/running) project-level job matching any given type."""
        if not job_types:
            return None
        stmt = (
            select(BackgroundJob)
            .where(
                BackgroundJob.project_id == project_id,
                BackgroundJob.job_type.in_(list(job_types)),
                BackgroundJob.status.in_(
                    (
                        BackgroundJobStatus.QUEUED.value,
                        BackgroundJobStatus.RUNNING.value,
                    )
                ),
            )
            .order_by(BackgroundJob.created_at.desc())
            .limit(1)
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def claim_next_job(
        self,
        *,
        worker_id: str,
        lease_seconds: int,
        now: datetime,
        job_type: str | None = None,
        job_types: Sequence[str] | None = None,
    ) -> BackgroundJob | None:
        """Atomically claim the next ready job using `FOR UPDATE SKIP LOCKED` on PostgreSQL."""
        self.fail_expired_exhausted_jobs(now=now)

        ready_queued = and_(
            BackgroundJob.status == BackgroundJobStatus.QUEUED.value,
            or_(
                BackgroundJob.next_retry_at.is_(None),
                BackgroundJob.next_retry_at <= now,
            ),
            BackgroundJob.attempt_count < BackgroundJob.max_attempts,
        )
        expired_running = and_(
            BackgroundJob.status == BackgroundJobStatus.RUNNING.value,
            BackgroundJob.lease_expires_at.is_not(None),
            BackgroundJob.lease_expires_at < now,
            BackgroundJob.attempt_count < BackgroundJob.max_attempts,
        )

        stmt = select(BackgroundJob).where(or_(ready_queued, expired_running))
        if job_types:
            stmt = stmt.where(BackgroundJob.job_type.in_(list(job_types)))
        elif job_type is not None:
            stmt = stmt.where(BackgroundJob.job_type == job_type)
        stmt = stmt.order_by(BackgroundJob.priority.asc(), BackgroundJob.created_at.asc()).limit(1)

        bind = self._session.get_bind()
        if bind is not None and bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)

        job = self._session.execute(stmt).scalar_one_or_none()
        if job is None:
            return None

        job.status = BackgroundJobStatus.RUNNING.value
        job.attempt_count = int(job.attempt_count) + 1
        job.locked_by = worker_id[:128]
        job.locked_at = now
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        if job.started_at is None:
            job.started_at = now
        job.error_code = None
        job.error_message = None
        self._session.flush()
        return job


@contextmanager
def job_lease_heartbeat(
    *,
    session_factory: sessionmaker[Session],
    job_id: uuid.UUID,
    lease_seconds: int = 300,
    interval_seconds: float = 30.0,
) -> Iterator[None]:
    """Periodically extend a running BackgroundJob lease on an isolated session."""
    stop_event = threading.Event()
    effective_lease = max(180, int(lease_seconds))
    effective_interval = max(5.0, min(float(interval_seconds), effective_lease / 3.0))

    def _beat() -> None:
        while not stop_event.wait(effective_interval):
            try:
                now = utc_now()
                with session_factory() as beat_session:
                    beat_session.execute(
                        update(BackgroundJob)
                        .where(
                            BackgroundJob.id == job_id,
                            BackgroundJob.status == BackgroundJobStatus.RUNNING.value,
                        )
                        .values(
                            lease_expires_at=now + timedelta(seconds=effective_lease),
                            locked_at=now,
                        )
                    )
                    beat_session.commit()
            except Exception as exc:  # pragma: no cover - defensive runtime safeguard
                _heartbeat_logger.debug("Lease heartbeat failed for job %s: %s", job_id, exc)

    thread = threading.Thread(
        target=_beat,
        name=f"job-lease-{str(job_id)[:8]}",
        daemon=True,
    )
    thread.start()
    try:
        yield
    finally:
        stop_event.set()
        thread.join(timeout=2.0)
