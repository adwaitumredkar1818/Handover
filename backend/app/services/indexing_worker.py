"""PostgreSQL-backed background worker for evidence chunking, PG FTS, and ChromaDB indexing."""

from __future__ import annotations

import logging
import socket
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import ExtractionSettings, IngestionSettings
from app.core.logging import redact_sensitive_text
from app.core.security import utc_now
from app.models.enums import (
    AuditOutcome,
    BackgroundJobStatus,
    BackgroundJobType,
    ChunkIndexingStatus,
    EvidenceIndexingStatus,
    EvidenceProcessingStatus,
    ExtractionRunScope,
    ExtractionRunStatus,
    KnowledgeCategory,
)
from app.models.knowledge import KnowledgeExtractionRun
from app.repositories.audit import AuditLogRepository
from app.repositories.chunk import EvidenceChunkRepository
from app.repositories.evidence import EvidenceRepository
from app.repositories.job import BackgroundJobRepository
from app.repositories.knowledge import KnowledgeRepository
from app.services.audit import AuditService
from app.services.chunking import ChunkingService
from app.services.embedding import EmbeddingExecutionError, EmbeddingService
from app.services.vector_store import (
    VectorStoreClient,
    VectorStoreError,
    VectorUpsertRecord,
    build_deterministic_vector_id,
    resolve_permission_scope_key,
    sanitize_vector_metadata,
)

logger = logging.getLogger("app.services.indexing_worker")

_SUPPORTED_INDEXING_JOBS: tuple[str, ...] = (
    BackgroundJobType.EVIDENCE_INDEX_CLEANUP.value,
    BackgroundJobType.EVIDENCE_INDEXING.value,
    BackgroundJobType.EVIDENCE_CHUNKING.value,
    BackgroundJobType.EVIDENCE_EMBEDDING.value,
    BackgroundJobType.EVIDENCE_REINDEXING.value,
)

_ELIGIBLE_PROCESSING_STATUSES: frozenset[str] = frozenset(
    {
        EvidenceProcessingStatus.EXTRACTED.value,
        EvidenceProcessingStatus.PARTIALLY_EXTRACTED.value,
    }
)


def _default_worker_id() -> str:
    return f"{socket.gethostname()[:48]}-index-{uuid.uuid4().hex[:8]}"


def _sanitise_error(message: str) -> str:
    return redact_sensitive_text(message).strip()[:500]


@dataclass(frozen=True, slots=True)
class _ClaimedIndexJob:
    job_id: uuid.UUID
    job_type: str
    organisation_id: uuid.UUID
    project_id: uuid.UUID
    evidence_id: uuid.UUID | None
    attempt_count: int
    max_attempts: int
    payload_json: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _ItemIndexOutcome:
    status: str  # "indexed" | "partially_indexed" | "failed" | "skipped"
    chunk_count: int
    vectors_upserted: int
    retryable: bool = False
    error_code: str | None = None
    error_message: str | None = None


class IndexingWorkerService:
    """Executes async chunking, PG FTS population, Nomic embeddings, Chroma upsert & cleanup."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        chunking_service: ChunkingService,
        embedding_service: EmbeddingService,
        vector_store: VectorStoreClient,
        ingestion_settings: IngestionSettings,
        extraction_settings: ExtractionSettings | None = None,
        llm_model_name: str = "qwen3:8b",
        worker_id: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._chunking = chunking_service
        self._embedding = embedding_service
        self._vector_store = vector_store
        self._settings = ingestion_settings
        self._extraction_settings = extraction_settings
        self._llm_model_name = llm_model_name
        self._worker_id = worker_id or _default_worker_id()

    @property
    def worker_id(self) -> str:
        """Identifier recorded on claimed job leases."""
        return self._worker_id

    def drain_pending_jobs(self, *, max_jobs: int = 100) -> int:
        """Process currently ready indexing jobs sequentially up to `max_jobs`."""
        processed = 0
        while processed < max_jobs:
            if not self.process_next_job():
                break
            processed += 1
        return processed

    def process_next_job(self) -> bool:
        """Claim and execute one ready indexing/cleanup/reindex job; return True if handled."""
        claimed = self._claim_job()
        if claimed is None:
            return False

        started_perf = time.perf_counter()
        try:
            if claimed.job_type == BackgroundJobType.EVIDENCE_INDEX_CLEANUP.value:
                self._execute_cleanup_job(claimed=claimed, started_perf=started_perf)
            elif claimed.job_type == BackgroundJobType.EVIDENCE_REINDEXING.value:
                self._execute_reindex_job(claimed=claimed, started_perf=started_perf)
            else:
                self._execute_single_evidence_job(claimed=claimed, started_perf=started_perf)
        except Exception as exc:  # pragma: no cover - defensive runtime safeguard
            elapsed_ms = int((time.perf_counter() - started_perf) * 1000)
            logger.exception("Unhandled error inside indexing worker.")
            self._fail_job_only(
                claimed=claimed,
                duration_ms=elapsed_ms,
                error_code="INDEX_WORKER_UNEXPECTED_ERROR",
                error_message=f"Unexpected indexing worker failure: {type(exc).__name__}",
                retryable=claimed.attempt_count < claimed.max_attempts,
            )
        return True

    def _claim_job(self) -> _ClaimedIndexJob | None:
        now = utc_now()
        with self._session_factory() as session:
            job_repo = BackgroundJobRepository(session)
            evidence_repo = EvidenceRepository(session)

            job = job_repo.claim_next_job(
                worker_id=self._worker_id,
                lease_seconds=self._settings.worker_lease_seconds,
                now=now,
                job_types=_SUPPORTED_INDEXING_JOBS,
            )
            if job is None:
                session.commit()
                return None

            payload = dict(job.payload_json or {})
            if job.job_type in {
                BackgroundJobType.EVIDENCE_INDEXING.value,
                BackgroundJobType.EVIDENCE_CHUNKING.value,
                BackgroundJobType.EVIDENCE_EMBEDDING.value,
            }:
                if job.evidence_id is None:
                    job.status = BackgroundJobStatus.FAILED.value
                    job.completed_at = now
                    job.error_code = "MISSING_EVIDENCE_REF"
                    job.error_message = "Indexing job is missing an evidence_id reference."
                    job.locked_by = None
                    job.lease_expires_at = None
                    session.commit()
                    return None

                evidence = evidence_repo.get_by_id(job.evidence_id, include_deleted=False)
                if evidence is None:
                    job.status = BackgroundJobStatus.CANCELLED.value
                    job.completed_at = now
                    job.error_code = "EVIDENCE_UNAVAILABLE"
                    job.error_message = "Parent evidence item is unavailable or deleted."
                    job.locked_by = None
                    job.lease_expires_at = None
                    session.commit()
                    return None

                if evidence.processing_status not in _ELIGIBLE_PROCESSING_STATUSES:
                    job.status = BackgroundJobStatus.FAILED.value
                    job.completed_at = now
                    job.error_code = "EVIDENCE_NOT_EXTRACTED"
                    job.error_message = (
                        "Evidence item cannot be indexed while processing_status is "
                        f"'{evidence.processing_status}'."
                    )
                    job.locked_by = None
                    job.lease_expires_at = None
                    session.commit()
                    return None

                evidence.indexing_status = EvidenceIndexingStatus.PROCESSING.value
                evidence.index_error_code = None
                evidence.index_error_message = None
                claim_meta = dict(evidence.metadata_json or {})
                claim_meta["lifecycle_stage"] = "indexing"
                evidence.metadata_json = claim_meta

            claimed = _ClaimedIndexJob(
                job_id=job.id,
                job_type=job.job_type,
                organisation_id=job.organisation_id,
                project_id=job.project_id,
                evidence_id=job.evidence_id,
                attempt_count=int(job.attempt_count),
                max_attempts=int(job.max_attempts),
                payload_json=payload,
            )
            session.commit()
            return claimed

    def _execute_cleanup_job(self, *, claimed: _ClaimedIndexJob, started_perf: float) -> None:
        target_ev_id = claimed.evidence_id
        if target_ev_id is None and claimed.payload_json.get("evidence_id"):
            try:
                target_ev_id = uuid.UUID(str(claimed.payload_json["evidence_id"]))
            except ValueError:
                target_ev_id = None

        if target_ev_id is None:
            elapsed_ms = int((time.perf_counter() - started_perf) * 1000)
            self._fail_job_only(
                claimed=claimed,
                duration_ms=elapsed_ms,
                error_code="MISSING_EVIDENCE_REF",
                error_message="Index cleanup job omitted target evidence_id.",
                retryable=False,
            )
            return

        payload_vector_ids = [
            str(v)
            for v in (claimed.payload_json.get("vector_ids") or [])
            if isinstance(v, str) and v.strip()
        ]

        with self._session_factory() as session:
            db_vector_ids = EvidenceChunkRepository(session).delete_chunks_for_evidence(
                target_ev_id
            )
            ev = EvidenceRepository(session).get_by_id(target_ev_id, include_deleted=True)
            if ev is not None:
                ev.indexing_status = EvidenceIndexingStatus.DELETED.value
                ev.chunk_count = 0
                ev.index_error_code = None
                ev.index_error_message = None
            session.commit()

        vectors_deleted = 0
        try:
            vectors_deleted += self._vector_store.delete_records(
                where={"evidence_id": str(target_ev_id)},
            )
            combined_ids = list(dict.fromkeys([*payload_vector_ids, *db_vector_ids]))
            if combined_ids:
                self._vector_store.delete_records(ids=combined_ids)
        except VectorStoreError as exc:
            elapsed_ms = int((time.perf_counter() - started_perf) * 1000)
            self._fail_job_only(
                claimed=claimed,
                duration_ms=elapsed_ms,
                error_code=exc.code,
                error_message=exc.message,
                retryable=exc.retryable and claimed.attempt_count < claimed.max_attempts,
            )
            return

        elapsed_ms = int((time.perf_counter() - started_perf) * 1000)
        now = utc_now()
        with self._session_factory() as session:
            job = BackgroundJobRepository(session).get_by_id(claimed.job_id)
            audit = AuditService(audit_repository=AuditLogRepository(session))
            if job is not None:
                job.status = BackgroundJobStatus.SUCCEEDED.value
                job.completed_at = now
                job.duration_ms = elapsed_ms
                job.locked_by = None
                job.lease_expires_at = None
                job.error_code = None
                job.error_message = None
                job.result_json = {
                    "evidence_id": str(target_ev_id),
                    "vectors_deleted": vectors_deleted,
                }
            audit.record_event(
                event_type="evidence.index_cleanup_completed",
                resource_type="evidence_item",
                actor_user_id=None,
                organisation_id=claimed.organisation_id,
                project_id=claimed.project_id,
                resource_id=str(target_ev_id),
                metadata={
                    "job_id": str(claimed.job_id),
                    "vectors_deleted": vectors_deleted,
                    "duration_ms": elapsed_ms,
                },
                message="Cleaned up PostgreSQL chunks and ChromaDB vectors for deleted evidence.",
            )
            session.commit()

    def _execute_single_evidence_job(
        self,
        *,
        claimed: _ClaimedIndexJob,
        started_perf: float,
    ) -> None:
        if claimed.evidence_id is None:
            raise ValueError("Single-evidence indexing job requires a non-null evidence_id.")
        target = str(claimed.payload_json.get("target") or "full").strip().lower()
        if claimed.job_type == BackgroundJobType.EVIDENCE_CHUNKING.value:
            target = "fts_only"
        elif claimed.job_type == BackgroundJobType.EVIDENCE_EMBEDDING.value:
            target = "vectors_only"

        force_rechunk = bool(
            claimed.payload_json.get(
                "force_rechunk",
                claimed.job_type
                in {
                    BackgroundJobType.EVIDENCE_INDEXING.value,
                    BackgroundJobType.EVIDENCE_CHUNKING.value,
                },
            )
        )

        outcome = self._index_single_evidence_item(
            evidence_id=claimed.evidence_id,
            target=target,
            force_rechunk=force_rechunk,
        )
        elapsed_ms = int((time.perf_counter() - started_perf) * 1000)

        now = utc_now()
        with self._session_factory() as session:
            job_repo = BackgroundJobRepository(session)
            audit = AuditService(audit_repository=AuditLogRepository(session))
            job = job_repo.get_by_id(claimed.job_id)
            if job is None:
                return

            if outcome.status == "skipped":
                job.status = BackgroundJobStatus.CANCELLED.value
                job.completed_at = now
                job.duration_ms = elapsed_ms
                job.locked_by = None
                job.lease_expires_at = None
                job.error_code = "EVIDENCE_UNAVAILABLE"
                job.error_message = (
                    "Evidence item was removed or became ineligible before completion."
                )
                session.commit()
                return

            if outcome.status == "indexed":
                job.status = BackgroundJobStatus.SUCCEEDED.value
                job.completed_at = now
                job.duration_ms = elapsed_ms
                job.locked_by = None
                job.lease_expires_at = None
                job.error_code = None
                job.error_message = None
                job.result_json = {
                    "target": target,
                    "indexing_status": outcome.status,
                    "chunk_count": outcome.chunk_count,
                    "vectors_upserted": outcome.vectors_upserted,
                    "embedding_model": self._embedding.model_name,
                    "index_version": self._vector_store.index_version,
                }
                audit.record_event(
                    event_type="evidence.indexing_completed",
                    resource_type="evidence_item",
                    actor_user_id=None,
                    organisation_id=claimed.organisation_id,
                    project_id=claimed.project_id,
                    resource_id=str(claimed.evidence_id),
                    metadata={
                        "job_id": str(job.id),
                        "chunk_count": outcome.chunk_count,
                        "vectors_upserted": outcome.vectors_upserted,
                        "target": target,
                        "duration_ms": elapsed_ms,
                    },
                    message=f"Completed evidence indexing ({outcome.chunk_count} chunk(s)).",
                )
                session.commit()

                # Run per-evidence fast extraction and progressive relationship updates immediately
                try:
                    from app.services.fast_extractor import FastKnowledgeExtractor
                    from app.repositories.evidence import EvidenceRepository

                    with self._session_factory() as item_session:
                        ev_item = EvidenceRepository(item_session).get_by_id(claimed.evidence_id, include_deleted=False)
                        if ev_item is not None:
                            fast_extractor = FastKnowledgeExtractor(item_session)
                            fast_items = fast_extractor.extract_evidence_knowledge(
                                evidence=ev_item,
                                force_rerun=False,
                            )
                            item_session.commit()

                            meta = dict(ev_item.metadata_json or {})
                            k_count = len(fast_items) if fast_items else meta.get("knowledge_count", 0)
                            meta["knowledge_count"] = k_count
                            if k_count > 0:
                                meta["lifecycle_stage"] = "knowledge_ready"
                            else:
                                meta["lifecycle_stage"] = "indexed"
                            ev_item.metadata_json = meta
                            item_session.commit()

                            # Run progressive relationship reconstruction when new non-outline fast items were created
                            # or when a high-value item (manifest, repo, PR, issue, doc) was indexed without graph update yet
                            from app.services.technology_manifest_parser import is_manifest_path

                            has_non_outline_fast_items = any(
                                not (it.structured_payload or {}).get("is_document_outline")
                                for it in (fast_items or [])
                            )
                            needs_initial_graph_projection = (
                                k_count > 0
                                and meta.get("lifecycle_stage") != "graph_updated"
                                and (
                                    ev_item.category in ("design_document", "project_document", "pull_request", "issue", "architecture")
                                    or is_manifest_path(ev_item.title)
                                    or meta.get("github_item_type") == "repository"
                                )
                            )
                            if has_non_outline_fast_items or needs_initial_graph_projection:
                                try:
                                    from app.services.knowledge_graphs import invalidate_knowledge_graph_cache
                                    from app.services.relationship_coordinator import RelationshipCoordinatorService

                                    with self._session_factory() as rel_session:
                                        RelationshipCoordinatorService(rel_session).run_reconstruction(
                                            organisation_id=claimed.organisation_id,
                                            project_id=claimed.project_id,
                                            include_llm_suggestions=False,
                                        )
                                        rel_session.commit()
                                    invalidate_knowledge_graph_cache(claimed.project_id)

                                    with self._session_factory() as upd_session:
                                        ev_upd = EvidenceRepository(upd_session).get_by_id(claimed.evidence_id, include_deleted=False)
                                        if ev_upd:
                                            m = dict(ev_upd.metadata_json or {})
                                            m["lifecycle_stage"] = "graph_updated"
                                            ev_upd.metadata_json = m
                                            upd_session.commit()
                                except Exception as rel_exc:
                                    logger.warning("Progressive relationship update failed: %s", rel_exc)
                except Exception as fast_exc:
                    logger.warning("Per-evidence fast extraction skipped: %s", fast_exc)

                return

            # Degraded (`partially_indexed`) or chunking failure (`failed`)
            should_retry = outcome.retryable and claimed.attempt_count < claimed.max_attempts
            safe_code = (outcome.error_code or "INDEXING_ERROR")[:64]
            safe_msg = _sanitise_error(
                outcome.error_message or "Evidence indexing encountered an error."
            )
            if should_retry:
                backoff = min(
                    3600,
                    self._settings.worker_retry_base_seconds
                    * (2 ** max(0, claimed.attempt_count - 1)),
                )
                job.status = BackgroundJobStatus.QUEUED.value
                job.next_retry_at = now + timedelta(seconds=backoff)
                job.locked_by = None
                job.lease_expires_at = None
                job.error_code = safe_code
                job.error_message = safe_msg
                audit.record_event(
                    event_type="evidence.indexing_retry_scheduled",
                    resource_type="evidence_item",
                    actor_user_id=None,
                    organisation_id=claimed.organisation_id,
                    project_id=claimed.project_id,
                    resource_id=str(claimed.evidence_id),
                    outcome=AuditOutcome.ERROR.value,
                    metadata={
                        "job_id": str(job.id),
                        "attempt_count": claimed.attempt_count,
                        "retry_delay_seconds": backoff,
                        "error_code": safe_code,
                        "chunk_count": outcome.chunk_count,
                    },
                    message="Scheduled retry for evidence vector indexing.",
                    level=logging.WARNING,
                )
            else:
                if target == "fts_only" and outcome.status == "partially_indexed":
                    job.status = BackgroundJobStatus.SUCCEEDED.value
                    job.error_code = None
                    job.error_message = None
                else:
                    job.status = BackgroundJobStatus.FAILED.value
                    job.error_code = safe_code
                    job.error_message = safe_msg
                job.completed_at = now
                job.duration_ms = elapsed_ms
                job.locked_by = None
                job.lease_expires_at = None
                job.result_json = {
                    "target": target,
                    "indexing_status": outcome.status,
                    "chunk_count": outcome.chunk_count,
                    "vectors_upserted": outcome.vectors_upserted,
                }
                audit.record_event(
                    event_type=(
                        "evidence.indexing_partially_indexed"
                        if outcome.status == "partially_indexed"
                        else "evidence.indexing_failed"
                    ),
                    resource_type="evidence_item",
                    actor_user_id=None,
                    organisation_id=claimed.organisation_id,
                    project_id=claimed.project_id,
                    resource_id=str(claimed.evidence_id),
                    outcome=AuditOutcome.ERROR.value,
                    metadata={
                        "job_id": str(job.id),
                        "error_code": safe_code,
                        "chunk_count": outcome.chunk_count,
                        "indexing_status": outcome.status,
                    },
                    message=safe_msg,
                    level=logging.ERROR if outcome.status == "failed" else logging.WARNING,
                )
            session.commit()

    def _execute_reindex_job(self, *, claimed: _ClaimedIndexJob, started_perf: float) -> None:
        target = str(claimed.payload_json.get("target") or "full").strip().lower()
        force_rechunk = bool(claimed.payload_json.get("force_rechunk", target == "full"))
        include_synthetic = bool(claimed.payload_json.get("include_synthetic", False))
        raw_ids = claimed.payload_json.get("evidence_ids") or []
        requested_ids: list[uuid.UUID] | None = None
        if raw_ids:
            requested_ids = []
            for raw_id in raw_ids:
                try:
                    requested_ids.append(uuid.UUID(str(raw_id)))
                except ValueError:
                    continue

        with self._session_factory() as session:
            target_ids = EvidenceChunkRepository(session).list_project_evidence_ids_for_reindex(
                project_id=claimed.project_id,
                evidence_ids=requested_ids,
                include_synthetic=include_synthetic,
            )

        indexed_count = 0
        partial_count = 0
        failed_count = 0
        skipped_count = 0
        total_chunks = 0
        total_vectors = 0
        last_retryable_code: str | None = None
        last_retryable_msg: str | None = None
        has_retryable_failure = False

        for ev_id in target_ids:
            res = self._index_single_evidence_item(
                evidence_id=ev_id,
                target=target,
                force_rechunk=force_rechunk,
            )
            total_chunks += res.chunk_count
            total_vectors += res.vectors_upserted
            if res.status == "indexed":
                indexed_count += 1
            elif res.status == "partially_indexed":
                partial_count += 1
                if res.retryable:
                    has_retryable_failure = True
                    last_retryable_code = res.error_code
                    last_retryable_msg = res.error_message
            elif res.status == "failed":
                failed_count += 1
                if res.retryable:
                    has_retryable_failure = True
                    last_retryable_code = res.error_code
                    last_retryable_msg = res.error_message
            else:
                skipped_count += 1

        elapsed_ms = int((time.perf_counter() - started_perf) * 1000)
        now = utc_now()
        with self._session_factory() as session:
            job = BackgroundJobRepository(session).get_by_id(claimed.job_id)
            audit = AuditService(audit_repository=AuditLogRepository(session))
            if job is None:
                return

            result_summary = {
                "target": target,
                "force_rechunk": force_rechunk,
                "target_items": len(target_ids),
                "indexed_items": indexed_count,
                "partially_indexed_items": partial_count,
                "failed_items": failed_count,
                "skipped_items": skipped_count,
                "total_chunks": total_chunks,
                "total_vectors_upserted": total_vectors,
                "embedding_model": self._embedding.model_name,
                "index_version": self._vector_store.index_version,
            }

            if (
                has_retryable_failure
                and claimed.attempt_count < claimed.max_attempts
                and target != "fts_only"
            ):
                backoff = min(
                    3600,
                    self._settings.worker_retry_base_seconds
                    * (2 ** max(0, claimed.attempt_count - 1)),
                )
                job.status = BackgroundJobStatus.QUEUED.value
                job.next_retry_at = now + timedelta(seconds=backoff)
                job.locked_by = None
                job.lease_expires_at = None
                job.error_code = (last_retryable_code or "VECTOR_SYNC_RETRYABLE")[:64]
                job.error_message = _sanitise_error(
                    last_retryable_msg or "Reindex encountered a retryable vector error."
                )
                job.result_json = result_summary
                audit.record_event(
                    event_type="evidence.reindex_retry_scheduled",
                    resource_type="project",
                    actor_user_id=None,
                    organisation_id=claimed.organisation_id,
                    project_id=claimed.project_id,
                    resource_id=str(claimed.project_id),
                    outcome=AuditOutcome.ERROR.value,
                    metadata={**result_summary, "job_id": str(job.id)},
                    message="Scheduled retry for project reindex due to transient vector error.",
                    level=logging.WARNING,
                )
                session.commit()
                return

            has_errors = (failed_count > 0) or (partial_count > 0 and target != "fts_only")
            if has_errors and indexed_count == 0 and len(target_ids) > 0:
                job.status = BackgroundJobStatus.FAILED.value
                job.error_code = (last_retryable_code or "REINDEX_INCOMPLETE")[:64]
                job.error_message = _sanitise_error(
                    last_retryable_msg
                    or "Project reindex completed with vector indexing failures."
                )
            else:
                job.status = BackgroundJobStatus.SUCCEEDED.value
                job.error_code = None
                job.error_message = None

            job.completed_at = now
            job.duration_ms = elapsed_ms
            job.locked_by = None
            job.lease_expires_at = None
            job.result_json = result_summary
            audit.record_event(
                event_type="evidence.reindex_completed",
                resource_type="project",
                actor_user_id=None,
                organisation_id=claimed.organisation_id,
                project_id=claimed.project_id,
                resource_id=str(claimed.project_id),
                outcome=AuditOutcome.ERROR.value if has_errors else AuditOutcome.SUCCESS.value,
                metadata={**result_summary, "job_id": str(job.id), "duration_ms": elapsed_ms},
                message=(
                    f"Completed project reindex ({indexed_count}/{len(target_ids)} indexed)."
                ),
            )
            session.commit()

    def _index_single_evidence_item(
        self,
        *,
        evidence_id: uuid.UUID,
        target: str,
        force_rechunk: bool,
    ) -> _ItemIndexOutcome:
        """Chunk + PG FTS (phase 1) then embed + Chroma upsert (phase 2) with isolation."""
        collection_name = self._vector_store.collection_name
        chunks_snapshot: list[tuple[uuid.UUID, int, str, str, str, datetime | None]] = []
        ev_meta_ctx: dict[str, Any] = {}
        obsolete_vector_ids: list[str] = []

        # Phase 1: Chunking + Canonical PG Persistence (committed before external network calls)
        try:
            with self._session_factory() as session:
                ev_repo = EvidenceRepository(session)
                chunk_repo = EvidenceChunkRepository(session)
                ev = ev_repo.get_by_id_detail(evidence_id, include_deleted=False)
                if ev is None or ev.processing_status not in _ELIGIBLE_PROCESSING_STATUSES:
                    return _ItemIndexOutcome(status="skipped", chunk_count=0, vectors_upserted=0)

                existing_chunks = chunk_repo.list_chunks_for_evidence(ev.id)
                should_rechunk = force_rechunk or (not existing_chunks) or target == "full"

                if target == "fts_only" and existing_chunks and not force_rechunk:
                    chunk_repo.rebuild_pg_fts_for_evidence(evidence=ev)
                    active_chunks = chunk_repo.list_chunks_for_evidence(ev.id)
                    ev.chunk_count = len(active_chunks)
                    ev.index_version = self._vector_store.index_version
                    session.commit()
                    has_all_vectors = all(
                        c.indexing_status == ChunkIndexingStatus.INDEXED.value
                        for c in active_chunks
                    )
                    return _ItemIndexOutcome(
                        status="indexed" if has_all_vectors else "partially_indexed",
                        chunk_count=len(active_chunks),
                        vectors_upserted=0,
                    )

                if should_rechunk:
                    drafts = self._chunking.chunk_evidence(ev)
                    active_chunks, obsolete_vector_ids = chunk_repo.replace_chunks_for_evidence(
                        evidence=ev,
                        drafts=drafts,
                        collection_name=collection_name,
                    )
                    if existing_chunks:
                        KnowledgeRepository(session).mark_stale_for_evidence(
                            evidence_id=ev.id,
                            reason="evidence_chunks_replaced",
                            now=utc_now(),
                        )
                else:
                    active_chunks = existing_chunks

                ev.chunk_count = len(active_chunks)
                ev.index_version = self._vector_store.index_version
                ev.index_error_code = None
                ev.index_error_message = None

                if not active_chunks:
                    ev.indexing_status = EvidenceIndexingStatus.INDEXED.value
                    ev.indexed_at = utc_now()
                    ev.embedding_model = self._embedding.model_name
                    session.commit()
                    # Clean up any residual vectors in Chroma best-effort
                    try:
                        self._vector_store.delete_records(where={"evidence_id": str(ev.id)})
                        if obsolete_vector_ids:
                            self._vector_store.delete_records(ids=obsolete_vector_ids)
                    except VectorStoreError:
                        logger.warning(
                            "Best-effort Chroma cleanup for zero-chunk evidence failed.",
                            extra={"evidence_id": str(ev.id)},
                        )
                    return _ItemIndexOutcome(status="indexed", chunk_count=0, vectors_upserted=0)

                if target == "fts_only":
                    ev.indexing_status = EvidenceIndexingStatus.PARTIALLY_INDEXED.value
                    chunk_repo.mark_chunks_vector_results(
                        chunks=active_chunks,
                        indexing_status=ChunkIndexingStatus.PARTIALLY_INDEXED.value,
                        collection_name=collection_name,
                    )
                    session.commit()
                    return _ItemIndexOutcome(
                        status="partially_indexed",
                        chunk_count=len(active_chunks),
                        vectors_upserted=0,
                    )

                chunks_snapshot = [
                    (
                        c.id,
                        int(c.chunk_index),
                        c.chroma_vector_id
                        or build_deterministic_vector_id(
                            evidence_id=ev.id,
                            chunk_index=int(c.chunk_index),
                        ),
                        c.chunk_text,
                        c.chunk_type,
                        c.source_created_at,
                    )
                    for c in active_chunks
                ]
                ev_meta_ctx = {
                    "organisation_id": str(ev.organisation_id),
                    "project_id": str(ev.project_id),
                    "evidence_id": str(ev.id),
                    "source_type": ev.source_type,
                    "category": ev.category,
                    "acl_scope": ev.acl_scope,
                    "permission_scope_key": resolve_permission_scope_key(
                        acl_scope=ev.acl_scope,
                        source_access_policy_id=ev.source_access_policy_id,
                    ),
                    "source_access_policy_id": (
                        str(ev.source_access_policy_id) if ev.source_access_policy_id else None
                    ),
                    "uploaded_by_user_id": (
                        str(ev.uploaded_by_user_id) if ev.uploaded_by_user_id else None
                    ),
                    "is_synthetic": EvidenceChunkRepository.is_item_synthetic(ev),
                    "evidence_source_created_at": ev.source_created_at,
                }
                session.commit()
        except Exception as exc:
            logger.exception("Chunking/PG FTS persistence failed for evidence item.")
            with self._session_factory() as err_session:
                ev = EvidenceRepository(err_session).get_by_id(evidence_id, include_deleted=False)
                if ev is not None:
                    ev.indexing_status = EvidenceIndexingStatus.FAILED.value
                    ev.index_error_code = "CHUNKING_FAILED"
                    ev.index_error_message = _sanitise_error(
                        f"Chunking error: {type(exc).__name__}"
                    )
                    err_session.commit()
            return _ItemIndexOutcome(
                status="failed",
                chunk_count=0,
                vectors_upserted=0,
                retryable=False,
                error_code="CHUNKING_FAILED",
                error_message=f"Chunking error: {type(exc).__name__}",
            )

        # Phase 2: Generate embeddings + Upsert to ChromaDB (keeping PG FTS intact on outage)
        try:
            texts = [row[3] for row in chunks_snapshot]
            vectors = self._embedding.embed_documents(texts)
            if len(vectors) != len(chunks_snapshot):
                raise EmbeddingExecutionError(
                    code="EMBEDDING_COUNT_MISMATCH",
                    message="Generated embedding count did not match chunk count.",
                    retryable=True,
                )

            self._vector_store.ensure_collection()
            # Purge any prior vectors for this evidence item to guarantee no orphaned chunk indices
            self._vector_store.delete_records(where={"evidence_id": str(evidence_id)})
            if obsolete_vector_ids:
                self._vector_store.delete_records(ids=obsolete_vector_ids)

            records: list[VectorUpsertRecord] = []
            for (c_id, c_idx, vec_id, _text, c_type, c_dt), vec in zip(
                chunks_snapshot,
                vectors,
                strict=True,
            ):
                eff_dt = c_dt or ev_meta_ctx["evidence_source_created_at"]
                eff_ts: int | None = None
                if isinstance(eff_dt, datetime):
                    aware_dt = (
                        eff_dt.replace(tzinfo=UTC)
                        if eff_dt.tzinfo is None
                        else eff_dt.astimezone(UTC)
                    )
                    eff_ts = int(aware_dt.timestamp())
                records.append(
                    VectorUpsertRecord(
                        vector_id=vec_id,
                        embedding=vec,
                        metadata=sanitize_vector_metadata(
                            {
                                "organisation_id": ev_meta_ctx["organisation_id"],
                                "project_id": ev_meta_ctx["project_id"],
                                "evidence_id": ev_meta_ctx["evidence_id"],
                                "chunk_id": str(c_id),
                                "chunk_index": c_idx,
                                "chunk_type": c_type,
                                "source_type": ev_meta_ctx["source_type"],
                                "category": ev_meta_ctx["category"],
                                "acl_scope": ev_meta_ctx["acl_scope"],
                                "permission_scope_key": ev_meta_ctx["permission_scope_key"],
                                "source_access_policy_id": ev_meta_ctx["source_access_policy_id"],
                                "uploaded_by_user_id": ev_meta_ctx["uploaded_by_user_id"],
                                "is_synthetic": ev_meta_ctx["is_synthetic"],
                                "source_created_ts": eff_ts,
                            }
                        ),
                    )
                )

            vector_error: Any = None
            try:
                for batch_start in range(0, len(records), 64):
                    self._vector_store.upsert_records(records[batch_start : batch_start + 64])
            except (EmbeddingExecutionError, VectorStoreError) as exc:
                vector_error = exc
                self._record_partial_vector_failure(
                    evidence_id=evidence_id,
                    collection_name=collection_name,
                    error_code=exc.code,
                    error_message=exc.message,
                )
        except Exception as exc:  # Catch other unexpected vector errors
            vector_error = exc
            logger.warning("Vector indexing encountered unexpected issue: %s", exc)

        # Phase 3: Mark canonical chunks & parent EvidenceItem (allow downstream extraction regardless)
        now = utc_now()
        with self._session_factory() as session:
            ev_repo = EvidenceRepository(session)
            chunk_repo = EvidenceChunkRepository(session)
            ev = ev_repo.get_by_id(evidence_id, include_deleted=False)
            if ev is None:
                return _ItemIndexOutcome(
                    status="skipped",
                    chunk_count=len(chunks_snapshot),
                    vectors_upserted=len(chunks_snapshot) if vector_error is None else 0,
                )
            chunks = chunk_repo.list_chunks_for_evidence(ev.id)
            if vector_error is None:
                chunk_repo.mark_chunks_vector_results(
                    chunks=chunks,
                    indexing_status=ChunkIndexingStatus.INDEXED.value,
                    collection_name=collection_name,
                    embedding_model=self._embedding.model_name,
                    embedding_dimensions=self._embedding.expected_dimensions,
                    embedded_at=now,
                    error_code=None,
                    error_message=None,
                )
                ev.indexing_status = EvidenceIndexingStatus.INDEXED.value
                ev.index_error_code = None
                ev.index_error_message = None
            else:
                ev.indexing_status = EvidenceIndexingStatus.PARTIALLY_INDEXED.value
                ev.index_error_code = getattr(vector_error, "code", "VECTOR_STORE_ERROR")
                ev.index_error_message = str(getattr(vector_error, "message", vector_error))

            ev.chunk_count = len(chunks)
            ev.indexed_at = now
            ev.embedding_model = self._embedding.model_name
            ev.index_version = self._vector_store.index_version
            meta = dict(ev.metadata_json or {})
            if meta.get("lifecycle_stage") in (None, "discovered", "imported", "indexing"):
                meta["lifecycle_stage"] = "indexed"
            ev.metadata_json = meta

            if chunks and self._extraction_settings is not None:
                from app.services.fast_extractor import is_evidence_semantic_eligible

                text_len = max(
                    sum(len(c.chunk_text or "") for c in chunks),
                    int(ev.file_size_bytes or 0),
                )
                is_semantic_eligible = is_evidence_semantic_eligible(
                    category=ev.category,
                    title=ev.title,
                    mime_type=ev.mime_type,
                    text_len=text_len,
                    metadata_json=ev.metadata_json,
                )
                is_not_applicable = (
                    (ev.metadata_json or {}).get("semantic_status") == "not_applicable"
                ) or (not is_semantic_eligible)

                if is_not_applicable and (ev.metadata_json or {}).get("semantic_status") != "not_applicable":
                    meta = dict(ev.metadata_json or {})
                    meta["semantic_status"] = "not_applicable"
                    ev.metadata_json = meta

                if not is_not_applicable:
                    k_repo = KnowledgeRepository(session)
                    job_repo = BackgroundJobRepository(session)

                    fp = (ev.metadata_json or {}).get("extraction_fingerprint")
                    has_matching_fingerprint = (
                        isinstance(fp, dict)
                        and fp.get("content_hash") == ev.content_hash
                    )
                    has_active_run = (
                        k_repo.get_active_run_for_evidence(
                            project_id=ev.project_id,
                            evidence_id=ev.id,
                        )
                        is not None
                    ) or job_repo.has_active_job_for_evidence(
                        evidence_id=ev.id,
                        job_type=BackgroundJobType.KNOWLEDGE_RECONSTRUCTION.value,
                    )
                    has_stale = k_repo.has_stale_items_for_evidence(ev.id, semantic_only=True)
                    is_unchanged = has_matching_fingerprint and not has_stale

                    # State machine handling per Step 1 specification:
                    # - Unchanged, successfully processed evidence: skip inference
                    # - Already active run: skip duplicate scheduling
                    if not is_unchanged and not has_active_run:
                        has_prior_knowledge = k_repo.has_items_for_evidence(ev.id, semantic_only=True)
                        has_completed_run = (
                            session.execute(
                                select(KnowledgeExtractionRun.id).where(
                                    KnowledgeExtractionRun.evidence_id == ev.id,
                                    KnowledgeExtractionRun.status.in_(
                                        [
                                            ExtractionRunStatus.COMPLETED.value,
                                            ExtractionRunStatus.PARTIALLY_COMPLETED.value,
                                        ]
                                    ),
                                )
                            ).scalar_one_or_none()
                            is not None
                        )

                        is_new_evidence = (
                            fp is None and not has_prior_knowledge and not has_completed_run
                        )
                        is_changed_evidence = (
                            (fp is not None and fp.get("content_hash") != ev.content_hash)
                            or has_stale
                        )

                        # Step 1 Mandate:
                        # 1. New evidence, never semantically processed: ALWAYS schedule extraction (do NOT gate on auto_reextract_on_update)
                        # 2. Changed evidence with an outdated content fingerprint: schedule according to auto_reextract_on_update
                        should_schedule = is_new_evidence or (
                            is_changed_evidence
                            and self._extraction_settings.auto_reextract_on_update
                        )

                        if should_schedule:
                            categories = [c.value for c in KnowledgeCategory]
                            is_synth = EvidenceChunkRepository.is_item_synthetic(ev)
                            auto_run = k_repo.create_extraction_run(
                                organisation_id=ev.organisation_id,
                                project_id=ev.project_id,
                                background_job_id=None,
                                evidence_id=ev.id,
                                triggered_by_user_id=ev.uploaded_by_user_id,
                                scope_type=ExtractionRunScope.EVIDENCE.value,
                                target_categories=categories,
                                model_name=self._llm_model_name,
                                prompt_version=self._extraction_settings.prompt_version,
                                is_synthetic=is_synth,
                                total_evidence_items=1,
                            )
                            auto_job = job_repo.create_job(
                                organisation_id=ev.organisation_id,
                                project_id=ev.project_id,
                                evidence_id=ev.id,
                                triggered_by_user_id=ev.uploaded_by_user_id,
                                job_type=BackgroundJobType.KNOWLEDGE_RECONSTRUCTION.value,
                                max_attempts=self._settings.worker_max_attempts,
                                priority=2,
                                payload_json={
                                    "run_id": str(auto_run.id),
                                    "scope_type": ExtractionRunScope.EVIDENCE.value,
                                    "evidence_ids": [str(ev.id)],
                                    "categories": categories,
                                    "force_rerun": False,
                                    "include_synthetic": is_synth,
                                    "trigger": "auto_new_evidence"
                                    if is_new_evidence
                                    else "auto_reextract_on_update",
                                },
                            )
                            auto_run.background_job_id = auto_job.id
                            meta = dict(ev.metadata_json or {})
                            meta["semantic_status"] = "queued"
                            ev.metadata_json = meta

            session.commit()
            try:
                from app.services.pipeline_coordinator import invalidate_project_status_cache

                invalidate_project_status_cache(ev.project_id)
            except Exception:
                pass
            try:
                from app.main import signal_worker_activity

                signal_worker_activity()
            except Exception:
                pass

        if vector_error is not None:
            return _ItemIndexOutcome(
                status="partially_indexed",
                chunk_count=len(chunks_snapshot),
                vectors_upserted=0,
                retryable=bool(getattr(vector_error, "retryable", True)),
                error_code=getattr(vector_error, "code", "VECTOR_STORE_ERROR"),
                error_message=str(getattr(vector_error, "message", vector_error)),
            )

        return _ItemIndexOutcome(
            status="indexed",
            chunk_count=len(chunks_snapshot),
            vectors_upserted=len(chunks_snapshot),
        )

    def _record_partial_vector_failure(
        self,
        *,
        evidence_id: uuid.UUID,
        collection_name: str,
        error_code: str,
        error_message: str,
    ) -> None:
        safe_code = error_code[:64]
        safe_msg = _sanitise_error(error_message)
        with self._session_factory() as session:
            ev = EvidenceRepository(session).get_by_id(evidence_id, include_deleted=False)
            if ev is None:
                return
            chunk_repo = EvidenceChunkRepository(session)
            chunks = chunk_repo.list_chunks_for_evidence(ev.id)
            chunk_repo.mark_chunks_vector_results(
                chunks=chunks,
                indexing_status=ChunkIndexingStatus.PARTIALLY_INDEXED.value,
                collection_name=collection_name,
                error_code=safe_code,
                error_message=safe_msg,
            )
            ev.indexing_status = (
                EvidenceIndexingStatus.PARTIALLY_INDEXED.value
                if chunks
                else EvidenceIndexingStatus.FAILED.value
            )
            ev.chunk_count = len(chunks)
            ev.index_error_code = safe_code
            ev.index_error_message = safe_msg
            session.commit()

    def _fail_job_only(
        self,
        *,
        claimed: _ClaimedIndexJob,
        duration_ms: int,
        error_code: str,
        error_message: str,
        retryable: bool,
    ) -> None:
        now = utc_now()
        safe_code = error_code[:64]
        safe_msg = _sanitise_error(error_message)
        with self._session_factory() as session:
            job = BackgroundJobRepository(session).get_by_id(claimed.job_id)
            if job is None:
                return
            if retryable:
                backoff = min(
                    3600,
                    self._settings.worker_retry_base_seconds
                    * (2 ** max(0, claimed.attempt_count - 1)),
                )
                job.status = BackgroundJobStatus.QUEUED.value
                job.next_retry_at = now + timedelta(seconds=backoff)
                job.locked_by = None
                job.lease_expires_at = None
                job.error_code = safe_code
                job.error_message = safe_msg
            else:
                job.status = BackgroundJobStatus.FAILED.value
                job.completed_at = now
                job.duration_ms = duration_ms
                job.locked_by = None
                job.lease_expires_at = None
                job.error_code = safe_code
                job.error_message = safe_msg
            session.commit()
