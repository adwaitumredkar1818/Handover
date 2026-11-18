"""Universal Evidence-to-Knowledge Pipeline Coordinator.

Orchestrates automatic end-to-end background evidence processing, progress monitoring,
and state reporting across all connected evidence sources (Uploads, GitHub, Jira, Slack).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from app.core.security import utc_now
from app.models.enums import (
    BackgroundJobStatus,
    BackgroundJobType,
    EvidenceCategory,
    EvidenceIndexingStatus,
    EvidenceProcessingStatus,
    ExtractionRunScope,
    ExtractionRunStatus,
    KnowledgeCategory,
)
from app.models.evidence import EvidenceContent, EvidenceItem
from app.models.job import BackgroundJob
from app.models.knowledge import KnowledgeEvidenceLink, KnowledgeExtractionRun, KnowledgeItem
from app.models.relationship import KnowledgeEntity, KnowledgeRelationship
from app.repositories.evidence import EvidenceRepository
from app.repositories.job import BackgroundJobRepository
from app.repositories.knowledge import KnowledgeRepository

logger = logging.getLogger("app.services.pipeline_coordinator")

# Mapping of active background job types to user-facing stages
_STAGE_MAPPING: dict[str, tuple[str, str]] = {
    BackgroundJobType.DOCUMENT_INGESTION.value: (
        "parsing",
        "Parsing and extracting text from documents",
    ),
    BackgroundJobType.SOURCE_SYNC.value: (
        "syncing",
        "Syncing evidence from connected source",
    ),
    BackgroundJobType.EVIDENCE_INDEXING.value: (
        "indexing",
        "Indexing evidence and generating embeddings",
    ),
    BackgroundJobType.EVIDENCE_CHUNKING.value: (
        "indexing",
        "Preparing evidence chunks",
    ),
    BackgroundJobType.EVIDENCE_EMBEDDING.value: (
        "indexing",
        "Generating nomic-embed-text vector embeddings",
    ),
    BackgroundJobType.EVIDENCE_REINDEXING.value: (
        "indexing",
        "Rebuilding project evidence vector index",
    ),
    BackgroundJobType.KNOWLEDGE_RECONSTRUCTION.value: (
        "extracting_knowledge",
        "Extracting knowledge using Ollama (qwen3:8b)",
    ),
    BackgroundJobType.RELATIONSHIP_RECONSTRUCTION.value: (
        "reconstructing_graphs",
        "Reconstructing project relationships and graph projections",
    ),
}

_STAGE_PRIORITY = [
    "reconstructing_graphs",
    "extracting_knowledge",
    "indexing",
    "parsing",
    "syncing",
]

_CANONICAL_KNOWLEDGE_CATEGORIES = [
    KnowledgeCategory.PROJECT_OVERVIEW_CONTEXT.value,
    KnowledgeCategory.DECISIONS_RATIONALE.value,
    KnowledgeCategory.WORK_ITEMS.value,
    KnowledgeCategory.RESPONSIBILITIES_OWNERSHIP.value,
    KnowledgeCategory.TECHNICAL_ARCHITECTURE.value,
    KnowledgeCategory.BUGS_BLOCKERS_RISKS.value,
    KnowledgeCategory.DEPENDENCIES.value,
    KnowledgeCategory.OPERATIONAL_HISTORICAL.value,
]


class ProjectProcessingStatus(BaseModel):
    state: str  # no_evidence, queued, processing, partially_ready, ready, failed, insufficient_evidence
    state_label: str
    is_processing: bool
    stage: str | None
    stage_label: str | None
    total_evidence_count: int
    processed_evidence_count: int
    queued_evidence_count: int
    failed_evidence_count: int
    has_existing_graphs: bool
    knowledge_item_count: int
    entity_count: int
    relationship_count: int
    last_reconstructed_at: datetime | None
    error_message: str | None
    updated_at: datetime
    graph_version: str | None = None
    stage_counts: dict[str, int] = Field(default_factory=dict)

    # Explicit two-stage pipeline counts
    total_imported: int = 0
    deterministic_ready: int = 0
    semantic_queued: int = 0
    semantic_extracting: int = 0
    semantic_ready: int = 0
    graph_published: int = 0
    failed: int = 0
    not_applicable: int = 0
    item_states: dict[str, dict[str, Any]] = Field(default_factory=dict)


_STATUS_CACHE: dict[uuid.UUID, tuple[float, ProjectProcessingStatus]] = {}
_STATUS_CACHE_TTL_SECONDS = 1.5


def invalidate_project_status_cache(project_id: uuid.UUID) -> None:
    """Clear short-lived processing status cache immediately when items/batches commit."""
    _STATUS_CACHE.pop(project_id, None)


class PipelineCoordinatorService:
    """Coordinates automatic execution and observability of the universal evidence-to-knowledge pipeline."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_status(self, project_id: uuid.UUID) -> ProjectProcessingStatus:
        """Compute the current real-time processing status of a project from PostgreSQL records."""
        now = utc_now()

        # 1. Query evidence item counts
        ev_counts = dict(
            self.session.execute(
                select(EvidenceItem.processing_status, func.count(EvidenceItem.id))
                .where(
                    EvidenceItem.project_id == project_id,
                    EvidenceItem.deleted_at.is_(None),
                )
                .group_by(EvidenceItem.processing_status)
            ).all()
        )

        total_ev = sum(ev_counts.values())
        failed_ev = ev_counts.get(EvidenceProcessingStatus.FAILED.value, 0)
        extracted_ev = (
            ev_counts.get(EvidenceProcessingStatus.EXTRACTED.value, 0)
            + ev_counts.get(EvidenceProcessingStatus.PARTIALLY_EXTRACTED.value, 0)
        )
        queued_ev = (
            ev_counts.get(EvidenceProcessingStatus.PENDING.value, 0)
            + ev_counts.get(EvidenceProcessingStatus.QUEUED.value, 0)
        )

        # 2. Query active jobs for project (column projection to avoid JSON payload overhead)
        active_jobs = (
            self.session.execute(
                select(BackgroundJob.status, BackgroundJob.job_type)
                .where(
                    BackgroundJob.project_id == project_id,
                    BackgroundJob.status.in_(
                        [BackgroundJobStatus.QUEUED.value, BackgroundJobStatus.RUNNING.value]
                    ),
                )
                .order_by(BackgroundJob.created_at.desc())
            )
            .all()
        )

        running_jobs = [j for j in active_jobs if j.status == BackgroundJobStatus.RUNNING.value]
        has_active_jobs = len(active_jobs) > 0
        is_running = len(running_jobs) > 0

        # Determine current stage
        current_stage: str | None = None
        current_stage_label: str | None = None
        if active_jobs:
            target_job = running_jobs[0] if running_jobs else active_jobs[0]
            stage_tuple = _STAGE_MAPPING.get(target_job.job_type)
            if stage_tuple:
                current_stage, current_stage_label = stage_tuple
            else:
                current_stage = "processing"
                current_stage_label = f"Processing {target_job.job_type}"

        # 3. Query active knowledge items, entities and relationships + max updated_at timestamps
        counts_row = self.session.execute(
            select(
                select(func.count(KnowledgeItem.id))
                .where(
                    KnowledgeItem.project_id == project_id,
                    KnowledgeItem.deleted_at.is_(None),
                    KnowledgeItem.is_deleted.is_(False),
                    KnowledgeItem.is_stale.is_(False),
                )
                .scalar_subquery()
                .label("k_count"),
                select(func.max(KnowledgeItem.updated_at))
                .where(KnowledgeItem.project_id == project_id)
                .scalar_subquery()
                .label("k_max_upd"),
                select(func.count(KnowledgeEntity.id))
                .where(
                    KnowledgeEntity.project_id == project_id,
                    KnowledgeEntity.is_deleted.is_(False),
                    KnowledgeEntity.is_stale.is_(False),
                )
                .scalar_subquery()
                .label("entity_count"),
                select(func.max(KnowledgeEntity.updated_at))
                .where(KnowledgeEntity.project_id == project_id)
                .scalar_subquery()
                .label("e_max_upd"),
                select(func.count(KnowledgeRelationship.id))
                .where(
                    KnowledgeRelationship.project_id == project_id,
                    KnowledgeRelationship.is_stale.is_(False),
                )
                .scalar_subquery()
                .label("rel_count"),
                select(func.max(KnowledgeRelationship.updated_at))
                .where(KnowledgeRelationship.project_id == project_id)
                .scalar_subquery()
                .label("r_max_upd"),
            )
        ).one()
        k_count = counts_row.k_count or 0
        entity_count = counts_row.entity_count or 0
        rel_count = counts_row.rel_count or 0
        k_ts = counts_row.k_max_upd.isoformat() if counts_row.k_max_upd else ""
        e_ts = counts_row.e_max_upd.isoformat() if counts_row.e_max_upd else ""
        r_ts = counts_row.r_max_upd.isoformat() if counts_row.r_max_upd else ""

        has_existing_graphs = (entity_count > 0 and rel_count > 0) or k_count > 0

        # 4. Find timestamp of last successful reconstruction
        last_reconstructed_at = (
            self.session.execute(
                select(KnowledgeExtractionRun.completed_at)
                .where(
                    KnowledgeExtractionRun.project_id == project_id,
                    KnowledgeExtractionRun.status == ExtractionRunStatus.COMPLETED.value,
                )
                .order_by(KnowledgeExtractionRun.completed_at.desc())
                .limit(1)
            )
            .scalar_one_or_none()
        )

        # 5. Check recent error message if any
        error_message: str | None = None
        if failed_ev > 0:
            error_message = (
                self.session.execute(
                    select(EvidenceItem.error_message)
                    .where(
                        EvidenceItem.project_id == project_id,
                        EvidenceItem.processing_status == EvidenceProcessingStatus.FAILED.value,
                        EvidenceItem.deleted_at.is_(None),
                    )
                    .order_by(EvidenceItem.updated_at.desc())
                    .limit(1)
                )
                .scalar_one_or_none()
            )

        if not error_message and not has_active_jobs:
            error_message = (
                self.session.execute(
                    select(BackgroundJob.error_message)
                    .where(
                        BackgroundJob.project_id == project_id,
                        BackgroundJob.status == BackgroundJobStatus.FAILED.value,
                    )
                    .order_by(BackgroundJob.completed_at.desc())
                    .limit(1)
                )
                .scalar_one_or_none()
            )

        # 6. Compute per-evidence stage breakdown, individual item_states, & accurately completed count
        ev_items = self.session.execute(
            select(
                EvidenceItem.id,
                EvidenceItem.metadata_json,
                EvidenceItem.indexing_status,
                EvidenceItem.processing_status,
            )
            .where(
                EvidenceItem.project_id == project_id,
                EvidenceItem.deleted_at.is_(None),
            )
        ).all()

        stage_counts: dict[str, int] = {
            "discovered": 0,
            "imported": 0,
            "indexing": 0,
            "indexed": 0,
            "extracting": 0,
            "knowledge_ready": 0,
            "graph_updated": 0,
            "failed": 0,
            "not_applicable": 0,
        }
        item_states: dict[str, dict[str, Any]] = {}
        actually_processed_count = 0

        # Two-stage pipeline metrics
        deterministic_ready_cnt = 0
        semantic_queued_cnt = 0
        semantic_extracting_cnt = 0
        semantic_ready_cnt = 0
        graph_published_cnt = 0
        failed_cnt = 0
        not_applicable_cnt = 0

        for row in ev_items:
            m = row.metadata_json or {}
            st = m.get("lifecycle_stage")
            sem = m.get("semantic_status")
            has_det = "deterministic_fingerprint" in m
            if has_det:
                deterministic_ready_cnt += 1

            if sem == "queued":
                semantic_queued_cnt += 1
            elif sem in ("extracting", "running", "processing"):
                semantic_extracting_cnt += 1
            elif sem in ("completed", "succeeded", "ready"):
                semantic_ready_cnt += 1
            elif sem == "not_applicable":
                not_applicable_cnt += 1

            if st in ("graph_published", "graph_updated"):
                graph_published_cnt += 1

            if not st:
                if row.processing_status == "failed" or row.indexing_status == "failed":
                    st = "failed"
                elif row.indexing_status == "processing":
                    st = "indexing"
                elif row.indexing_status in ("indexed", "partially_indexed"):
                    st = "graph_updated" if m.get("knowledge_count", 0) > 0 else "indexed"
                elif row.processing_status == "extracted":
                    st = "imported"
                else:
                    st = "discovered"

            if st == "failed" or row.processing_status == "failed" or row.indexing_status == "failed":
                failed_cnt += 1

            stage_counts[st] = stage_counts.get(st, 0) + 1
            item_states[str(row.id)] = {
                "lifecycle_stage": st,
                "semantic_status": sem or "not_applicable",
                "processing_status": row.processing_status,
                "indexing_status": row.indexing_status,
                "knowledge_count": int(m.get("knowledge_count", 0)),
            }

            # Completed all applicable stages:
            # 1. Produced knowledge and graph was updated
            # 2. Or deterministic/indexing completed and semantic extraction was not applicable
            if st in ("graph_updated", "graph_published", "knowledge_ready") or (
                st in ("indexed", "deterministic_ready") and sem == "not_applicable"
            ):
                actually_processed_count += 1

        graph_version = (
            f"{k_count}:{entity_count}:{rel_count}:{k_ts}:{e_ts}:{r_ts}:"
            f"{last_reconstructed_at.isoformat() if last_reconstructed_at else ''}"
        )

        # Recover stranded queued indexing work when no active job exists for this project
        has_stranded_unindexed = any(
            r.indexing_status in ("not_indexed", "queued", "partially_indexed") for r in ev_items
        )
        if semantic_queued_cnt > 0 and not has_active_jobs and has_stranded_unindexed:
            try:
                scheduled = self.trigger_auto_pipeline(project_id=project_id)
                if scheduled > 0:
                    has_active_jobs = True
                    current_stage = "indexing"
                    current_stage_label = "Indexing evidence and generating embeddings"
            except Exception as exc:
                logger.warning("Stranded pipeline auto-recovery notice for project %s: %s", project_id, exc)

        # 7. Compute canonical state
        if total_ev == 0:
            state = "no_evidence"
            state_label = "No evidence connected"
            is_processing = False
        elif is_running:
            state = "processing"
            state_label = "Processing evidence"
            is_processing = True
        elif has_active_jobs:
            state = "queued"
            state_label = "Queued for processing"
            is_processing = True
        elif failed_ev == total_ev:
            state = "failed"
            state_label = "Processing failed"
            is_processing = False
        elif k_count == 0 and rel_count == 0 and total_ev > 0:
            state = "insufficient_evidence"
            state_label = "Insufficient extractable evidence"
            is_processing = False
        elif failed_ev > 0:
            state = "partially_ready"
            state_label = "Partially ready"
            is_processing = False
        else:
            state = "ready"
            state_label = "Ready"
            is_processing = False

        return ProjectProcessingStatus(
            state=state,
            state_label=state_label,
            is_processing=is_processing,
            stage=current_stage,
            stage_label=current_stage_label,
            total_evidence_count=total_ev,
            processed_evidence_count=actually_processed_count,
            queued_evidence_count=queued_ev + len(active_jobs),
            failed_evidence_count=failed_ev,
            has_existing_graphs=has_existing_graphs,
            knowledge_item_count=k_count,
            entity_count=entity_count,
            relationship_count=rel_count,
            last_reconstructed_at=last_reconstructed_at,
            error_message=error_message,
            updated_at=now,
            graph_version=graph_version,
            stage_counts=stage_counts,
            total_imported=total_ev,
            deterministic_ready=deterministic_ready_cnt,
            semantic_queued=semantic_queued_cnt,
            semantic_extracting=semantic_extracting_cnt,
            semantic_ready=semantic_ready_cnt,
            graph_published=graph_published_cnt,
            failed=failed_cnt,
            not_applicable=not_applicable_cnt,
            item_states=item_states,
        )

    def trigger_auto_pipeline(
        self,
        project_id: uuid.UUID,
        triggered_by_user_id: uuid.UUID | None = None,
        force_reextract: bool = False,
    ) -> int:
        """Ensure all eligible evidence items enter the background pipeline automatically.

        Creates indexing or reconstruction jobs for any items that need them, then signals the worker.
        Returns the number of jobs scheduled.
        """
        now = utc_now()
        job_repo = BackgroundJobRepository(self.session)
        evidence_repo = EvidenceRepository(self.session)
        knowledge_repo = KnowledgeRepository(self.session)

        # 1. Find evidence items for project
        items = (
            self.session.execute(
                select(EvidenceItem).where(
                    EvidenceItem.project_id == project_id,
                    EvidenceItem.deleted_at.is_(None),
                )
            )
            .scalars()
            .all()
        )

        jobs_scheduled = 0
        needs_reconstruction_ev_ids: list[uuid.UUID] = []

        # Batch load active jobs for project (eliminates N+1 queries)
        active_index_job_types = {
            BackgroundJobType.EVIDENCE_INDEXING.value,
            BackgroundJobType.EVIDENCE_REINDEXING.value,
            BackgroundJobType.EVIDENCE_CHUNKING.value,
            BackgroundJobType.EVIDENCE_EMBEDDING.value,
        }
        active_job_rows = self.session.execute(
            select(BackgroundJob.evidence_id, BackgroundJob.job_type, BackgroundJob.payload_json).where(
                BackgroundJob.project_id == project_id,
                BackgroundJob.status.in_(
                    [BackgroundJobStatus.QUEUED.value, BackgroundJobStatus.RUNNING.value]
                ),
            )
        ).all()
        active_jobs_tuples = {(row[0], row[1]) for row in active_job_rows}
        active_index_ev_ids: set[uuid.UUID] = set()
        has_project_wide_reindex = False
        for row_ev_id, row_type, row_payload in active_job_rows:
            if row_type not in active_index_job_types:
                continue
            if row_ev_id is not None:
                active_index_ev_ids.add(row_ev_id)
            if row_type == BackgroundJobType.EVIDENCE_REINDEXING.value:
                raw_ids = (row_payload or {}).get("evidence_ids") or []
                if not raw_ids:
                    has_project_wide_reindex = True
                else:
                    for raw_id in raw_ids:
                        try:
                            active_index_ev_ids.add(uuid.UUID(str(raw_id)))
                        except ValueError:
                            continue

        char_counts_by_ev = dict(
            self.session.execute(
                select(EvidenceContent.evidence_id, EvidenceContent.char_count)
                .join(EvidenceItem, EvidenceItem.id == EvidenceContent.evidence_id)
                .where(
                    EvidenceItem.project_id == project_id,
                    EvidenceItem.deleted_at.is_(None),
                )
            ).all()
        )

        # Batch load evidence IDs that already have non-deleted knowledge items
        ev_ids_with_knowledge = set(
            self.session.execute(
                select(KnowledgeEvidenceLink.evidence_id)
                .join(KnowledgeItem, KnowledgeEvidenceLink.knowledge_item_id == KnowledgeItem.id)
                .where(
                    KnowledgeEvidenceLink.project_id == project_id,
                    KnowledgeItem.is_deleted == False,
                )
            )
            .scalars()
            .all()
        )

        # Batch load evidence IDs that have stale Stage-2 semantic knowledge items
        ev_ids_with_stale = set(
            self.session.execute(
                select(KnowledgeEvidenceLink.evidence_id)
                .join(KnowledgeItem, KnowledgeEvidenceLink.knowledge_item_id == KnowledgeItem.id)
                .where(
                    KnowledgeEvidenceLink.project_id == project_id,
                    KnowledgeItem.is_deleted == False,
                    KnowledgeItem.is_stale == True,
                    KnowledgeItem.extraction_run_id.is_not(None),
                )
            )
            .scalars()
            .all()
        )

        # Batch load evidence IDs with active extraction runs
        active_run_ev_ids = set(
            self.session.execute(
                select(KnowledgeExtractionRun.evidence_id).where(
                    KnowledgeExtractionRun.project_id == project_id,
                    KnowledgeExtractionRun.status.in_(
                        [ExtractionRunStatus.QUEUED.value, ExtractionRunStatus.RUNNING.value]
                    ),
                    KnowledgeExtractionRun.evidence_id.is_not(None),
                )
            )
            .scalars()
            .all()
        )

        from app.core.config import get_settings
        from app.services.fast_extractor import is_evidence_semantic_eligible

        settings = get_settings()
        active_prompt_version = settings.extraction.prompt_version
        active_model_name = getattr(settings.extraction, "llm_model_name", "qwen3:8b")

        # Batch load evidence IDs with completed extraction runs for model/prompt
        completed_run_ev_ids = knowledge_repo.get_extracted_evidence_ids_for_project(
            project_id=project_id,
            model_name=active_model_name,
            prompt_version=active_prompt_version,
        )

        reconcile_indexed_ids: list[uuid.UUID] = []
        queue_indexing_ids: list[uuid.UUID] = []
        queue_ingest_ids: list[uuid.UUID] = []

        for item in items:
            has_active_ingest = (item.id, BackgroundJobType.DOCUMENT_INGESTION.value) in active_jobs_tuples
            # If upload is pending/queued, queue ingestion
            if (
                item.source_type == "document_upload"
                and item.processing_status in (
                    EvidenceProcessingStatus.PENDING.value,
                    EvidenceProcessingStatus.QUEUED.value,
                )
                and not has_active_ingest
            ):
                job_repo.create_job(
                    organisation_id=item.organisation_id,
                    project_id=item.project_id,
                    evidence_id=item.id,
                    triggered_by_user_id=triggered_by_user_id,
                    job_type=BackgroundJobType.DOCUMENT_INGESTION.value,
                    priority=3,
                    flush=False,
                )
                queue_ingest_ids.append(item.id)
                jobs_scheduled += 1
                continue

            # If item is extracted or partially extracted, check indexing and semantic readiness
            if item.processing_status in (
                EvidenceProcessingStatus.EXTRACTED.value,
                EvidenceProcessingStatus.PARTIALLY_EXTRACTED.value,
            ):
                text_len = int(
                    char_counts_by_ev.get(item.id)
                    or item.file_size_bytes
                    or (100 if item.chunk_count > 0 else 0)
                )
                is_semantic_eligible = is_evidence_semantic_eligible(
                    category=item.category,
                    title=item.title,
                    mime_type=item.mime_type,
                    text_len=text_len,
                    metadata_json=item.metadata_json,
                )

                has_active_index = has_project_wide_reindex or (item.id in active_index_ev_ids)
                needs_indexing = item.indexing_status in (
                    EvidenceIndexingStatus.NOT_INDEXED.value,
                    EvidenceIndexingStatus.QUEUED.value,
                    EvidenceIndexingStatus.PARTIALLY_INDEXED.value,
                ) or (
                    item.indexing_status == EvidenceIndexingStatus.INDEXED.value
                    and item.chunk_count == 0
                    and text_len > 0
                )
                if needs_indexing:
                    if is_semantic_eligible:
                        if not has_active_index:
                            job_repo.create_job(
                                organisation_id=item.organisation_id,
                                project_id=item.project_id,
                                evidence_id=item.id,
                                triggered_by_user_id=triggered_by_user_id,
                                job_type=BackgroundJobType.EVIDENCE_INDEXING.value,
                                priority=1,
                                payload_json={
                                    "target": "full",
                                    "force_rechunk": True,
                                    "trigger": "pipeline_auto",
                                },
                                flush=False,
                            )
                            queue_indexing_ids.append(item.id)
                            jobs_scheduled += 1
                    else:
                        is_meta_not_app = (item.metadata_json or {}).get("semantic_status") == "not_applicable"
                        if (
                            is_meta_not_app
                            and item.indexing_status == EvidenceIndexingStatus.QUEUED.value
                            and not has_active_index
                        ):
                            reconcile_indexed_ids.append(item.id)
                        elif not has_active_index:
                            job_repo.create_job(
                                organisation_id=item.organisation_id,
                                project_id=item.project_id,
                                evidence_id=item.id,
                                triggered_by_user_id=triggered_by_user_id,
                                job_type=BackgroundJobType.EVIDENCE_INDEXING.value,
                                priority=9,
                                payload_json={
                                    "target": "full",
                                    "force_rechunk": True,
                                    "trigger": "pipeline_auto",
                                },
                                flush=False,
                            )
                            queue_indexing_ids.append(item.id)
                            jobs_scheduled += 1
                    # Never queue Qwen3 reconstruction before canonical chunks exist;
                    # IndexingWorkerService automatically triggers downstream reconstruction once indexed.
                    continue

                if item.indexing_status != EvidenceIndexingStatus.INDEXED.value or item.chunk_count == 0:
                    continue

                if not is_semantic_eligible or (item.metadata_json or {}).get("semantic_status") == "not_applicable":
                    item_meta = dict(item.metadata_json or {})
                    if item_meta.get("semantic_status") != "not_applicable":
                        item_meta["semantic_status"] = "not_applicable"
                        item.metadata_json = item_meta
                    continue

                # Check if knowledge reconstruction is needed for this indexed, semantic-eligible item
                fp = (item.metadata_json or {}).get("extraction_fingerprint")
                has_matching_fingerprint = (
                    isinstance(fp, dict)
                    and fp.get("content_hash") == item.content_hash
                    and fp.get("model_name") in (active_model_name, "qwen3:8b", "deterministic_manifest")
                )
                has_completed_run = item.id in completed_run_ev_ids
                has_stale = item.id in ev_ids_with_stale
                has_active_run = item.id in active_run_ev_ids
                has_active_ev_recon = (item.id, BackgroundJobType.KNOWLEDGE_RECONSTRUCTION.value) in active_jobs_tuples

                is_already_extracted = has_matching_fingerprint or (has_completed_run and not has_stale)
                is_changed = isinstance(fp, dict) and fp.get("content_hash") != item.content_hash
                should_extract = (
                    force_reextract
                    or (not is_already_extracted and (not is_changed or settings.extraction.auto_reextract_on_update))
                    or (has_stale and settings.extraction.auto_reextract_on_update)
                )
                if should_extract and not has_active_run and not has_active_ev_recon:
                    needs_reconstruction_ev_ids.append(item.id)

        # 2. If indexed eligible evidence items need reconstruction, batch into project-level extraction run
        if needs_reconstruction_ev_ids:
            # Check if there is already an active knowledge reconstruction job for this project
            has_active_recon = (
                self.session.execute(
                    select(BackgroundJob.id).where(
                        BackgroundJob.project_id == project_id,
                        BackgroundJob.job_type == BackgroundJobType.KNOWLEDGE_RECONSTRUCTION.value,
                        BackgroundJob.status.in_(
                            [BackgroundJobStatus.QUEUED.value, BackgroundJobStatus.RUNNING.value]
                        ),
                    )
                ).first()
                is not None
            )

            if not has_active_recon and items:
                first_item = items[0]
                categories = list(_CANONICAL_KNOWLEDGE_CATEGORIES)
                auto_run = knowledge_repo.create_extraction_run(
                    organisation_id=first_item.organisation_id,
                    project_id=project_id,
                    background_job_id=None,
                    evidence_id=None,
                    triggered_by_user_id=triggered_by_user_id,
                    scope_type=ExtractionRunScope.PROJECT.value,
                    target_categories=categories,
                    model_name=active_model_name,
                    prompt_version=active_prompt_version,
                    is_synthetic=False,
                    total_evidence_items=len(needs_reconstruction_ev_ids),
                )
                auto_job = job_repo.create_job(
                    organisation_id=first_item.organisation_id,
                    project_id=project_id,
                    evidence_id=None,
                    triggered_by_user_id=triggered_by_user_id,
                    job_type=BackgroundJobType.KNOWLEDGE_RECONSTRUCTION.value,
                    priority=2,
                    payload_json={
                        "run_id": str(auto_run.id),
                        "scope_type": ExtractionRunScope.PROJECT.value,
                        "evidence_ids": [str(eid) for eid in needs_reconstruction_ev_ids],
                        "categories": categories,
                        "force_rerun": force_reextract,
                        "include_synthetic": False,
                        "trigger": "pipeline_auto",
                    },
                )
                auto_run.background_job_id = auto_job.id
                jobs_scheduled += 1

        if queue_ingest_ids:
            self.session.execute(
                update(EvidenceItem)
                .where(EvidenceItem.id.in_(queue_ingest_ids))
                .values(processing_status=EvidenceProcessingStatus.QUEUED.value)
            )
        if queue_indexing_ids:
            self.session.execute(
                update(EvidenceItem)
                .where(EvidenceItem.id.in_(queue_indexing_ids))
                .values(indexing_status=EvidenceIndexingStatus.QUEUED.value)
            )
        if reconcile_indexed_ids:
            self.session.execute(
                update(EvidenceItem)
                .where(EvidenceItem.id.in_(reconcile_indexed_ids))
                .values(indexing_status=EvidenceIndexingStatus.INDEXED.value, indexed_at=now)
            )

        # Elevate priority of queued jobs for this active project so it is not starved by historical backlogs
        self.session.execute(
            update(BackgroundJob)
            .where(
                BackgroundJob.project_id == project_id,
                BackgroundJob.status == BackgroundJobStatus.QUEUED.value,
            )
            .values(
                priority=case(
                    (BackgroundJob.job_type == BackgroundJobType.DOCUMENT_INGESTION.value, 1),
                    (BackgroundJob.job_type == BackgroundJobType.EVIDENCE_INDEXING.value, 1),
                    (BackgroundJob.job_type == BackgroundJobType.KNOWLEDGE_RECONSTRUCTION.value, 2),
                    (BackgroundJob.job_type == BackgroundJobType.RELATIONSHIP_RECONSTRUCTION.value, 3),
                    else_=10,
                )
            )
        )

        self.session.commit()

        # Signal in-process worker to wake up and process jobs immediately
        if jobs_scheduled > 0:
            try:
                from app.main import signal_worker_activity

                signal_worker_activity()
            except Exception:
                pass

        return jobs_scheduled
