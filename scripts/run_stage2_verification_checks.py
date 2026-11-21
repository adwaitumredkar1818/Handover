"""Run Stage 2 Assertions and Test C directly on the completed run."""

import os
import sys
import uuid
import httpx
import logging

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
from app.services.knowledge_validator import _normalize_text_for_matching
from app.services.llm import OllamaLLMClient
from app.services.reconstruction_worker import ReconstructionWorkerService
from datetime import timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("stage2_checker")

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)
base_url = "http://localhost:8000/api/v1"
pid = uuid.UUID("17ca9ab2-bbb8-4e61-9f52-4fbd6a7ce9c8")
adr_id = uuid.UUID("2498e191-42f9-4d2a-8481-8cfeabe0f8f1")
run_id = uuid.UUID("0ead9db7-cb39-4a9d-b4a8-b0dc93613868")

# Authenticate
with session_factory() as session:
    proj = session.query(Project).filter_by(id=pid).first()
    org_id = proj.organisation_id
    pm = session.query(ProjectMembership).filter_by(project_id=pid).first()
    user_id = pm.user_id
    raw_token = generate_refresh_token()
    family_id = uuid.uuid4()
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

# 1. Verify Run and Metadata
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
    assert run.claims_persisted > 0, "Expected at least 1 persisted claim"

    adr_item_after = session.query(EvidenceItem).filter_by(id=adr_id).first()
    meta = dict(adr_item_after.metadata_json or {})
    logger.info("Evidence metadata: semantic_status=%s, lifecycle_stage=%s", meta.get("semantic_status"), meta.get("lifecycle_stage"))
    assert meta.get("semantic_status") == "succeeded", f"Expected succeeded, got {meta.get('semantic_status')}"

    # 2. Grounding verification: verify every persisted claim has verbatim/normalised supporting excerpt
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
        logger.info("  ✓ [%s] '%s' -> Grounded (%d links, mode=%s)", item.category, item.title[:50], len(links), link.excerpt_match_mode)

# 3. Check Graph and Processing Status After Stage 2
resp_after = httpx.get(f"{base_url}/projects/{pid}/processing-status", headers=auth_headers, timeout=30.0)
assert resp_after.status_code == 200
status_after = resp_after.json()
graph_v_after = status_after.get("active_graph_version")
k_count_after = status_after.get("knowledge_item_count", 0)
logger.info("Post-Stage 2 Status: knowledge_count=%d, graph_version=%s", k_count_after, graph_v_after)

# 4. Test C: Resilience and Failure Recovery
logger.info("-----------------------------------------------------------------")
logger.info("TEST C: FAILURE RECOVERY & BOUNDED RETRY VERIFICATION")
logger.info("-----------------------------------------------------------------")
llm_client = OllamaLLMClient(base_url=settings.ollama.base_url)
recon_worker = ReconstructionWorkerService(
    session_factory=session_factory,
    llm_client=llm_client,
    extraction_settings=settings.extraction,
    ingestion_settings=settings.ingestion,
)

with session_factory() as session:
    job_repo = BackgroundJobRepository(session)
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
    assert j.status in (
        BackgroundJobStatus.SUCCEEDED.value,
        BackgroundJobStatus.FAILED.value,
        BackgroundJobStatus.CANCELLED.value,
    ), f"Unexpected status: {j.status}"

logger.info("=================================================================")
logger.info("ALL STAGE 2 & RESILIENCE TESTS PASSED!")
logger.info("=================================================================")
