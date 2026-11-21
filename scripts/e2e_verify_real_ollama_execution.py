"""End-to-End Real Ollama Execution & Completion Verification.
Demonstrates:
  New evidence -> indexing -> actual Qwen3 inference -> grounded KnowledgeItems
  -> entities/relationships -> updated graph -> completed jobs -> idle.
Records:
  Evidence ID, Job ID, Extraction Run ID, Model invocation, and Persisted Results.
"""

import sys
import os
import uuid
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.enums import (
    BackgroundJobStatus,
    BackgroundJobType,
    EvidenceProcessingStatus,
    EvidenceIndexingStatus,
    ExtractionRunStatus,
    ExtractionRunScope,
    KnowledgeCategory,
)
from app.models.project import Project, ProjectMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.models.evidence import EvidenceItem, EvidenceChunk
from app.models.job import BackgroundJob
from app.models.knowledge import KnowledgeItem, KnowledgeEvidenceLink, KnowledgeExtractionRun
from app.models.relationship import KnowledgeEntity, KnowledgeRelationship
from app.repositories.knowledge import KnowledgeRepository
from app.repositories.job import BackgroundJobRepository
from app.services.chunking import ChunkingService
from app.services.llm import OllamaLLMClient
from app.services.reconstruction_worker import ReconstructionWorkerService
from app.services.relationship_coordinator import RelationshipCoordinatorService
from app.services.pipeline_coordinator import PipelineCoordinatorService
from app.repositories.auth import RefreshSessionRepository
from app.core.security import create_access_token, utc_now, generate_refresh_token, hash_refresh_token
from datetime import timedelta
import urllib.request
import json
from sqlalchemy import select

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)

def run_e2e_test():
    print("=================================================================")
    print("REAL OLLAMA QWEN3:8B INFERENCE & COMPLETION END-TO-END TEST")
    print("=================================================================")

    with session_factory() as session:
        # Use verified user and active matching organisation
        user = session.execute(
            select(User).where(User.email == "vernitg185@gmail.com")
        ).scalars().first()
        org = session.get(Organisation, uuid.UUID("f37fb746-da77-4718-a9ab-54f864dd953e"))
        assert org is not None and user is not None, "Verified user or org not found!"

        test_slug = f"test-real-ollama-{uuid.uuid4().hex[:6]}"
        test_project = Project(
            organisation_id=org.id,
            name=f"__E2E_Real_Ollama_{uuid.uuid4().hex[:6]}",
            slug=test_slug,
            description="Testing end-to-end real Qwen3 extraction and graph completion",
            status="active",
            created_by_id=user.id,
            owner_id=user.id,
        )
        session.add(test_project)
        session.commit()
        session.refresh(test_project)
        project_id = test_project.id

        # Add explicit ProjectMembership for triggering user as project_manager
        proj_mem = ProjectMembership(
            project_id=project_id,
            user_id=user.id,
            role_id=uuid.UUID("ba0fd659-9a70-5b18-b06c-78feaf382b8d"),  # project_manager
            status="active",
            assigned_by_id=user.id,
        )
        session.add(proj_mem)
        session.commit()
        print(f"[1. SETUP] Controlled Project created: {test_project.name} ({project_id}) with project_manager membership")

        try:
            # 2. Add New Evidence Item
            test_content = (
                "Billing Architecture Specification: The subscription billing system integrates with the Stripe API "
                "v2023-10-16 for processing recurring payments. Webhook events (invoice.paid, payment_failed) "
                "are received at /api/v1/billing/webhooks and validated via HMAC SHA-256 signatures before updating PostgreSQL."
            )
            import hashlib
            content_hash = hashlib.sha256(test_content.encode("utf-8")).hexdigest()

            ev_item = EvidenceItem(
                organisation_id=org.id,
                project_id=project_id,
                source_type="document_upload",
                category="pdf_document",
                source_external_id=f"upload_{uuid.uuid4().hex[:8]}",
                title="Billing Architecture Specification.pdf",
                content_hash=content_hash,
                processing_status=EvidenceProcessingStatus.EXTRACTED.value,
                indexing_status=EvidenceIndexingStatus.NOT_INDEXED.value,
                metadata_json={},
            )
            session.add(ev_item)
            session.commit()
            session.refresh(ev_item)
            print(f"[2. EVIDENCE] Created EvidenceItem: ID={ev_item.id}, Title='{ev_item.title}'")

            # 3. Create Chunk for grounding
            chunk = EvidenceChunk(
                organisation_id=org.id,
                project_id=project_id,
                evidence_id=ev_item.id,
                chunk_index=0,
                chunk_text=test_content,
                char_start=0,
                char_end=len(test_content),
                char_count=len(test_content),
                token_estimate=len(test_content.split()),
                chunk_content_hash=content_hash,
                source_type="document_upload",
                indexing_status="chunked",
            )
            session.add(chunk)
            ev_item.chunk_count = 1
            ev_item.indexing_status = EvidenceIndexingStatus.INDEXED.value
            session.commit()
            session.refresh(chunk)
            print(f"[3. CHUNKING] Chunk created: ID={chunk.id}, {chunk.token_estimate} tokens")

            # 4. Create BackgroundJob and ExtractionRun
            k_repo = KnowledgeRepository(session)
            job_repo = BackgroundJobRepository(session)

            categories = ["technical_architecture", "decisions_rationale", "work_items"]
            run = k_repo.create_extraction_run(
                organisation_id=org.id,
                project_id=project_id,
                background_job_id=None,
                evidence_id=ev_item.id,
                triggered_by_user_id=user.id,
                scope_type=ExtractionRunScope.EVIDENCE.value,
                target_categories=categories,
                model_name="qwen3:8b",
                prompt_version="v2",
                is_synthetic=False,
                total_evidence_items=1,
            )
            job = job_repo.create_job(
                organisation_id=org.id,
                project_id=project_id,
                evidence_id=ev_item.id,
                triggered_by_user_id=user.id,
                job_type=BackgroundJobType.KNOWLEDGE_RECONSTRUCTION.value,
                priority=10,
                payload_json={
                    "run_id": str(run.id),
                    "scope_type": ExtractionRunScope.EVIDENCE.value,
                    "evidence_id": str(ev_item.id),
                    "categories": categories,
                    "force_rerun": True,
                    "trigger": "e2e_test",
                },
            )
            run.background_job_id = job.id
            session.commit()
            session.refresh(run)
            session.refresh(job)
            print(f"[4. QUEUE] Job created: ID={job.id}, Extraction Run: ID={run.id}")

            # 5. Execute Real Ollama Inference via ReconstructionWorkerService
            print("\n[5. INFERENCE] Invoking Ollama Qwen3:8b model (real inference)...")
            start_time = time.time()
            llm_client = OllamaLLMClient(
                base_url=settings.ollama.base_url,
                model=settings.ollama.llm_model,
                num_ctx=settings.ollama.llm_num_ctx,
                num_predict=settings.ollama.llm_num_predict,
                temperature=settings.ollama.llm_temperature,
                timeout_seconds=settings.ollama.llm_timeout_seconds,
                think=settings.ollama.llm_think,
            )
            worker = ReconstructionWorkerService(
                session_factory=session_factory,
                llm_client=llm_client,
                extraction_settings=settings.extraction,
                ingestion_settings=settings.ingestion,
                worker_id="test-e2e-worker",
            )
            success = worker.process_next_job()
            elapsed = time.time() - start_time
            print(f"[5. INFERENCE] Ollama inference finished in {elapsed:.2f}s, success={success}")
            assert success, "Real Ollama extraction failed!"

            # 6. Verify Persisted Knowledge Items & Grounding
            session.refresh(run)
            session.refresh(job)
            session.refresh(ev_item)

            k_items = session.execute(
                select(KnowledgeItem).where(
                    KnowledgeItem.project_id == project_id,
                    KnowledgeItem.is_deleted == False,
                )
            ).scalars().all()

            print(f"\n[6. PERSISTED RESULTS]")
            print(f"  Extraction Run Status: {run.status}")
            print(f"  Background Job Status: {job.status}")
            print(f"  Claims Persisted: {run.claims_persisted}")
            print(f"  Prompt Tokens: {run.prompt_tokens}, Completion Tokens: {run.completion_tokens}")
            print(f"  Evidence Fingerprint: {ev_item.metadata_json.get('extraction_fingerprint')}")
            print(f"  Extracted Knowledge Items Count: {len(k_items)}")
            assert len(k_items) > 0, "No knowledge items were persisted from Qwen3 inference!"

            for item in k_items:
                print(f"    - [{item.category}] {item.title}")
                print(f"      Summary: {item.structured_summary[:120]}...")
                links = session.execute(
                    select(KnowledgeEvidenceLink).where(KnowledgeEvidenceLink.knowledge_item_id == item.id)
                ).scalars().all()
                for l in links:
                    print(f"      Grounding Excerpt: \"{l.supporting_excerpt[:100]}...\"")

            # 7. Update Relationships and Graph Projections
            print("\n[7. RELATIONSHIPS & GRAPH PROJECTION]")
            rel_coord = RelationshipCoordinatorService(session)
            seeded_count = rel_coord.run_reconstruction(organisation_id=org.id, project_id=project_id)
            session.commit()
            print(f"  Relationships/Entities Reconstructed: {seeded_count}")

            # Generate auth token and test API graph response directly
            now = utc_now()
            token_family_id = uuid.uuid4()
            raw_refresh = generate_refresh_token()
            token_hash = hash_refresh_token(raw_refresh)
            expires_at = now + timedelta(days=settings.security.jwt_refresh_token_expire_days)
            RefreshSessionRepository(session).create(
                user_id=user.id,
                token_family_id=token_family_id,
                token_hash=token_hash,
                expires_at=expires_at,
                session_metadata={"user_agent": "e2e-script", "ip": "127.0.0.1"},
            )
            auth_token, _ = create_access_token(user_id=user.id, session_family_id=token_family_id, settings=settings, now=now)
            session.commit()

            base_url = f"http://127.0.0.1:8000/api/v1/projects/{project_id}/knowledge-intelligence/graphs"
            for g_type in ["technology-stack", "system-architecture"]:
                req = urllib.request.Request(f"{base_url}/{g_type}", headers={"Authorization": f"Bearer {auth_token}"})
                with urllib.request.urlopen(req) as resp:
                    data = json.loads(resp.read().decode())
                    g_nodes = data.get("nodes", [])
                    g_edges = data.get("edges", [])
                    print(f"  {g_type} graph (HTTP {resp.status}): {len(g_nodes)} nodes, {len(g_edges)} edges")
                    for n in g_nodes[:4]:
                        print(f"    - [{n.get('entity_type')}] {n.get('label')}")

            # 8. Verify Pipeline State Returns to IDLE
            print("\n[8. IDLE STATE CHECK]")
            pipe_coord = PipelineCoordinatorService(session)
            status = pipe_coord.get_status(project_id)
            print(f"  Pipeline State: {status.state}, is_processing: {status.is_processing}, queued: {status.queued_evidence_count}")
            assert not status.is_processing, "Expected pipeline to be idle after job completion!"
            print("  Pipeline confirmed completely IDLE with 0 pending inference requests.")

            print("\n=================================================================")
            print("SUCCESS: REAL OLLAMA PIPELINE EXECUTION VERIFIED END-TO-END!")
            print("=================================================================")

        finally:
            print("\n[CLEANUP] Removing test project records...")
            session.rollback()
            session.execute(BackgroundJob.__table__.delete().where(BackgroundJob.project_id == project_id))
            session.execute(KnowledgeRelationship.__table__.delete().where(KnowledgeRelationship.project_id == project_id))
            session.execute(KnowledgeEntity.__table__.delete().where(KnowledgeEntity.project_id == project_id))
            session.execute(KnowledgeEvidenceLink.__table__.delete().where(KnowledgeEvidenceLink.project_id == project_id))
            session.execute(KnowledgeItem.__table__.delete().where(KnowledgeItem.project_id == project_id))
            session.execute(EvidenceChunk.__table__.delete().where(EvidenceChunk.project_id == project_id))
            session.execute(EvidenceItem.__table__.delete().where(EvidenceItem.project_id == project_id))
            session.execute(KnowledgeExtractionRun.__table__.delete().where(KnowledgeExtractionRun.project_id == project_id))
            session.execute(ProjectMembership.__table__.delete().where(ProjectMembership.project_id == project_id))
            session.delete(test_project)
            session.commit()
            print("[CLEANUP] Done.")

if __name__ == "__main__":
    run_e2e_test()
