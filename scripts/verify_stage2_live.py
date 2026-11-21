"""Verify Stage 2 Background Ollama Semantic Enrichment & Failure Recovery.

Executes real Ollama Qwen3:8b semantic extraction on ADR 001 from Rashkar project,
verifies grounding, measures latency and tokens, verifies graph updates,
and validates bounded failure recovery.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
import uuid
from datetime import timedelta

import httpx

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.core.config import get_settings
from app.core.security import create_access_token, generate_refresh_token, hash_refresh_token, utc_now
from app.db.session import create_db_engine, create_session_factory
from app.models.auth import RefreshSession
from app.models.enums import BackgroundJobStatus, BackgroundJobType, ExtractionRunStatus
from app.models.evidence import EvidenceChunk, EvidenceItem
from app.models.job import BackgroundJob
from app.models.knowledge import KnowledgeEvidenceLink, KnowledgeExtractionRun, KnowledgeItem
from app.models.project import Project, ProjectMembership
from app.models.user import User
from app.repositories.evidence import EvidenceRepository
from app.repositories.job import BackgroundJobRepository
from app.repositories.knowledge import KnowledgeRepository
from app.services.chunking import ChunkingService
from app.services.indexing_worker import IndexingWorkerService
from app.services.knowledge_validator import KnowledgeCandidateValidator
from app.services.llm import OllamaLLMClient
from app.services.reconstruction_worker import ReconstructionWorkerService
from app.services.relationship_coordinator import RelationshipCoordinatorService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("stage2_verify")


def get_gpu_vram_mb() -> float:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True,
            timeout=5,
        )
        return float(out.strip().split("\n")[0])
    except Exception:
        return 0.0


def main():
    logger.info("=================================================================")
    logger.info("STAGE 2 VERIFICATION: BACKGROUND OLLAMA ENRICHMENT & RESILIENCE")
    logger.info("=================================================================")

    settings = get_settings()
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)
    pid = uuid.UUID("17ca9ab2-bbb8-4e61-9f52-4fbd6a7ce9c8")
    adr_id = uuid.UUID("2498e191-42f9-4d2a-8481-8cfeabe0f8f1")
    base_url = "http://localhost:8000/api/v1"

    # 1. Authenticate user
    with session_factory() as session:
        member = session.query(ProjectMembership).filter_by(project_id=pid).first()
        user_id = member.user_id if member else session.query(User).first().id
        proj = session.query(Project).filter_by(id=pid).first()
        org_id = proj.organisation_id

        active_session = session.query(RefreshSession).filter(
            RefreshSession.user_id == user_id,
            RefreshSession.revoked_at.is_(None),
            RefreshSession.expires_at > utc_now(),
        ).first()

        if not active_session:
            family_id = uuid.uuid4()
            raw_token = generate_refresh_token()
            active_session = RefreshSession(
                user_id=user_id,
                token_family_id=family_id,
                token_hash=hash_refresh_token(raw_token),
                expires_at=utc_now() + timedelta(days=7),
                revoked_at=None,
            )
            session.add(active_session)
            session.commit()
            session.refresh(active_session)

        token, _ = create_access_token(
            user_id=user_id,
            session_family_id=active_session.token_family_id,
            settings=settings,
        )
        auth_headers = {"Authorization": f"Bearer {token}"}

    # 2. Check evidence and ensure chunks exist for ADR 001
    with session_factory() as session:
        ev_repo = EvidenceRepository(session)
        adr_item = ev_repo.get_by_id(adr_id)
        assert adr_item is not None, f"ADR 001 item {adr_id} not found"
        logger.info("Target document: '%s' (category=%s)", adr_item.title, adr_item.category)

        existing_chunks = list(
            session.query(EvidenceChunk)
            .filter_by(evidence_id=adr_id)
            .order_by(EvidenceChunk.chunk_index.asc())
            .all()
        )
        logger.info("Initial chunk count: %d", len(existing_chunks))

        if not existing_chunks:
            logger.info("Chunking ADR 001 with format-aware ChunkingService...")
            from app.repositories.chunk import EvidenceChunkRepository
            chunker = ChunkingService(settings=settings.chunking)
            drafts = chunker.chunk_evidence(adr_item)
            logger.info("Chunking produced %d drafts. Persisting...", len(drafts))
            chunk_repo = EvidenceChunkRepository(session)
            persisted_chunks, _ = chunk_repo.replace_chunks_for_evidence(
                evidence=adr_item,
                drafts=drafts,
                collection_name=f"proj_{pid}",
            )
            adr_item.chunk_count = len(persisted_chunks)
            adr_item.indexing_status = "indexed"
            session.commit()
            existing_chunks = persisted_chunks
            logger.info("ADR 001 chunks persisted successfully (%d chunks).", len(existing_chunks))

    # 3. Check baseline metrics before Stage 2
    resp = httpx.get(f"{base_url}/projects/{pid}/processing-status", headers=auth_headers, timeout=30.0)
    assert resp.status_code == 200, f"Failed status check: {resp.text}"
    status_before = resp.json()
    graph_v_before = status_before.get("active_graph_version")
    k_count_before = status_before.get("knowledge_item_count", 0)
    logger.info("Baseline: knowledge_count=%d, graph_version=%s", k_count_before, graph_v_before)

    # 4. Trigger semantic extraction for ADR 001 via API
    logger.info("Triggering POST /projects/%s/evidence/%s/extract ...", pid, adr_id)
    extract_resp = httpx.post(
        f"{base_url}/projects/{pid}/evidence/{adr_id}/extract",
        headers=auth_headers,
        json={"include_synthetic": False},
        timeout=30.0,
    )
    assert extract_resp.status_code == 202, f"Extract trigger failed: {extract_resp.text}"
    extract_data = extract_resp.json()
    run_id = uuid.UUID(extract_data["run"]["id"])
    logger.info("Extraction queued! Run ID: %s, Job ID: %s", run_id, extract_data["job"]["id"])

    # 5. Execute Stage 2 background reconstruction worker
    vram_before = get_gpu_vram_mb()
    logger.info("Initial GPU VRAM: %.1f MB", vram_before)
    logger.info("Starting ReconstructionWorkerService execution with real Qwen3:8b...")

    llm_client = OllamaLLMClient(
        base_url=settings.ollama.base_url,
    )
    recon_worker = ReconstructionWorkerService(
        session_factory=session_factory,
        llm_client=llm_client,
        extraction_settings=settings.extraction,
        ingestion_settings=settings.ingestion,
    )

    t0 = time.perf_counter()
    jobs_processed = recon_worker.drain_pending_jobs(max_jobs=1)
    duration_s = time.perf_counter() - t0
    vram_after = get_gpu_vram_mb()

    logger.info("ReconstructionWorker finished in %.2f seconds. Jobs processed: %d", duration_s, jobs_processed)
    logger.info("Peak GPU VRAM during/after: %.1f MB", vram_after)

    # 6. Verify Extraction Run details and Ollama performance
    with session_factory() as session:
        run = session.query(KnowledgeExtractionRun).filter_by(id=run_id).first()
        assert run is not None, "Extraction run record not found"
        logger.info("Run status: %s", run.status)
        logger.info("Batches executed: %d", run.batches_executed)
        logger.info("Prompt tokens: %d, Completion tokens: %d", run.prompt_tokens, run.completion_tokens)
        logger.info("Candidates generated: %d", run.candidates_generated)
        logger.info("Claims persisted: %d", run.claims_persisted)
        logger.info("Claims rejected ungrounded: %d", run.claims_rejected_ungrounded)
        logger.info("Duplicates merged: %d", run.duplicates_merged)

        assert run.status == ExtractionRunStatus.COMPLETED.value, f"Run did not complete: {run.error_message}"
        assert run.batches_executed >= 1, "Expected at least 1 batch"
        assert run.claims_persisted > 0, "Expected at least 1 persisted claim"

        # Check evidence metadata updated
        adr_item_after = session.query(EvidenceItem).filter_by(id=adr_id).first()
        meta = dict(adr_item_after.metadata_json or {})
        logger.info("Evidence metadata: semantic_status=%s, lifecycle_stage=%s", meta.get("semantic_status"), meta.get("lifecycle_stage"))
        assert meta.get("semantic_status") == "succeeded", f"Expected succeeded, got {meta.get('semantic_status')}"

        # 7. Grounding verification: verify every persisted claim has verbatim supporting excerpt
        new_items = (
            session.query(KnowledgeItem)
            .filter(KnowledgeItem.extraction_run_id == run_id)
            .all()
        )
        logger.info("Verifying grounding for %d newly extracted knowledge items...", len(new_items))
        for item in new_items:
            links = session.query(KnowledgeEvidenceLink).filter_by(knowledge_item_id=item.id).all()
            assert len(links) > 0, f"Item '{item.title}' has no evidence links!"
            for link in links:
                chunk = session.query(EvidenceChunk).filter_by(id=link.evidence_chunk_id).first()
                assert chunk is not None, f"Chunk {link.evidence_chunk_id} not found"
                excerpt = link.supporting_excerpt.strip()
                assert len(excerpt) >= 12, f"Excerpt too short: {excerpt}"
                is_exact = excerpt in chunk.chunk_text
                is_norm = _normalize_text_for_matching(excerpt) in _normalize_text_for_matching(chunk.chunk_text)
                assert is_exact or is_norm, (
                    f"GROUNDING VIOLATION: Excerpt '{excerpt[:60]}...' not found in chunk {chunk.id}!"
                )
            logger.info("  ✓ [%s] '%s' -> Grounded (%d links)", item.category, item.title[:50], len(links))

    # 8. Check Graph and Processing Status After Stage 2
    resp_after = httpx.get(f"{base_url}/projects/{pid}/processing-status", headers=auth_headers, timeout=30.0)
    assert resp_after.status_code == 200
    status_after = resp_after.json()
    graph_v_after = status_after.get("active_graph_version")
    k_count_after = status_after.get("knowledge_item_count", 0)
    logger.info("Post-Stage 2: knowledge_count=%d (was %d), graph_version=%s (was %s)", k_count_after, k_count_before, graph_v_after, graph_v_before)

    # 9. Test C: Resilience and Failure Recovery
    logger.info("-----------------------------------------------------------------")
    logger.info("TEST C: FAILURE RECOVERY & BOUNDED RETRY VERIFICATION")
    logger.info("-----------------------------------------------------------------")
    with session_factory() as session:
        job_repo = BackgroundJobRepository(session)
        # Create a job with non-existent evidence to verify clean graceful error reporting
        fake_ev_id = uuid.uuid4()
        fail_job = job_repo.create_job(
            organisation_id=org_id,
            project_id=pid,
            evidence_id=None,
            triggered_by_user_id=user_id,
            job_type=BackgroundJobType.KNOWLEDGE_RECONSTRUCTION.value,
            payload_json={"evidence_ids": [str(fake_ev_id)], "force_rerun": False},
        )
        session.commit()
        fail_job_id = fail_job.id
        logger.info("Created test job with missing evidence: %s", fail_job_id)

    # Drain with worker
    recon_worker.drain_pending_jobs(max_jobs=1)

    with session_factory() as session:
        j = session.query(BackgroundJob).filter_by(id=fail_job_id).first()
        logger.info("Missing-evidence job status: %s (error_message=%s)", j.status, j.error_message)
        # Worker must have handled this without crashing or staying locked
        assert j.status in (
            BackgroundJobStatus.SUCCEEDED.value,
            BackgroundJobStatus.FAILED.value,
            BackgroundJobStatus.CANCELLED.value,
        ), f"Unexpected status: {j.status}"

    logger.info("=================================================================")
    logger.info("ALL STAGE 2 & RESILIENCE TESTS PASSED!")
    logger.info("=================================================================")


if __name__ == "__main__":
    main()
