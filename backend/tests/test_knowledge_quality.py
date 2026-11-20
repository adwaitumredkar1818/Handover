"""Unit and integration tests for real-time Knowledge Quality Engine."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.models.enums import (
    EpistemicStatus,
    EvidenceSourceType,
    KnowledgeCategory,
    KnowledgeReviewStatus,
    RelationshipBasis,
    RelationshipVerificationStatus,
    TraceabilityCompletenessStatus,
    VerificationCaseStatus,
)
from app.models.evidence import EvidenceItem
from app.models.knowledge import KnowledgeEvidenceLink, KnowledgeItem
from app.models.relationship import (
    DecisionTraceabilityChain,
    KnowledgeEntity,
    KnowledgeRelationship,
)
from app.models.verification import VerificationCase
from app.services.knowledge_quality import KnowledgeQualityEngine
from tests.conftest import (
    isolated_auth_app,
    register_and_login_user,
)


def _create_org_and_project(
    client: TestClient, headers: dict[str, str], slug_suffix: str
) -> tuple[str, str]:
    org_resp = client.post(
        "/api/v1/organisations",
        headers=headers,
        json={"name": f"Org {slug_suffix}", "slug": f"org-{slug_suffix}"},
    )
    assert org_resp.status_code == 201, org_resp.text
    org_id = org_resp.json()["id"]

    proj_resp = client.post(
        f"/api/v1/organisations/{org_id}/projects",
        headers=headers,
        json={
            "name": f"Project {slug_suffix}",
            "slug": f"proj-{slug_suffix}",
        },
    )
    assert proj_resp.status_code == 201, proj_resp.text
    return org_id, proj_resp.json()["id"]


def test_empty_project_knowledge_quality(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty project with 0 items must report exactly 0.0% overall and 0.0% across all dimensions."""
    with isolated_auth_app(monkeypatch) as ctx:
        with TestClient(ctx.app) as client:
            owner = register_and_login_user(client, email="owner_empty@example.com", full_name="Empty Owner")
            _, proj_id_str = _create_org_and_project(client, owner.headers, "empty-kq")
            proj_id = uuid.UUID(proj_id_str)

            with ctx.session_factory() as session:
                engine = KnowledgeQualityEngine(session)
                res = engine.assess_project_quality(project_id=proj_id, user_id=owner.user_id)

                assert res["project_id"] == str(proj_id)
                assert res["overall_quality_score"] == 0.0
                assert res["total_items"] == 0
                assert res["verified_items"] == 0
                assert res["stale_items"] == 0

                scores = res["dimension_scores"]
                for dim, val in scores.items():
                    assert val == 0.0, f"Expected {dim} to be 0.0, got {val}"

                assert len(res["identified_gaps"]) >= 1
                assert res["identified_gaps"][0]["type"] == "no_extracted_knowledge"


def test_populated_project_real_time_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    """Populated project evaluates live evidence, verification, components, chains, and risk mitigations."""
    with isolated_auth_app(monkeypatch) as ctx:
        with TestClient(ctx.app) as client:
            owner = register_and_login_user(client, email="owner_pop@example.com", full_name="Pop Owner")
            org_id_str, proj_id_str = _create_org_and_project(client, owner.headers, "pop-kq")
            org_id, proj_id = uuid.UUID(org_id_str), uuid.UUID(proj_id_str)

            with ctx.session_factory() as session:
                now = datetime.now(UTC)

                # Seed evidence
                ev = EvidenceItem(
                    organisation_id=org_id,
                    project_id=proj_id,
                    source_type=EvidenceSourceType.DOCUMENT_UPLOAD.value,
                    source_provider="document_upload",
                    category="design_document",
                    source_external_id=f"src-{uuid.uuid4().hex[:8]}",
                    source_url="https://docs.example.com/arch",
                    source_author_identity="dev@example.com",
                    source_created_at=now,
                    title="Architecture and Runbook Spec",
                    content_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                    acl_scope="project_members",
                    uploaded_by_user_id=owner.user_id,
                )
                session.add(ev)
                session.flush()

                # 1. Architecture item (human verified + grounded)
                ki_arch = KnowledgeItem(
                    organisation_id=org_id,
                    project_id=proj_id,
                    category=KnowledgeCategory.TECHNICAL_ARCHITECTURE.value,
                    support_classification="direct",
                    title="Microservice Architecture Overview",
                    structured_summary="Platform uses modular FastAPI microservices.",
                    structured_payload={"services": ["api", "worker"]},
                    extraction_model="qwen3:8b",
                    prompt_version="p2.6-v1",
                    fingerprint=uuid.uuid4().hex,
                    epistemic_status=EpistemicStatus.HUMAN_VERIFIED.value,
                    review_status=KnowledgeReviewStatus.APPROVED.value,
                    confidence_metadata_json={"confidence": 0.95},
                )
                session.add(ki_arch)
                session.flush()

                link1 = KnowledgeEvidenceLink(
                    organisation_id=org_id,
                    project_id=proj_id,
                    knowledge_item_id=ki_arch.id,
                    evidence_id=ev.id,
                    support_type="direct",
                    supporting_excerpt="Architecture uses modular FastAPI microservices.",
                )
                session.add(link1)

                # 2. Operational runbook item (grounded)
                ki_runbook = KnowledgeItem(
                    organisation_id=org_id,
                    project_id=proj_id,
                    category=KnowledgeCategory.OPERATIONAL_HISTORICAL.value,
                    support_classification="direct",
                    title="Deployment Runbook & Environment Setup",
                    structured_summary="Deployment runbook instructions and rollback steps.",
                    structured_payload={"runbook": True},
                    extraction_model="qwen3:8b",
                    prompt_version="p2.6-v1",
                    fingerprint=uuid.uuid4().hex,
                    epistemic_status=EpistemicStatus.EXTRACTED.value,
                    review_status=KnowledgeReviewStatus.PENDING_REVIEW.value,
                    confidence_metadata_json={"confidence": 0.88},
                )
                session.add(ki_runbook)
                session.flush()

                link2 = KnowledgeEvidenceLink(
                    organisation_id=org_id,
                    project_id=proj_id,
                    knowledge_item_id=ki_runbook.id,
                    evidence_id=ev.id,
                    support_type="direct",
                    supporting_excerpt="Deployment runbook instructions.",
                )
                session.add(link2)

                # 3. Decision item
                ki_decision = KnowledgeItem(
                    organisation_id=org_id,
                    project_id=proj_id,
                    category=KnowledgeCategory.DECISIONS_RATIONALE.value,
                    support_classification="direct",
                    title="Adopt PostgreSQL for Canonical Storage",
                    structured_summary="Decided on PostgreSQL for canonical persistence.",
                    structured_payload={"decision": "PostgreSQL"},
                    extraction_model="qwen3:8b",
                    prompt_version="p2.6-v1",
                    fingerprint=uuid.uuid4().hex,
                    epistemic_status=EpistemicStatus.EXTRACTED.value,
                    review_status=KnowledgeReviewStatus.PENDING_REVIEW.value,
                    confidence_metadata_json={"confidence": 0.9},
                )
                session.add(ki_decision)
                session.flush()

                # 4. Risk item with mitigation in structured_payload and summary (tests r.content fix)
                ki_risk = KnowledgeItem(
                    organisation_id=org_id,
                    project_id=proj_id,
                    category=KnowledgeCategory.BUGS_BLOCKERS_RISKS.value,
                    support_classification="direct",
                    title="Risk of Database Connection Saturation",
                    structured_summary="Potential connection pool exhaustion; mitigation via connection pooler.",
                    structured_payload={"status": "mitigated", "mitigation": "Use Supabase transaction pooler"},
                    extraction_model="qwen3:8b",
                    prompt_version="p2.6-v1",
                    fingerprint=uuid.uuid4().hex,
                    epistemic_status=EpistemicStatus.EXTRACTED.value,
                    review_status=KnowledgeReviewStatus.PENDING_REVIEW.value,
                    confidence_metadata_json={"confidence": 0.85},
                )
                session.add(ki_risk)

                # 5. Soft-deleted item (should NOT be included in metrics)
                ki_deleted = KnowledgeItem(
                    organisation_id=org_id,
                    project_id=proj_id,
                    category=KnowledgeCategory.WORK_PROGRESS.value,
                    support_classification="direct",
                    title="Obsolete Task",
                    structured_summary="This was deleted.",
                    structured_payload={},
                    extraction_model="qwen3:8b",
                    prompt_version="p2.6-v1",
                    fingerprint=uuid.uuid4().hex,
                    epistemic_status=EpistemicStatus.EXTRACTED.value,
                    review_status=KnowledgeReviewStatus.PENDING_REVIEW.value,
                    confidence_metadata_json={"confidence": 0.5},
                    is_deleted=True,
                )
                session.add(ki_deleted)

                # Entities & component ownership
                comp_entity = KnowledgeEntity(
                    organisation_id=org_id,
                    project_id=proj_id,
                    entity_type="component",
                    canonical_name="API Gateway",
                    normalized_name="api gateway",
                    confidence_score=0.95,
                )
                user_entity = KnowledgeEntity(
                    organisation_id=org_id,
                    project_id=proj_id,
                    entity_type="person",
                    canonical_name="Pop Owner",
                    normalized_name="pop owner",
                    confidence_score=0.99,
                )
                decision_entity = KnowledgeEntity(
                    organisation_id=org_id,
                    project_id=proj_id,
                    entity_type="decision",
                    canonical_name="PostgreSQL Adoption",
                    normalized_name="postgresql adoption",
                    confidence_score=0.95,
                )
                session.add_all([comp_entity, user_entity, decision_entity])
                session.flush()

                rel_ownership = KnowledgeRelationship(
                    organisation_id=org_id,
                    project_id=proj_id,
                    source_entity_id=user_entity.id,
                    target_entity_id=comp_entity.id,
                    relationship_type="owned_by",
                    relationship_basis=RelationshipBasis.EXPLICIT.value,
                    verification_status=RelationshipVerificationStatus.VERIFIED.value,
                    confidence_score=0.95,
                    fingerprint=uuid.uuid4().hex,
                )
                session.add(rel_ownership)

                # Decision traceability chain (tests c.work_item_ids_json fix)
                chain = DecisionTraceabilityChain(
                    organisation_id=org_id,
                    project_id=proj_id,
                    decision_entity_id=decision_entity.id,
                    completeness_status=TraceabilityCompletenessStatus.COMPLETE.value,
                    work_item_ids_json=["ISSUE-101"],
                    pull_request_ids_json=["PR-50"],
                    commit_ids_json=["c0ffee1"],
                    component_ids_json=[str(comp_entity.id)],
                )
                session.add(chain)

                # Verification cases
                vc1 = VerificationCase(
                    organisation_id=org_id,
                    project_id=proj_id,
                    target_type="knowledge_item",
                    target_id=ki_arch.id,
                    case_status=VerificationCaseStatus.VERIFIED.value,
                    domain="technical_architecture",
                    title="Microservice Architecture Overview",
                )
                vc2 = VerificationCase(
                    organisation_id=org_id,
                    project_id=proj_id,
                    target_type="knowledge_item",
                    target_id=ki_runbook.id,
                    case_status=VerificationCaseStatus.CANDIDATE.value,
                    domain="operational_historical",
                    title="Deployment Runbook",
                )
                session.add_all([vc1, vc2])
                session.commit()

                # Run assessment
                engine = KnowledgeQualityEngine(session)
                res = engine.assess_project_quality(project_id=proj_id, user_id=owner.user_id)

                # Assertions
                assert res["total_items"] == 4  # 4 active items (excluding deleted)
                scores = res["dimension_scores"]

                # Evidence coverage: 2 of 4 items have links
                assert scores["evidence_coverage"] == 50.0

                # Verification coverage: 1 of 2 cases verified
                assert scores["verification_coverage"] == 50.0

                # Ownership coverage: API Gateway has owner
                assert scores["ownership_coverage"] == 100.0

                # Decision traceability: 1 complete chain for 1 decision
                assert scores["decision_traceability"] == 100.0

                # Risk coverage: 1 risk item is mitigated
                assert scores["risk_coverage"] == 100.0

                # Freshness: 0 stale items among 4
                assert scores["knowledge_freshness"] == 100.0

                assert res["overall_quality_score"] > 0.0


def test_quality_api_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test HTTP API endpoint returns quality payload and supports sync_findings query param."""
    with isolated_auth_app(monkeypatch) as ctx:
        with TestClient(ctx.app) as client:
            owner = register_and_login_user(client, email="owner_api@example.com", full_name="API Owner")
            _, proj_id_str = _create_org_and_project(client, owner.headers, "api-kq")

            # Standard fetch
            resp = client.get(
                f"/api/v1/projects/{proj_id_str}/knowledge-intelligence/quality",
                headers=owner.headers,
            )
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert data["project_id"] == proj_id_str
            assert data["overall_quality_score"] == 0.0
            assert "dimension_scores" in data

            # Refresh fetch with sync_findings
            resp_sync = client.get(
                f"/api/v1/projects/{proj_id_str}/knowledge-intelligence/quality?sync_findings=true",
                headers=owner.headers,
            )
            assert resp_sync.status_code == 200, resp_sync.text
            assert resp_sync.json()["project_id"] == proj_id_str
