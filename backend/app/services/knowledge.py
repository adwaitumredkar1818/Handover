"""Domain service for Phase 2.6 knowledge extraction orchestration and permissioned reads."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from app.core.security import utc_now
from app.models.enums import (
    AuditOutcome,
    BackgroundJobStatus,
    BackgroundJobType,
    EpistemicStatus,
    EvidenceProcessingStatus,
    ExtractionRunScope,
    ExtractionRunStatus,
    KnowledgeCategory,
    KnowledgeReviewStatus,
    OrganisationStatus,
    ProjectStatus,
    SupportClassification,
)
from app.models.evidence import EvidenceChunk, EvidenceItem
from app.models.knowledge import KnowledgeEvidenceLink, KnowledgeExtractionRun, KnowledgeItem
from app.repositories.chunk import EvidenceChunkRepository
from app.repositories.evidence import EvidenceRepository
from app.repositories.job import BackgroundJobRepository
from app.repositories.knowledge import (
    AccessibleKnowledgeItemResult,
    KnowledgeRepository,
)
from app.schemas.knowledge import (
    EvidenceExtractRequest,
    EvidenceFactsResponse,
    ExtractedFactItemResponse,
    ExtractionTriggerResponse,
    KnowledgeEvidenceLinkResponse,
    KnowledgeExtractionRunListResponse,
    KnowledgeExtractionRunResponse,
    KnowledgeItemDetailResponse,
    KnowledgeItemFilterQuery,
    KnowledgeItemListResponse,
    KnowledgeItemSummaryResponse,
    ProjectKnowledgeExtractRequest,
    ProjectKnowledgeStatusResponse,
    RawChunkItemResponse,
)
from app.services.audit import AuditService
from app.services.evidence import to_background_job_response
from app.services.extraction_prompts import ALL_EXTRACTION_CATEGORIES
from app.services.integrations.access_policy import SourceAccessPolicyService
from app.services.knowledge_domains import is_valid_domain, resolve_canonical_domain
from app.services.rbac import ProjectContext

logger = logging.getLogger("app.services.knowledge")

_ELIGIBLE_EVIDENCE_STATUSES: frozenset[str] = frozenset(
    {
        EvidenceProcessingStatus.EXTRACTED.value,
        EvidenceProcessingStatus.PARTIALLY_EXTRACTED.value,
    }
)
_VALID_CATEGORIES: frozenset[str] = frozenset(c.value for c in KnowledgeCategory)
_VALID_EPISTEMIC: frozenset[str] = frozenset(e.value for e in EpistemicStatus)
_VALID_REVIEW: frozenset[str] = frozenset(r.value for r in KnowledgeReviewStatus)
_VALID_SUPPORT: frozenset[str] = frozenset(s.value for s in SupportClassification)
_VALID_RUN_STATUSES: frozenset[str] = frozenset(s.value for s in ExtractionRunStatus)


def to_extraction_run_response(run: KnowledgeExtractionRun) -> KnowledgeExtractionRunResponse:
    """Map KnowledgeExtractionRun ORM row cleanly into a public Pydantic response."""
    return KnowledgeExtractionRunResponse(
        id=run.id,
        organisation_id=run.organisation_id,
        project_id=run.project_id,
        background_job_id=run.background_job_id,
        evidence_id=run.evidence_id,
        triggered_by_user_id=run.triggered_by_user_id,
        scope_type=run.scope_type,
        target_categories=list(run.target_categories or []),
        model_name=run.model_name,
        prompt_version=run.prompt_version,
        status=ExtractionRunStatus(run.status),
        is_synthetic=bool(run.is_synthetic),
        total_evidence_items=int(run.total_evidence_items),
        processed_evidence_items=int(run.processed_evidence_items),
        failed_evidence_items=int(run.failed_evidence_items),
        skipped_evidence_items=int(run.skipped_evidence_items),
        total_chunks_evaluated=int(run.total_chunks_evaluated),
        batches_executed=int(run.batches_executed),
        candidates_generated=int(run.candidates_generated),
        claims_persisted=int(run.claims_persisted),
        claims_rejected_ungrounded=int(run.claims_rejected_ungrounded),
        duplicates_merged=int(run.duplicates_merged),
        prompt_tokens=int(run.prompt_tokens),
        completion_tokens=int(run.completion_tokens),
        warnings=list(run.warnings_json or []),
        error_code=run.error_code,
        error_message=run.error_message,
        started_at=run.started_at,
        completed_at=run.completed_at,
        duration_ms=run.duration_ms,
        created_at=run.created_at,
        updated_at=run.updated_at,
        job=(
            to_background_job_response(run.background_job)
            if run.background_job is not None
            else None
        ),
    )


def to_evidence_link_response(link: KnowledgeEvidenceLink) -> KnowledgeEvidenceLinkResponse:
    """Map verified KnowledgeEvidenceLink row preserving strict provenance fields."""
    return KnowledgeEvidenceLinkResponse(
        id=link.id,
        evidence_id=link.evidence_id,
        evidence_chunk_id=link.evidence_chunk_id,
        support_type=SupportClassification(link.support_type),
        source_location=dict(link.source_location_json or {}),
        supporting_excerpt=link.supporting_excerpt,
        excerpt_verified=bool(link.excerpt_verified),
        excerpt_match_mode=link.excerpt_match_mode,
        source_metadata=dict(link.source_metadata_json or {}),
        created_at=link.created_at,
    )


def _sanitised_attribution(
    *,
    item: KnowledgeItem,
    accessible_links: tuple[KnowledgeEvidenceLink, ...],
) -> dict[str, Any]:
    """Ensure source_attribution retains provenance and evidence citations."""
    raw_attr = dict(item.source_attribution_json or {})
    if not accessible_links:
        ev_id = raw_attr.get("evidence_id")
        return {
            **raw_attr,
            "evidence_id": ev_id,
            "evidence_ids": [ev_id] if ev_id else [],
            "evidence_count": 1 if ev_id else 0,
            "stored_epistemic_tier": item.epistemic_status,
        }
    first = accessible_links[0]
    first_meta = dict(first.source_metadata_json or {})
    ev_ids = [str(lnk.evidence_id) for lnk in accessible_links if lnk.evidence_id]
    if not ev_ids and raw_attr.get("evidence_id"):
        ev_ids = [str(raw_attr["evidence_id"])]
    primary_ev_id = ev_ids[0] if ev_ids else str(first.evidence_id)
    return {
        "source_type": first_meta.get("source_type") or raw_attr.get("source_type") or "document_upload",
        "source_provider": first_meta.get("source_provider") or raw_attr.get("source_provider") or "local_upload",
        "source_external_id": first_meta.get("source_external_id") or raw_attr.get("source_external_id") or f"upload:{primary_ev_id}",
        "source_url": first_meta.get("source_url") or raw_attr.get("source_url"),
        "source_author_identity": first_meta.get("source_author_identity") or raw_attr.get("author") or item.person_or_owner_label or "Shubham",
        "title": first_meta.get("title") or raw_attr.get("title") or item.title,
        "source_created_at": first_meta.get("source_created_at"),
        "evidence_id": primary_ev_id,
        "evidence_ids": ev_ids,
        "evidence_count": len(set(ev_ids)),
        "stored_epistemic_tier": item.epistemic_status,
    }


def to_knowledge_item_summary(res: AccessibleKnowledgeItemResult) -> KnowledgeItemSummaryResponse:
    item = res.item
    return KnowledgeItemSummaryResponse(
        id=item.id,
        organisation_id=item.organisation_id,
        project_id=item.project_id,
        extraction_run_id=item.extraction_run_id,
        category=KnowledgeCategory(item.category),
        epistemic_status=EpistemicStatus(item.epistemic_status),
        review_status=KnowledgeReviewStatus(item.review_status),
        support_classification=SupportClassification(item.support_classification),
        title=item.title,
        structured_summary=item.structured_summary,
        structured_payload=dict(item.structured_payload or {}),
        normalised_status=item.normalised_status,
        person_or_owner_label=item.person_or_owner_label,
        source_attribution=_sanitised_attribution(
            item=item,
            accessible_links=res.accessible_links,
        ),
        extraction_model=item.extraction_model,
        prompt_version=item.prompt_version,
        confidence_metadata=dict(item.confidence_metadata_json or {}),
        uncertainty_reason=item.uncertainty_reason,
        is_stale=bool(item.is_stale),
        stale_reason=item.stale_reason,
        stale_detected_at=item.stale_detected_at,
        superseded_by_id=item.superseded_by_id,
        is_synthetic=bool(item.is_synthetic),
        source_observed_at=item.source_observed_at,
        evidence_links_count=len(res.accessible_links),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def to_knowledge_item_detail(res: AccessibleKnowledgeItemResult) -> KnowledgeItemDetailResponse:
    summary = to_knowledge_item_summary(res)
    return KnowledgeItemDetailResponse(
        **summary.model_dump(),
        evidence_links=[to_evidence_link_response(lnk) for lnk in res.accessible_links],
    )


class KnowledgeReconstructionService:
    """Orchestrates permissioned knowledge extraction jobs, runs & provenance-safe queries."""

    def __init__(
        self,
        *,
        session: Session,
        settings: Settings,
        knowledge_repository: KnowledgeRepository,
        evidence_repository: EvidenceRepository,
        chunk_repository: EvidenceChunkRepository,
        job_repository: BackgroundJobRepository,
        audit_service: AuditService,
        access_policy_service: SourceAccessPolicyService | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._knowledge_repo = knowledge_repository
        self._evidence_repo = evidence_repository
        self._chunk_repo = chunk_repository
        self._job_repo = job_repository
        self._audit = audit_service
        self._access_policy = access_policy_service or SourceAccessPolicyService()

    def _require_project_mutable(self, project_ctx: ProjectContext) -> None:
        if project_ctx.organisation.status != OrganisationStatus.ACTIVE.value:
            raise ConflictError(
                f"Organisation is '{project_ctx.organisation.status}' and cannot run extraction.",
                code="ORGANISATION_NOT_ACTIVE",
            )
        if project_ctx.project.status == ProjectStatus.ARCHIVED.value:
            raise ConflictError(
                "Project workspace is archived and cannot run knowledge extraction.",
                code="PROJECT_ARCHIVED",
            )

    def _require_trigger_permission(self, project_ctx: ProjectContext, *, resource_id: str) -> None:
        can_trigger = project_ctx.has_permission("project.manage") or (
            project_ctx.project_membership is not None
            and project_ctx.has_permission("project.evidence.contribute")
        )
        if not can_trigger:
            self._audit.record_event(
                event_type="knowledge.extraction_trigger_denied",
                resource_type="project",
                actor_user_id=project_ctx.principal.user.id,
                organisation_id=project_ctx.organisation.id,
                project_id=project_ctx.project.id,
                resource_id=resource_id,
                outcome=AuditOutcome.DENIED.value,
                message="Denied knowledge extraction trigger due to missing project permission.",
                level=logging.WARNING,
            )
            self._session.commit()
            raise ForbiddenError(
                "You do not have permission to trigger knowledge extraction in this project.",
                code="FORBIDDEN",
            )

    def _resolve_target_categories(
        self, requested: list[KnowledgeCategory] | None
    ) -> list[str]:
        if not requested:
            return [c.value for c in ALL_EXTRACTION_CATEGORIES]
        deduped: list[str] = []
        for cat in requested:
            if cat.value not in deduped:
                deduped.append(cat.value)
        return deduped

    def _count_chunks_for_evidence(self, evidence_id: uuid.UUID) -> int:
        chunks = self._chunk_repo.list_chunks_for_evidence(evidence_id)
        return len(chunks)

    def trigger_evidence_extraction(
        self,
        *,
        project_ctx: ProjectContext,
        evidence_id: uuid.UUID,
        payload: EvidenceExtractRequest,
    ) -> ExtractionTriggerResponse:
        """Queue asynchronous knowledge extraction for one authorised, chunked evidence item."""
        self._require_trigger_permission(project_ctx, resource_id=str(evidence_id))
        self._require_project_mutable(project_ctx)

        evidence = self._evidence_repo.get_by_id(evidence_id, include_deleted=False)
        if evidence is None or evidence.project_id != project_ctx.project.id:
            raise NotFoundError("Evidence item was not found.", code="EVIDENCE_NOT_FOUND")

        self._access_policy.enforce_evidence_access(
            evidence=evidence,
            project_ctx=project_ctx,
            session=self._session,
            audit_service=self._audit,
        )

        if evidence.processing_status not in _ELIGIBLE_EVIDENCE_STATUSES:
            raise ConflictError(
                f"Evidence item in status '{evidence.processing_status}' cannot be extracted yet.",
                code="EVIDENCE_NOT_EXTRACTED",
            )

        if self._count_chunks_for_evidence(evidence.id) == 0:
            raise ConflictError(
                "Evidence item has no canonical chunks yet; run evidence indexing first.",
                code="EVIDENCE_NOT_CHUNKED",
            )

        active_run = self._knowledge_repo.get_active_run_for_evidence(
            project_id=project_ctx.project.id,
            evidence_id=evidence.id,
        )
        if active_run is not None:
            active_job = (
                to_background_job_response(active_run.background_job)
                if active_run.background_job is not None
                else None
            )
            return ExtractionTriggerResponse(
                run=to_extraction_run_response(active_run),
                job=active_job,
                already_active=True,
                skipped_inaccessible_count=0,
            )

        categories = self._resolve_target_categories(payload.categories)
        is_synthetic = EvidenceChunkRepository.is_item_synthetic(evidence)

        run = self._knowledge_repo.create_extraction_run(
            organisation_id=project_ctx.organisation.id,
            project_id=project_ctx.project.id,
            background_job_id=None,
            evidence_id=evidence.id,
            triggered_by_user_id=project_ctx.principal.user.id,
            scope_type=ExtractionRunScope.EVIDENCE.value,
            target_categories=categories,
            model_name=self._settings.ollama.llm_model,
            prompt_version=self._settings.extraction.prompt_version,
            is_synthetic=is_synthetic,
            total_evidence_items=1,
        )
        job = self._job_repo.create_job(
            organisation_id=project_ctx.organisation.id,
            project_id=project_ctx.project.id,
            evidence_id=evidence.id,
            triggered_by_user_id=project_ctx.principal.user.id,
            job_type=BackgroundJobType.KNOWLEDGE_RECONSTRUCTION.value,
            max_attempts=self._settings.ingestion.worker_max_attempts,
            priority=120,
            payload_json={
                "run_id": str(run.id),
                "scope_type": ExtractionRunScope.EVIDENCE.value,
                "evidence_ids": [str(evidence.id)],
                "categories": categories,
                "force_rerun": payload.force_rerun,
                "include_synthetic": is_synthetic,
            },
        )
        run.background_job_id = job.id

        self._audit.record_event(
            event_type="knowledge.extraction_queued",
            resource_type="knowledge_extraction_run",
            actor_user_id=project_ctx.principal.user.id,
            organisation_id=project_ctx.organisation.id,
            project_id=project_ctx.project.id,
            resource_id=str(run.id),
            metadata={
                "evidence_id": str(evidence.id),
                "job_id": str(job.id),
                "categories": categories,
                "model_name": run.model_name,
                "prompt_version": run.prompt_version,
            },
            message="Queued asynchronous knowledge reconstruction run for evidence item.",
        )
        self._session.commit()
        try:
            from app.main import signal_worker_activity

            signal_worker_activity()
        except Exception:
            pass
        refreshed = self._knowledge_repo.get_run_by_id(run.id) or run
        self._session.refresh(job)
        return ExtractionTriggerResponse(
            run=to_extraction_run_response(refreshed),
            job=to_background_job_response(job),
            already_active=False,
            skipped_inaccessible_count=0,
        )

    def trigger_project_extraction(
        self,
        *,
        project_ctx: ProjectContext,
        payload: ProjectKnowledgeExtractRequest,
    ) -> ExtractionTriggerResponse:
        """Queue asynchronous project-wide or multi-item knowledge extraction."""
        self._require_trigger_permission(project_ctx, resource_id=str(project_ctx.project.id))
        self._require_project_mutable(project_ctx)

        active_run = self._knowledge_repo.get_active_project_run(
            project_id=project_ctx.project.id
        )
        if active_run is not None:
            active_job = (
                to_background_job_response(active_run.background_job)
                if active_run.background_job is not None
                else None
            )
            return ExtractionTriggerResponse(
                run=to_extraction_run_response(active_run),
                job=active_job,
                already_active=True,
                skipped_inaccessible_count=0,
            )

        viewer_id = project_ctx.principal.user.id
        has_manage = project_ctx.has_permission("project.manage")

        candidates: list[EvidenceItem] = []
        skipped_inaccessible = 0
        requested_ids = list(dict.fromkeys(payload.evidence_ids or []))
        if requested_ids:
            for ev_id in requested_ids:
                ev = self._evidence_repo.get_by_id(ev_id, include_deleted=False)
                if ev is None or ev.project_id != project_ctx.project.id:
                    continue
                if not self._access_policy.can_user_access_evidence(
                    evidence=ev,
                    user_id=viewer_id,
                    has_project_manage=has_manage,
                ):
                    skipped_inaccessible += 1
                    continue
                if (not payload.include_synthetic) and (
                    EvidenceChunkRepository.is_item_synthetic(ev)
                ):
                    continue
                if ev.processing_status in _ELIGIBLE_EVIDENCE_STATUSES and (
                    self._count_chunks_for_evidence(ev.id) > 0
                ):
                    candidates.append(ev)
            if skipped_inaccessible > 0 and not candidates:
                self._audit.record_event(
                    event_type="knowledge.source_acl_denied",
                    resource_type="project",
                    actor_user_id=viewer_id,
                    organisation_id=project_ctx.organisation.id,
                    project_id=project_ctx.project.id,
                    resource_id=str(project_ctx.project.id),
                    outcome=AuditOutcome.DENIED.value,
                    metadata={"skipped_inaccessible_count": skipped_inaccessible},
                    message="Denied knowledge extraction on restricted evidence targets.",
                    level=logging.WARNING,
                )
                self._session.commit()
                raise ForbiddenError(
                    "You lack delegated source access for the requested evidence items.",
                    code="SOURCE_ACCESS_DENIED",
                )
        else:
            stmt = (
                select(EvidenceItem)
                .where(
                    EvidenceItem.project_id == project_ctx.project.id,
                    EvidenceItem.deleted_at.is_(None),
                    EvidenceItem.processing_status.in_(tuple(_ELIGIBLE_EVIDENCE_STATUSES)),
                )
                .order_by(
                    case((EvidenceItem.source_type == "document_upload", 0), else_=1),
                    EvidenceItem.created_at.asc(),
                    EvidenceItem.id.asc(),
                )
            )
            all_project_items = list(self._session.execute(stmt).scalars().all())
            for ev in all_project_items:
                if not self._access_policy.can_user_access_evidence(
                    evidence=ev,
                    user_id=viewer_id,
                    has_project_manage=has_manage,
                ):
                    skipped_inaccessible += 1
                    continue
                if (not payload.include_synthetic) and (
                    EvidenceChunkRepository.is_item_synthetic(ev)
                ):
                    continue
                has_chunk = (
                    self._session.execute(
                        select(EvidenceChunk.id)
                        .where(EvidenceChunk.evidence_id == ev.id)
                        .limit(1)
                    ).scalar_one_or_none()
                    is not None
                )
                if has_chunk:
                    candidates.append(ev)

        if not candidates:
            raise ConflictError(
                "No accessible, extracted, chunked evidence items are eligible for extraction.",
                code="NO_ELIGIBLE_EVIDENCE",
            )

        categories = self._resolve_target_categories(payload.categories)
        any_synthetic = any(EvidenceChunkRepository.is_item_synthetic(ev) for ev in candidates)

        run = self._knowledge_repo.create_extraction_run(
            organisation_id=project_ctx.organisation.id,
            project_id=project_ctx.project.id,
            background_job_id=None,
            evidence_id=None,
            triggered_by_user_id=viewer_id,
            scope_type=ExtractionRunScope.PROJECT.value,
            target_categories=categories,
            model_name=self._settings.ollama.llm_model,
            prompt_version=self._settings.extraction.prompt_version,
            is_synthetic=any_synthetic,
            total_evidence_items=len(candidates),
        )
        run.skipped_evidence_items = skipped_inaccessible

        job = self._job_repo.create_job(
            organisation_id=project_ctx.organisation.id,
            project_id=project_ctx.project.id,
            evidence_id=None,
            triggered_by_user_id=viewer_id,
            job_type=BackgroundJobType.KNOWLEDGE_RECONSTRUCTION.value,
            max_attempts=self._settings.ingestion.worker_max_attempts,
            priority=125,
            payload_json={
                "run_id": str(run.id),
                "scope_type": ExtractionRunScope.PROJECT.value,
                "evidence_ids": [str(ev.id) for ev in candidates],
                "categories": categories,
                "force_rerun": payload.force_rerun,
                "include_synthetic": payload.include_synthetic,
            },
        )
        run.background_job_id = job.id

        self._audit.record_event(
            event_type="knowledge.project_extraction_queued",
            resource_type="knowledge_extraction_run",
            actor_user_id=viewer_id,
            organisation_id=project_ctx.organisation.id,
            project_id=project_ctx.project.id,
            resource_id=str(run.id),
            metadata={
                "job_id": str(job.id),
                "target_evidence_count": len(candidates),
                "skipped_inaccessible_count": skipped_inaccessible,
                "categories": categories,
            },
            message=(
                f"Queued project knowledge extraction across {len(candidates)} evidence item(s)."
            ),
        )
        self._session.commit()
        try:
            from app.main import signal_worker_activity

            signal_worker_activity()
        except Exception:
            pass
        refreshed = self._knowledge_repo.get_run_by_id(run.id) or run
        self._session.refresh(job)
        return ExtractionTriggerResponse(
            run=to_extraction_run_response(refreshed),
            job=to_background_job_response(job),
            already_active=False,
            skipped_inaccessible_count=skipped_inaccessible,
        )

    def list_extraction_runs(
        self,
        *,
        project_ctx: ProjectContext,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> KnowledgeExtractionRunListResponse:
        if status is not None and status not in _VALID_RUN_STATUSES:
            raise BadRequestError(
                "Unsupported extraction run status filter.",
                code="INVALID_FILTER",
            )
        runs, total = self._knowledge_repo.list_runs_for_project(
            project_id=project_ctx.project.id,
            status=status,
            limit=limit,
            offset=offset,
        )
        return KnowledgeExtractionRunListResponse(
            items=[to_extraction_run_response(run) for run in runs],
            total=total,
            limit=limit,
            offset=offset,
        )

    def get_extraction_run(
        self,
        *,
        project_ctx: ProjectContext,
        run_id: uuid.UUID,
    ) -> KnowledgeExtractionRunResponse:
        run = self._knowledge_repo.get_run_by_id(run_id, project_id=project_ctx.project.id)
        if run is None:
            raise NotFoundError("Extraction run was not found.", code="EXTRACTION_RUN_NOT_FOUND")
        return to_extraction_run_response(run)

    def list_evidence_extraction_runs(
        self,
        *,
        project_ctx: ProjectContext,
        evidence_id: uuid.UUID,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> KnowledgeExtractionRunListResponse:
        evidence = self._evidence_repo.get_by_id(evidence_id, include_deleted=False)
        if evidence is None or evidence.project_id != project_ctx.project.id:
            raise NotFoundError("Evidence item was not found.", code="EVIDENCE_NOT_FOUND")

        self._access_policy.enforce_evidence_access(
            evidence=evidence,
            project_ctx=project_ctx,
            session=self._session,
            audit_service=self._audit,
        )

        if status is not None and status not in _VALID_RUN_STATUSES:
            raise BadRequestError(
                "Unsupported extraction run status filter.",
                code="INVALID_FILTER",
            )
        runs, total = self._knowledge_repo.list_runs_for_project(
            project_id=project_ctx.project.id,
            evidence_id=evidence_id,
            status=status,
            limit=limit,
            offset=offset,
        )
        return KnowledgeExtractionRunListResponse(
            items=[to_extraction_run_response(run) for run in runs],
            total=total,
            limit=limit,
            offset=offset,
        )

    def get_evidence_extraction_run(
        self,
        *,
        project_ctx: ProjectContext,
        evidence_id: uuid.UUID,
        run_id: uuid.UUID,
    ) -> KnowledgeExtractionRunResponse:
        evidence = self._evidence_repo.get_by_id(evidence_id, include_deleted=False)
        if evidence is None or evidence.project_id != project_ctx.project.id:
            raise NotFoundError("Evidence item was not found.", code="EVIDENCE_NOT_FOUND")

        self._access_policy.enforce_evidence_access(
            evidence=evidence,
            project_ctx=project_ctx,
            session=self._session,
            audit_service=self._audit,
        )

        run = self._knowledge_repo.get_run_by_id(run_id, project_id=project_ctx.project.id)
        if run is None or run.evidence_id != evidence_id:
            raise NotFoundError(
                "Extraction run was not found for this evidence item.",
                code="EXTRACTION_RUN_NOT_FOUND",
            )
        return to_extraction_run_response(run)

    def get_evidence_facts(
        self,
        *,
        project_ctx: ProjectContext,
        evidence_id: uuid.UUID,
    ) -> EvidenceFactsResponse:
        evidence = self._evidence_repo.get_by_id(evidence_id, include_deleted=False)
        if evidence is None or evidence.project_id != project_ctx.project.id:
            raise NotFoundError("Evidence item was not found.", code="EVIDENCE_NOT_FOUND")

        self._access_policy.enforce_evidence_access(
            evidence=evidence,
            project_ctx=project_ctx,
            session=self._session,
            audit_service=self._audit,
        )

        chunk_repo = EvidenceChunkRepository(self._session)
        chunks = chunk_repo.list_chunks_for_evidence(evidence.id)
        raw_chunks = [
            RawChunkItemResponse(
                id=c.id,
                chunk_index=c.chunk_index,
                page_number=c.page_number,
                chunk_type=c.chunk_type,
                char_count=c.char_count,
                token_estimate=c.token_estimate,
                chunk_text=c.chunk_text,
                indexing_status=c.indexing_status,
            )
            for c in chunks
        ]

        accessible_items, _ = self._knowledge_repo.list_accessible_items_for_project(
            project_id=project_ctx.project.id,
            viewer_user_id=project_ctx.principal.user_id,
            has_project_manage=project_ctx.has_permission("project.manage"),
            evidence_id=evidence.id,
            limit=500,
            offset=0,
        )

        facts: list[ExtractedFactItemResponse] = []
        for result in accessible_items:
            item = result.item
            matching_links = [
                lnk for lnk in result.accessible_links if lnk.evidence_id == evidence.id
            ]
            conf_meta = item.confidence_metadata_json or {}
            grounding_score = float(conf_meta.get("grounding_score", 1.0))
            conf_level = str(conf_meta.get("confidence_level", "high"))
            conf_expl = conf_meta.get("confidence_explanation") or conf_meta.get("rationale")
            val_state = (
                "candidate"
                if item.review_status in {"candidate", "pending_review"}
                else ("verified" if item.review_status == "approved" else item.review_status)
            )

            if matching_links:
                for lnk in matching_links:
                    loc = lnk.source_location_json or {}
                    page_num = loc.get("page_number")
                    page_or_sec = loc.get("page_or_section") or (
                        f"Page {page_num}" if page_num else None
                    )
                    facts.append(
                        ExtractedFactItemResponse(
                            id=lnk.id,
                            evidence_id=evidence.id,
                            knowledge_item_id=item.id,
                            chunk_id=lnk.evidence_chunk_id,
                            title=item.title,
                            description=item.structured_summary,
                            category=item.category,
                            primary_domain=item.primary_domain or item.category,
                            confidence_level=conf_level,
                            grounding_score=grounding_score,
                            confidence_explanation=conf_expl,
                            original_excerpt=lnk.supporting_excerpt,
                            page_or_section=page_or_sec,
                            validation_state=val_state,
                            is_ai_extracted=True,
                            created_at=item.created_at,
                        )
                    )
            else:
                facts.append(
                    ExtractedFactItemResponse(
                        id=item.id,
                        evidence_id=evidence.id,
                        knowledge_item_id=item.id,
                        chunk_id=None,
                        title=item.title,
                        description=item.structured_summary,
                        category=item.category,
                        primary_domain=item.primary_domain or item.category,
                        confidence_level=conf_level,
                        grounding_score=grounding_score,
                        confidence_explanation=conf_expl,
                        original_excerpt=item.structured_summary,
                        page_or_section=None,
                        validation_state=val_state,
                        is_ai_extracted=True,
                        created_at=item.created_at,
                    )
                )

        latest_run = self._knowledge_repo.get_active_run_for_evidence(
            project_id=project_ctx.project.id,
            evidence_id=evidence.id,
        )
        if latest_run is None:
            runs, _ = self._knowledge_repo.list_runs_for_project(
                project_id=project_ctx.project.id,
                evidence_id=evidence.id,
                limit=1,
            )
            if runs:
                latest_run = runs[0]

        latest_run_id = latest_run.id if latest_run else None
        latest_run_status = latest_run.status if latest_run else None

        return EvidenceFactsResponse(
            evidence_id=evidence.id,
            project_id=project_ctx.project.id,
            total_facts=len(facts) + len(raw_chunks),
            ai_extracted_count=len(facts),
            raw_chunk_count=len(raw_chunks),
            latest_run_id=latest_run_id,
            latest_run_status=latest_run_status,
            facts=facts,
            raw_chunks=raw_chunks,
        )

    def retry_extraction_run(
        self,
        *,
        project_ctx: ProjectContext,
        run_id: uuid.UUID,
    ) -> ExtractionTriggerResponse:
        self._require_trigger_permission(project_ctx, resource_id=str(run_id))
        self._require_project_mutable(project_ctx)

        run = self._knowledge_repo.get_run_by_id(run_id, project_id=project_ctx.project.id)
        if run is None:
            raise NotFoundError("Extraction run was not found.", code="EXTRACTION_RUN_NOT_FOUND")

        if run.status not in {
            ExtractionRunStatus.FAILED.value,
            ExtractionRunStatus.PARTIALLY_COMPLETED.value,
            ExtractionRunStatus.CANCELLED.value,
        }:
            raise ConflictError(
                f"Extraction run in status '{run.status}' cannot be retried.",
                code="INVALID_RUN_STATE",
            )

        prior_payload = dict(run.background_job.payload_json) if run.background_job else {}
        evidence_ids_raw = list(prior_payload.get("evidence_ids") or [])
        if not evidence_ids_raw and run.evidence_id is not None:
            evidence_ids_raw = [str(run.evidence_id)]

        new_run = self._knowledge_repo.create_extraction_run(
            organisation_id=project_ctx.organisation.id,
            project_id=project_ctx.project.id,
            background_job_id=None,
            evidence_id=run.evidence_id,
            triggered_by_user_id=project_ctx.principal.user.id,
            scope_type=run.scope_type,
            target_categories=list(run.target_categories or []),
            model_name=self._settings.ollama.llm_model,
            prompt_version=self._settings.extraction.prompt_version,
            is_synthetic=bool(run.is_synthetic),
            total_evidence_items=len(evidence_ids_raw),
        )
        new_job = self._job_repo.create_job(
            organisation_id=project_ctx.organisation.id,
            project_id=project_ctx.project.id,
            evidence_id=run.evidence_id,
            triggered_by_user_id=project_ctx.principal.user.id,
            job_type=BackgroundJobType.KNOWLEDGE_RECONSTRUCTION.value,
            max_attempts=self._settings.ingestion.worker_max_attempts,
            priority=120,
            payload_json={
                "run_id": str(new_run.id),
                "scope_type": run.scope_type,
                "evidence_ids": evidence_ids_raw,
                "categories": list(run.target_categories or []),
                "force_rerun": bool(prior_payload.get("force_rerun", False)),
                "include_synthetic": bool(run.is_synthetic),
                "retried_from_run_id": str(run.id),
            },
        )
        new_run.background_job_id = new_job.id
        self._audit.record_event(
            event_type="knowledge.extraction_retry_queued",
            resource_type="knowledge_extraction_run",
            actor_user_id=project_ctx.principal.user.id,
            organisation_id=project_ctx.organisation.id,
            project_id=project_ctx.project.id,
            resource_id=str(new_run.id),
            metadata={"previous_run_id": str(run.id), "job_id": str(new_job.id)},
            message="Queued manual retry of knowledge extraction run.",
        )
        self._session.commit()
        refreshed = self._knowledge_repo.get_run_by_id(new_run.id) or new_run
        self._session.refresh(new_job)
        return ExtractionTriggerResponse(
            run=to_extraction_run_response(refreshed),
            job=to_background_job_response(new_job),
            already_active=False,
        )

    def cancel_extraction_run(
        self,
        *,
        project_ctx: ProjectContext,
        run_id: uuid.UUID,
    ) -> KnowledgeExtractionRunResponse:
        self._require_trigger_permission(project_ctx, resource_id=str(run_id))
        self._require_project_mutable(project_ctx)

        run = self._knowledge_repo.get_run_by_id(run_id, project_id=project_ctx.project.id)
        if run is None:
            raise NotFoundError("Extraction run was not found.", code="EXTRACTION_RUN_NOT_FOUND")
        if run.status != ExtractionRunStatus.QUEUED.value:
            raise ConflictError(
                f"Only queued extraction runs can be cancelled (current status: '{run.status}').",
                code="INVALID_RUN_STATE",
            )

        now = utc_now()
        run.status = ExtractionRunStatus.CANCELLED.value
        run.completed_at = now
        run.error_code = "CANCELLED_BY_USER"
        run.error_message = "Extraction run cancelled before worker execution."
        if (
            run.background_job is not None
            and run.background_job.status == BackgroundJobStatus.QUEUED.value
        ):
            run.background_job.status = BackgroundJobStatus.CANCELLED.value
            run.background_job.completed_at = now
            run.background_job.locked_by = None
            run.background_job.lease_expires_at = None

        self._audit.record_event(
            event_type="knowledge.extraction_cancelled",
            resource_type="knowledge_extraction_run",
            actor_user_id=project_ctx.principal.user.id,
            organisation_id=project_ctx.organisation.id,
            project_id=project_ctx.project.id,
            resource_id=str(run.id),
            message="Cancelled queued knowledge extraction run.",
        )
        self._session.commit()
        try:
            from app.main import signal_worker_activity

            signal_worker_activity()
        except Exception:
            pass
        refreshed = self._knowledge_repo.get_run_by_id(run.id) or run
        return to_extraction_run_response(refreshed)

    def list_knowledge_items(
        self,
        *,
        project_ctx: ProjectContext,
        category: str | None = None,
        domain: str | None = None,
        epistemic_status: str | None = None,
        review_status: str | None = None,
        support_classification: str | None = None,
        normalised_status: str | None = None,
        person: str | None = None,
        source_provider: str | None = None,
        evidence_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        include_stale: bool = True,
        stale_only: bool = False,
        include_synthetic: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> KnowledgeItemListResponse:
        filter_domain = domain
        filter_category = category
        if category is not None:
            cat_clean = category.strip()
            if is_valid_domain(cat_clean):
                filter_domain = cat_clean
            elif cat_clean not in _VALID_CATEGORIES and cat_clean.lower() not in _VALID_CATEGORIES:
                raise BadRequestError("Unsupported category filter.", code="INVALID_FILTER")
        if filter_domain is not None and not is_valid_domain(filter_domain):
            raise BadRequestError("Unsupported domain filter.", code="INVALID_FILTER")

        if epistemic_status is not None and epistemic_status not in _VALID_EPISTEMIC:
            raise BadRequestError("Unsupported epistemic_status filter.", code="INVALID_FILTER")
        if review_status is not None and review_status not in _VALID_REVIEW:
            raise BadRequestError("Unsupported review_status filter.", code="INVALID_FILTER")
        if support_classification is not None and support_classification not in _VALID_SUPPORT:
            raise BadRequestError(
                "Unsupported support_classification filter.",
                code="INVALID_FILTER",
            )
        KnowledgeItemFilterQuery(date_from=date_from, date_to=date_to)

        rows, total = self._knowledge_repo.list_accessible_items_for_project(
            project_id=project_ctx.project.id,
            viewer_user_id=project_ctx.principal.user.id,
            has_project_manage=project_ctx.has_permission("project.manage"),
            category=filter_category,
            domain=filter_domain,
            epistemic_status=epistemic_status,
            review_status=review_status,
            support_classification=support_classification,
            normalised_status=normalised_status,
            person=person,
            source_provider=source_provider,
            evidence_id=evidence_id,
            date_from=date_from,
            date_to=date_to,
            include_stale=include_stale,
            stale_only=stale_only,
            include_synthetic=include_synthetic,
            limit=limit,
            offset=offset,
        )
        return KnowledgeItemListResponse(
            items=[to_knowledge_item_summary(r) for r in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def get_knowledge_item_detail(
        self,
        *,
        project_ctx: ProjectContext,
        item_id: uuid.UUID,
    ) -> KnowledgeItemDetailResponse:
        item, links, denied_by_acl = self._knowledge_repo.get_item_with_acl_check(
            project_id=project_ctx.project.id,
            item_id=item_id,
            viewer_user_id=project_ctx.principal.user.id,
            has_project_manage=project_ctx.has_permission("project.manage"),
        )
        if item is None:
            raise NotFoundError("Knowledge item was not found.", code="KNOWLEDGE_ITEM_NOT_FOUND")
        if denied_by_acl:
            self._audit.record_event(
                event_type="knowledge.source_acl_denied",
                resource_type="knowledge_item",
                actor_user_id=project_ctx.principal.user.id,
                organisation_id=project_ctx.organisation.id,
                project_id=project_ctx.project.id,
                resource_id=str(item_id),
                outcome=AuditOutcome.DENIED.value,
                message="Denied knowledge item read due to supporting source ACL restriction.",
                level=logging.WARNING,
            )
            self._session.commit()
            raise ForbiddenError(
                "You lack delegated source access to inspect this knowledge item's evidence.",
                code="SOURCE_ACCESS_DENIED",
            )
        return to_knowledge_item_detail(
            AccessibleKnowledgeItemResult(item=item, accessible_links=links)
        )

    def get_project_knowledge_status(
        self,
        *,
        project_ctx: ProjectContext,
        include_synthetic: bool = False,
    ) -> ProjectKnowledgeStatusResponse:
        stats = self._knowledge_repo.get_project_knowledge_stats(
            project_id=project_ctx.project.id,
            viewer_user_id=project_ctx.principal.user.id,
            has_project_manage=project_ctx.has_permission("project.manage"),
            include_synthetic=include_synthetic,
        )
        runs, _ = self._knowledge_repo.list_runs_for_project(
            project_id=project_ctx.project.id,
            limit=1,
            offset=0,
        )
        return ProjectKnowledgeStatusResponse(
            project_id=project_ctx.project.id,
            total_accessible_items=stats.total_accessible_items,
            stale_items_count=stats.stale_items_count,
            counts_by_category=stats.counts_by_category,
            counts_by_epistemic_status=stats.counts_by_epistemic_status,
            counts_by_support_classification=stats.counts_by_support_classification,
            active_runs_count=stats.active_runs_count,
            latest_run=to_extraction_run_response(runs[0]) if runs else None,
        )
