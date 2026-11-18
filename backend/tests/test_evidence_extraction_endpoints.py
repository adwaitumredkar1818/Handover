"""Test suite verifying per-evidence extraction endpoints and facts/findings retrieval."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.models.enums import (
    BackgroundJobType,
    EvidenceProcessingStatus,
    EvidenceSourceType,
    ExtractionRunStatus,
    KnowledgeCategory,
)
from app.repositories.evidence import EvidenceRepository
from app.repositories.job import BackgroundJobRepository
from app.services.chunking import ChunkingService
from app.services.indexing_worker import IndexingWorkerService
from app.services.reconstruction_worker import ReconstructionWorkerService
from tests.test_knowledge_reconstruction_api_and_security import (
    InMemoryEmbeddingService,
    InMemoryVectorStoreClient,
    ScriptedFakeLLMClient,
    _page,
    _seed_project_member,
    isolated_auth_app,
    register_and_login_user,
)


def test_evidence_extractions_facts_and_findings_endpoints(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_embed = InMemoryEmbeddingService(dims=64)
    fake_chroma = InMemoryVectorStoreClient(expected_dimensions=64)
    fake_llm = ScriptedFakeLLMClient(fail_first_invalid_json=False)

    with isolated_auth_app(
        monkeypatch,
        upload_storage_path=tmp_path / "extractions_test_uploads",
        embedding_expected_dimensions=64,
        extraction_auto_reextract_on_update=False,
    ) as ctx:
        indexing_worker = IndexingWorkerService(
            session_factory=ctx.session_factory,
            chunking_service=ChunkingService(settings=ctx.settings.chunking),
            embedding_service=fake_embed,
            vector_store=fake_chroma,
            ingestion_settings=ctx.settings.ingestion,
            extraction_settings=ctx.settings.extraction,
            llm_model_name=ctx.settings.ollama.llm_model,
        )
        recon_worker = ReconstructionWorkerService(
            session_factory=ctx.session_factory,
            llm_client=fake_llm,
            extraction_settings=ctx.settings.extraction,
            ingestion_settings=ctx.settings.ingestion,
        )

        with TestClient(ctx.app) as client:
            owner = register_and_login_user(
                client, email="ev-owner@example.com", full_name="EV Owner"
            )
            org = client.post(
                "/api/v1/organisations",
                headers=owner.headers,
                json={"name": "EV Org"},
            ).json()
            proj = client.post(
                f"/api/v1/organisations/{org['id']}/projects",
                headers=owner.headers,
                json={"name": "EV Proj", "status": "active", "visibility": "private"},
            ).json()

            oid = uuid.UUID(org["id"])
            pid = uuid.UUID(proj["id"])
            t_now = datetime(2026, 10, 15, tzinfo=UTC)

            # 1. Create evidence item with extracted text & index it
            with ctx.session_factory() as session:
                ev_repo = EvidenceRepository(session)
                text_content = (
                    "Alex Chen selected PostgreSQL 16 as our canonical store. "
                    "Priya Nair maintains the FastAPI ingestion worker."
                )
                ev = ev_repo.create_evidence_item(
                    organisation_id=oid,
                    project_id=pid,
                    uploaded_by_user_id=owner.user_id,
                    source_type=EvidenceSourceType.DOCUMENT_UPLOAD.value,
                    source_provider="local_upload",
                    category="pdf_document",
                    source_external_id="upload:test-trd-doc",
                    source_url=None,
                    source_author_identity="Alex Chen",
                    title="05_Technical_Requirements_Document.pdf",
                    original_filename="05_Technical_Requirements_Document.pdf",
                    mime_type="application/pdf",
                    file_size_bytes=1024,
                    content_hash="aa" * 32,
                    storage_provider=None,
                    storage_object_key=None,
                    encryption_algorithm=None,
                    encryption_key_id=None,
                    acl_scope="project_members",
                    source_created_at=t_now,
                    source_updated_at=t_now,
                    extracted_at=t_now,
                    processing_status=EvidenceProcessingStatus.EXTRACTED.value,
                    extraction_method="pymupdf",
                    page_count=2,
                    metadata_json={},
                )
                ev_repo.replace_extracted_content(
                    evidence_id=ev.id,
                    extracted_text=text_content,
                    warnings=(),
                    pages=(_page(text_content, section="Section 1"),),
                )
                BackgroundJobRepository(session).create_job(
                    organisation_id=oid,
                    project_id=pid,
                    evidence_id=ev.id,
                    triggered_by_user_id=owner.user_id,
                    job_type=BackgroundJobType.EVIDENCE_INDEXING.value,
                )
                session.commit()

            assert indexing_worker.drain_pending_jobs(max_jobs=5) == 1

            # 2. Test initial facts retrieval before extraction (should return raw chunks, 0 AI facts)
            f0 = client.get(
                f"/api/v1/projects/{proj['id']}/evidence/{ev.id}/facts",
                headers=owner.headers,
            )
            assert f0.status_code == 200
            facts_data0 = f0.json()
            assert facts_data0["evidence_id"] == str(ev.id)
            assert facts_data0["ai_extracted_count"] == 0
            assert facts_data0["raw_chunk_count"] >= 1
            assert len(facts_data0["raw_chunks"]) >= 1

            # 3. Trigger extraction using POST /evidence/{evidence_id}/extractions
            trig = client.post(
                f"/api/v1/projects/{proj['id']}/evidence/{ev.id}/extractions",
                headers=owner.headers,
                json={"categories": [KnowledgeCategory.DECISIONS_RATIONALE.value]},
            )
            assert trig.status_code == 202
            run_id = trig.json()["run"]["id"]

            # Drain job
            assert recon_worker.drain_pending_jobs(max_jobs=5) == 1

            # 4. GET /evidence/{evidence_id}/extractions
            runs_res = client.get(
                f"/api/v1/projects/{proj['id']}/evidence/{ev.id}/extractions",
                headers=owner.headers,
            )
            assert runs_res.status_code == 200
            runs_data = runs_res.json()
            assert runs_data["total"] >= 1
            assert runs_data["items"][0]["id"] == run_id
            assert runs_data["items"][0]["status"] == ExtractionRunStatus.COMPLETED.value

            # 5. GET /evidence/{evidence_id}/extractions/{run_id}
            run_res = client.get(
                f"/api/v1/projects/{proj['id']}/evidence/{ev.id}/extractions/{run_id}",
                headers=owner.headers,
            )
            assert run_res.status_code == 200
            assert run_res.json()["id"] == run_id

            # 6. GET /evidence/{evidence_id}/facts (now has AI extracted facts!)
            facts_res = client.get(
                f"/api/v1/projects/{proj['id']}/evidence/{ev.id}/facts",
                headers=owner.headers,
            )
            assert facts_res.status_code == 200
            facts_data = facts_res.json()
            assert facts_data["ai_extracted_count"] >= 1
            assert len(facts_data["facts"]) >= 1
            first_fact = facts_data["facts"][0]
            assert first_fact["validation_state"] == "candidate"
            assert first_fact["is_ai_extracted"] is True
            assert first_fact["grounding_score"] >= 0.0
            assert first_fact["original_excerpt"] != ""

            # 7. GET /evidence/{evidence_id}/findings
            findings_res = client.get(
                f"/api/v1/projects/{proj['id']}/evidence/{ev.id}/findings",
                headers=owner.headers,
            )
            assert findings_res.status_code == 200
            findings_data = findings_res.json()
            assert findings_data["total"] >= 1
            assert len(findings_data["items"]) >= 1
            first_finding = findings_data["items"][0]
            assert first_finding["review_status"] in {"candidate", "pending_review"}
