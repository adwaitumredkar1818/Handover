"""Regression tests for three-graph domain classification, validation, and live Technology Stack enrichment."""

from __future__ import annotations

import uuid

from types import SimpleNamespace
from fastapi.testclient import TestClient
from app.core.security import utc_now
from app.models.enums import (
    EntityType,
    EpistemicStatus,
    EvidenceCategory,
    EvidenceProcessingStatus,
    EvidenceSourceType,
    KnowledgeCategory,
    KnowledgeReviewStatus,
    RelationshipType,
)
from app.models.evidence import EvidenceChunk, EvidenceContent, EvidenceItem
from app.models.integration import SourceAccessPolicy, SourceConnection
from app.models.knowledge import KnowledgeExtractionRun, KnowledgeItem
from app.models.organisation import Organisation, OrganisationMembership
from app.models.project import Project, ProjectMembership
from app.models.rbac import Role
from app.models.relationship import KnowledgeEntity
from app.repositories.knowledge import KnowledgeRepository
from app.services.extraction_prompts import build_multi_domain_extraction_prompt
from app.services.knowledge_graphs import KnowledgeGraphProjectionService, get_project_graph_stamp
from app.services.knowledge_validator import (
    ChunkPromptInput,
    KnowledgeCandidateValidator,
    get_multi_domain_response_json_schema,
)
from app.services.pipeline_coordinator import PipelineCoordinatorService
from app.services.rbac import ProjectContext
from app.services.relationship_coordinator import RelationshipCoordinatorService
from tests.conftest import isolated_auth_app, register_and_login_user


def _chunk_for(
    *,
    evidence_id: uuid.UUID,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    text: str,
    title: str = "doc.md",
    chunk_id: uuid.UUID | None = None,
) -> ChunkPromptInput:
    return ChunkPromptInput(
        chunk_id=chunk_id or uuid.uuid4(),
        evidence_id=evidence_id,
        organisation_id=org_id,
        project_id=project_id,
        chunk_index=0,
        chunk_type="markdown",
        page_number=None,
        section_title=None,
        char_start=0,
        char_end=len(text),
        chunk_text=text,
        source_type="document_upload",
        source_provider="upload",
        source_external_id=title,
        source_url=None,
        title=title,
        source_author_identity="tester",
        source_created_at_iso=None,
        source_updated_at_iso=None,
        extracted_at_iso=None,
        evidence_content_hash="hash-ev",
        chunk_content_hash="hash-ch",
    )


def _setup_project(session, owner_id: uuid.UUID):
    owner_role = session.query(Role).filter_by(name="project_manager").first() or session.query(Role).first()
    org_role = session.query(Role).filter_by(name="org_owner").first() or owner_role
    org = Organisation(
        id=uuid.uuid4(),
        name="Test Org",
        slug=f"org-{uuid.uuid4().hex[:8]}",
        created_by_id=owner_id,
    )
    session.add(org)
    session.flush()
    session.add(
        OrganisationMembership(
            organisation_id=org.id,
            user_id=owner_id,
            role_id=org_role.id,
            status="active",
        )
    )
    project = Project(
        id=uuid.uuid4(),
        organisation_id=org.id,
        name="Graph Test Project",
        slug=f"proj-{uuid.uuid4().hex[:6]}",
        created_by_id=owner_id,
        owner_id=owner_id,
        visibility="organisation",
    )
    session.add(project)
    session.flush()
    session.add(
        ProjectMembership(
            id=uuid.uuid4(),
            project_id=project.id,
            user_id=owner_id,
            role_id=owner_role.id,
            status="active",
        )
    )
    session.commit()
    return org, project


def _add_evidence(session, *, org_id: uuid.UUID, project_id: uuid.UUID, user_id: uuid.UUID, title: str, text: str, source_connection_id: uuid.UUID | None = None) -> EvidenceItem:
    ev = EvidenceItem(
        id=uuid.uuid4(),
        organisation_id=org_id,
        project_id=project_id,
        source_type=EvidenceSourceType.DOCUMENT_UPLOAD.value,
        category=EvidenceCategory.DESIGN_DOCUMENT.value,
        processing_status=EvidenceProcessingStatus.EXTRACTED.value,
        title=title,
        original_filename=title,
        source_connection_id=source_connection_id,
        source_external_id=f"ext-{uuid.uuid4().hex[:8]}",
        content_hash=f"{uuid.uuid4().hex}{uuid.uuid4().hex}",
    )
    session.add(ev)
    session.flush()
    session.add(
        EvidenceContent(
            evidence_id=ev.id,
            extracted_text=text,
        )
    )
    ch = EvidenceChunk(
        id=uuid.uuid4(),
        organisation_id=org_id,
        project_id=project_id,
        evidence_id=ev.id,
        chunk_index=0,
        chunk_text=text,
        char_count=len(text),
        token_estimate=max(1, len(text) // 4),
        char_start=0,
        char_end=len(text),
        chunk_content_hash=ev.content_hash,
        source_type=ev.source_type,
    )
    session.add(ch)
    session.commit()
    ev._test_chunk_id = ch.id  # type: ignore[attr-defined]
    return ev


def test_prompt_and_schema_expose_all_three_graph_domains() -> None:
    schema = get_multi_domain_response_json_schema()
    item_props = schema["properties"]["items"]["items"]["properties"]
    assert "graph_classifications" in item_props
    assert "technology_details" in item_props
    assert "architecture_details" in item_props
    assert "feature_details" in item_props

    ch = _chunk_for(
        evidence_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        text="The React frontend calls the FastAPI backend to export reports.",
    )
    built = build_multi_domain_extraction_prompt(chunks=[ch])
    assert "TECHNOLOGY_STACK" in built.system_prompt
    assert "SYSTEM_ARCHITECTURE" in built.system_prompt
    assert "FEATURES_WORKFLOWS" in built.system_prompt


def test_a_technology_manifest_classification_and_no_fake_features(monkeypatch) -> None:
    with isolated_auth_app(monkeypatch) as app_ctx, TestClient(app_ctx.app) as client:
        session_factory = app_ctx.session_factory
        user_info = register_and_login_user(client, email="testa@example.com", full_name="Test User A")
        user_id = user_info.user_id
        with session_factory() as session:
            org, project = _setup_project(session, user_id)
            ev = _add_evidence(
                session,
                org_id=org.id,
                project_id=project.id,
                user_id=user_id,
                title="stack.md",
                text="Declared dependencies: React 19.0.0, TypeScript 5.4, FastAPI 0.115, and PostgreSQL 16.",
            )
            ch = _chunk_for(
                evidence_id=ev.id,
                org_id=org.id,
                project_id=project.id,
                text="Declared dependencies: React 19.0.0, TypeScript 5.4, FastAPI 0.115, and PostgreSQL 16.",
                title="stack.md",
                chunk_id=ev._test_chunk_id,
            )
            validator = KnowledgeCandidateValidator()
            report = validator.validate_multi_domain_response(
                parsed_json={
                    "items": [
                        {
                            "category": "dependencies",
                            "title": "React 19 Frontend Library",
                            "structured_summary": "React 19.0.0 is a declared frontend dependency.",
                            "confidence_level": "high",
                            "graph_classifications": ["TECHNOLOGY_STACK"],
                            "technology_details": {
                                "technology_name": "React",
                                "technology_category": "frontend",
                                "version": "19.0.0",
                                "usage_status": "DECLARED_DEPENDENCY",
                            },
                            "evidence_refs": [
                                {"chunk_id": str(ch.chunk_id), "supporting_excerpt": "Declared dependencies: React 19.0.0, TypeScript 5.4, FastAPI 0.115, and PostgreSQL 16.", "support_type": "direct"}
                            ],
                        },
                        {
                            "category": "dependencies",
                            "title": "FastAPI Backend Framework",
                            "structured_summary": "FastAPI 0.115 is a declared backend dependency.",
                            "confidence_level": "high",
                            "graph_classifications": ["TECHNOLOGY_STACK"],
                            "technology_details": {
                                "technology_name": "FastAPI",
                                "technology_category": "backend",
                                "version": "0.115",
                                "usage_status": "DECLARED_DEPENDENCY",
                            },
                            "evidence_refs": [
                                {"chunk_id": str(ch.chunk_id), "supporting_excerpt": "Declared dependencies: React 19.0.0, TypeScript 5.4, FastAPI 0.115, and PostgreSQL 16.", "support_type": "direct"}
                            ],
                        },
                    ]
                },
                supplied_chunks=[ch],
                is_synthetic=True,
            )
            assert len(report.accepted_items) == 2
            for draft in report.accepted_items:
                assert draft.review_status == KnowledgeReviewStatus.PENDING_REVIEW.value

            k_repo = KnowledgeRepository(session)
            for draft in report.accepted_items:
                k_repo.upsert_validated_draft(
                    organisation_id=org.id,
                    project_id=project.id,
                    extraction_run_id=None,
                    model_name="qwen3:8b",
                    prompt_version="v1",
                    draft=draft,
                )
            session.commit()

            RelationshipCoordinatorService(session).run_reconstruction(
                organisation_id=org.id,
                project_id=project.id,
                include_llm_suggestions=False,
            )
            session.commit()

            ctx = SimpleNamespace(project=project, organisation=org, principal=SimpleNamespace(user_id=user_id), permissions=frozenset({"knowledge.read"}), has_permission=lambda p: p in {"knowledge.read"})
            proj_svc = KnowledgeGraphProjectionService(session)
            tech_graph = proj_svc.get_graph(project_ctx=ctx, graph_type="technology-stack")
            feat_graph = proj_svc.get_graph(project_ctx=ctx, graph_type="features-workflows")

            tech_labels = {n.label for n in tech_graph.nodes}
            assert "React" in tech_labels
            assert "FastAPI" in tech_labels
            assert not any(n.entity_type == EntityType.FEATURE.value for n in feat_graph.nodes)


def test_b_and_c_architecture_and_feature_separation_and_exclusion(monkeypatch) -> None:
    with isolated_auth_app(monkeypatch) as app_ctx, TestClient(app_ctx.app) as client:
        session_factory = app_ctx.session_factory
        user_info = register_and_login_user(client, email="testbc@example.com", full_name="Test User BC")
        user_id = user_info.user_id
        with session_factory() as session:
            org, project = _setup_project(session, user_id)
            text = (
                "The React Web App communicates with the Backend REST API, which reads from the Primary Database.\n"
                "Users can upload a document, view analysis results, and export a report.\n"
                "Database migrations are managed internally via Alembic."
            )
            ev = _add_evidence(session, org_id=org.id, project_id=project.id, user_id=user_id, title="arch.md", text=text)
            ch = _chunk_for(evidence_id=ev.id, org_id=org.id, project_id=project.id, text=text, title="arch.md", chunk_id=ev._test_chunk_id)
            validator = KnowledgeCandidateValidator()
            report = validator.validate_multi_domain_response(
                parsed_json={
                    "items": [
                        {
                            "category": "technical_architecture",
                            "title": "React Web App to Backend REST API",
                            "structured_summary": "React Web App calls Backend REST API.",
                            "confidence_level": "high",
                            "graph_classifications": ["SYSTEM_ARCHITECTURE"],
                            "architecture_details": {
                                "component_name": "Backend REST API",
                                "component_type": "api",
                                "component_responsibility": "Serves project endpoints",
                                "implementation_status": "implemented",
                                "associated_technologies": [],
                                "relationship_type": "calls",
                                "source_component": "React Web App",
                                "target_component": "Backend REST API",
                            },
                            "evidence_refs": [
                                {"chunk_id": str(ch.chunk_id), "supporting_excerpt": "The React Web App communicates with the Backend REST API, which reads from the Primary Database.", "support_type": "direct"}
                            ],
                        },
                        {
                            "category": "work_items",
                            "title": "Document Upload and Report Export",
                            "structured_summary": "Users upload a document, view analysis results, and export a report.",
                            "confidence_level": "high",
                            "graph_classifications": ["FEATURES_WORKFLOWS"],
                            "feature_details": {
                                "feature_name": "Document Upload & Report Export",
                                "user_goal": "Analyze documents and export reports",
                                "user_actor": "User",
                                "user_visible_behavior": "Upload document, view analysis, export report",
                                "implementation_status": "implemented",
                                "workflow_steps": ["Upload document", "View analysis results", "Export report"],
                                "related_components": ["Backend REST API"],
                            },
                            "evidence_refs": [
                                {"chunk_id": str(ch.chunk_id), "supporting_excerpt": "Users can upload a document, view analysis results, and export a report.", "support_type": "direct"}
                            ],
                        },
                        # Internal dev/infra task mislabeled as FEATURES_WORKFLOWS -> must be stripped!
                        {
                            "category": "operational_historical",
                            "title": "Database Migrations",
                            "structured_summary": "Database migrations are managed internally via Alembic.",
                            "confidence_level": "high",
                            "graph_classifications": ["FEATURES_WORKFLOWS"],
                            "feature_details": {
                                "feature_name": "Database migrations",
                                "user_goal": "Run migrations",
                            },
                            "evidence_refs": [
                                {"chunk_id": str(ch.chunk_id), "supporting_excerpt": "Database migrations are managed internally via Alembic.", "support_type": "direct"}
                            ],
                        },
                    ]
                },
                supplied_chunks=[ch],
                is_synthetic=True,
            )
            # Verify Database Migrations had FEATURES_WORKFLOWS stripped
            db_mig = next(i for i in report.accepted_items if i.title == "Database Migrations")
            assert "feature_details" not in db_mig.structured_payload
            assert "FEATURES_WORKFLOWS" not in (db_mig.structured_payload.get("graph_classifications") or [])

            k_repo = KnowledgeRepository(session)
            for draft in report.accepted_items:
                k_repo.upsert_validated_draft(
                    organisation_id=org.id,
                    project_id=project.id,
                    extraction_run_id=None,
                    model_name="qwen3:8b",
                    prompt_version="v1",
                    draft=draft,
                )
            session.commit()

            RelationshipCoordinatorService(session).run_reconstruction(
                organisation_id=org.id,
                project_id=project.id,
                include_llm_suggestions=False,
            )
            session.commit()

            ctx = SimpleNamespace(project=project, organisation=org, principal=SimpleNamespace(user_id=user_id), permissions=frozenset({"knowledge.read"}), has_permission=lambda p: p in {"knowledge.read"})
            proj_svc = KnowledgeGraphProjectionService(session)
            arch_graph = proj_svc.get_graph(project_ctx=ctx, graph_type="system-architecture")
            feat_graph = proj_svc.get_graph(project_ctx=ctx, graph_type="features-workflows")

            arch_labels = {n.label for n in arch_graph.nodes}
            assert "React Web App" in arch_labels
            assert "Backend REST API" in arch_labels
            assert any(e.relationship_type == RelationshipType.CALLS.value for e in arch_graph.edges)

            feat_labels = {n.label for n in feat_graph.nodes}
            assert "Document Upload & Report Export" in feat_labels
            assert "Database migrations" not in feat_labels


def test_d_e_f_g_mixed_enrichment_revision_no_tech_and_acl(monkeypatch) -> None:
    with isolated_auth_app(monkeypatch) as app_ctx, TestClient(app_ctx.app) as client:
        session_factory = app_ctx.session_factory
        user_info = register_and_login_user(client, email="testdefg@example.com", full_name="Test User DEFG")
        user_id = user_info.user_id
        with session_factory() as session:
            org, project = _setup_project(session, user_id)

            # Test D: Mixed document -> all 3 graphs populated cleanly without duplicates
            mixed_text = (
                "The Next.js Portal communicates with the FastAPI Gateway.\n"
                "Users can submit project handovers for review."
            )
            ev1 = _add_evidence(session, org_id=org.id, project_id=project.id, user_id=user_id, title="mixed.md", text=mixed_text)
            ch1 = _chunk_for(evidence_id=ev1.id, org_id=org.id, project_id=project.id, text=mixed_text, title="mixed.md", chunk_id=ev1._test_chunk_id)
            validator = KnowledgeCandidateValidator()
            rep1 = validator.validate_multi_domain_response(
                parsed_json={
                    "items": [
                        {
                            "category": "technical_architecture",
                            "title": "Next.js Framework",
                            "structured_summary": "Uses Next.js for the web portal.",
                            "confidence_level": "high",
                            "graph_classifications": ["TECHNOLOGY_STACK"],
                            "technology_details": {
                                "technology_name": "Next.js",
                                "technology_category": "frontend",
                                "usage_status": "DIRECTLY_EVIDENCED_USE",
                                "associated_component": "Next.js Portal",
                            },
                            "evidence_refs": [{"chunk_id": str(ch1.chunk_id), "supporting_excerpt": "The Next.js Portal communicates with the FastAPI Gateway.", "support_type": "direct"}],
                        },
                        {
                            "category": "technical_architecture",
                            "title": "Portal to FastAPI Gateway",
                            "structured_summary": "Next.js Portal calls FastAPI Gateway.",
                            "confidence_level": "high",
                            "graph_classifications": ["SYSTEM_ARCHITECTURE"],
                            "architecture_details": {
                                "component_name": "FastAPI Gateway",
                                "component_type": "api",
                                "relationship_type": "calls",
                                "source_component": "Next.js Portal",
                                "target_component": "FastAPI Gateway",
                            },
                            "evidence_refs": [{"chunk_id": str(ch1.chunk_id), "supporting_excerpt": "The Next.js Portal communicates with the FastAPI Gateway.", "support_type": "direct"}],
                        },
                        {
                            "category": "work_items",
                            "title": "Submit Project Handovers",
                            "structured_summary": "Users submit project handovers for review.",
                            "confidence_level": "high",
                            "graph_classifications": ["FEATURES_WORKFLOWS"],
                            "feature_details": {
                                "feature_name": "Submit Project Handovers",
                                "user_goal": "Share handover package",
                                "user_actor": "User",
                            },
                            "evidence_refs": [{"chunk_id": str(ch1.chunk_id), "supporting_excerpt": "Users can submit project handovers for review.", "support_type": "direct"}],
                        },
                    ]
                },
                supplied_chunks=[ch1],
                is_synthetic=True,
            )
            k_repo = KnowledgeRepository(session)
            for d in rep1.accepted_items:
                k_repo.upsert_validated_draft(
                    organisation_id=org.id,
                    project_id=project.id,
                    extraction_run_id=None,
                    model_name="qwen3:8b",
                    prompt_version="v1",
                    draft=d,
                )
            session.commit()
            RelationshipCoordinatorService(session).run_reconstruction(organisation_id=org.id, project_id=project.id, include_llm_suggestions=False)
            session.commit()

            ctx = SimpleNamespace(project=project, organisation=org, principal=SimpleNamespace(user_id=user_id), permissions=frozenset({"knowledge.read"}), has_permission=lambda p: p in {"knowledge.read"})
            proj_svc = KnowledgeGraphProjectionService(session)
            tech_before = proj_svc.get_graph(project_ctx=ctx, graph_type="technology-stack")
            stamp_before = get_project_graph_stamp(session, project.id)
            rev_before = PipelineCoordinatorService(session).get_status(project.id).graph_version
            nextjs_nodes_before = [n for n in tech_before.nodes if n.label == "Next.js"]
            assert len(nextjs_nodes_before) == 1

            # Test E: Existing technology enriched with version -> no duplicate node, stamp & graph_version advance!
            ver_text = "Next.js 15.1.0 powers the SSR frontend."
            ev2 = _add_evidence(session, org_id=org.id, project_id=project.id, user_id=user_id, title="version.md", text=ver_text)
            ch2 = _chunk_for(evidence_id=ev2.id, org_id=org.id, project_id=project.id, text=ver_text, title="version.md", chunk_id=ev2._test_chunk_id)
            rep2 = validator.validate_multi_domain_response(
                parsed_json={
                    "items": [
                        {
                            "category": "technical_architecture",
                            "title": "Next.js 15.1.0 Runtime",
                            "structured_summary": "Next.js 15.1.0 powers SSR.",
                            "confidence_level": "high",
                            "graph_classifications": ["TECHNOLOGY_STACK"],
                            "technology_details": {
                                "technology_name": "Next.js",
                                "technology_category": "frontend",
                                "version": "15.1.0",
                                "role_in_project": "SSR frontend",
                                "usage_status": "DIRECTLY_EVIDENCED_USE",
                            },
                            "evidence_refs": [{"chunk_id": str(ch2.chunk_id), "supporting_excerpt": "Next.js 15.1.0 powers the SSR frontend.", "support_type": "direct"}],
                        }
                    ]
                },
                supplied_chunks=[ch2],
                is_synthetic=True,
            )
            for d in rep2.accepted_items:
                k_repo.upsert_validated_draft(
                    organisation_id=org.id,
                    project_id=project.id,
                    extraction_run_id=None,
                    model_name="qwen3:8b",
                    prompt_version="v1",
                    draft=d,
                )
            session.commit()
            RelationshipCoordinatorService(session).run_reconstruction(organisation_id=org.id, project_id=project.id, include_llm_suggestions=False)
            session.commit()

            tech_after = proj_svc.get_graph(project_ctx=ctx, graph_type="technology-stack")
            stamp_after = get_project_graph_stamp(session, project.id)
            rev_after = PipelineCoordinatorService(session).get_status(project.id).graph_version

            nextjs_nodes_after = [n for n in tech_after.nodes if n.label == "Next.js"]
            assert len(nextjs_nodes_after) == 1
            assert nextjs_nodes_after[0].metadata.get("version") == "15.1.0"
            assert stamp_after != stamp_before
            assert rev_after != rev_before

            # Test F: Batch with only user-facing feature info -> Technology Stack does NOT gain invented nodes
            tech_count_before_f = len([n for n in tech_after.nodes if n.entity_type == EntityType.TECHNOLOGY.value])
            feat_only_text = "Users can filter search results by date."
            ev3 = _add_evidence(session, org_id=org.id, project_id=project.id, user_id=user_id, title="feat.md", text=feat_only_text)
            ch3 = _chunk_for(evidence_id=ev3.id, org_id=org.id, project_id=project.id, text=feat_only_text, title="feat.md", chunk_id=ev3._test_chunk_id)
            rep3 = validator.validate_multi_domain_response(
                parsed_json={
                    "items": [
                        {
                            "category": "work_items",
                            "title": "Filter Search By Date",
                            "structured_summary": "Users can filter search results by date.",
                            "confidence_level": "high",
                            "graph_classifications": ["FEATURES_WORKFLOWS"],
                            "feature_details": {"feature_name": "Filter Search By Date"},
                            "evidence_refs": [{"chunk_id": str(ch3.chunk_id), "supporting_excerpt": "Users can filter search results by date.", "support_type": "direct"}],
                        }
                    ]
                },
                supplied_chunks=[ch3],
                is_synthetic=True,
            )
            for d in rep3.accepted_items:
                k_repo.upsert_validated_draft(
                    organisation_id=org.id,
                    project_id=project.id,
                    extraction_run_id=None,
                    model_name="qwen3:8b",
                    prompt_version="v1",
                    draft=d,
                )
            session.commit()
            RelationshipCoordinatorService(session).run_reconstruction(organisation_id=org.id, project_id=project.id, include_llm_suggestions=False)
            session.commit()
            tech_after_f = proj_svc.get_graph(project_ctx=ctx, graph_type="technology-stack")
            tech_count_after_f = len([n for n in tech_after_f.nodes if n.entity_type == EntityType.TECHNOLOGY.value])
            assert tech_count_after_f == tech_count_before_f

            # Test G: Source ACL fail-closed check on restricted source connection
            sc = SourceConnection(
                id=uuid.uuid4(),
                organisation_id=org.id,
                provider="github",
                display_name="Private Org Repo",
                created_by_user_id=user_id,
                status="active",
            )
            session.add(sc)
            session.flush()
            ev_priv = _add_evidence(
                session,
                org_id=org.id,
                project_id=project.id,
                user_id=user_id,
                title="priv.md",
                text="Private service uses Redis 7.2.",
                source_connection_id=sc.id,
            )
            ev_priv.acl_scope = "source_restricted"
            session.commit()
            ch_priv = _chunk_for(evidence_id=ev_priv.id, org_id=org.id, project_id=project.id, text="Private service uses Redis 7.2.", title="priv.md", chunk_id=ev_priv._test_chunk_id)
            rep_priv = validator.validate_multi_domain_response(
                parsed_json={
                    "items": [
                        {
                            "category": "technical_architecture",
                            "title": "Redis 7.2 Cache",
                            "structured_summary": "Private service uses Redis 7.2.",
                            "confidence_level": "high",
                            "graph_classifications": ["TECHNOLOGY_STACK"],
                            "technology_details": {
                                "technology_name": "Redis",
                                "technology_category": "database",
                                "version": "7.2",
                                "usage_status": "DIRECTLY_EVIDENCED_USE",
                            },
                            "evidence_refs": [{"chunk_id": str(ch_priv.chunk_id), "supporting_excerpt": "Private service uses Redis 7.2.", "support_type": "direct"}],
                        }
                    ]
                },
                supplied_chunks=[ch_priv],
                is_synthetic=True,
            )
            for d in rep_priv.accepted_items:
                k_repo.upsert_validated_draft(
                    organisation_id=org.id,
                    project_id=project.id,
                    extraction_run_id=None,
                    model_name="qwen3:8b",
                    prompt_version="v1",
                    draft=d,
                )
            session.commit()
            RelationshipCoordinatorService(session).run_reconstruction(organisation_id=org.id, project_id=project.id, include_llm_suggestions=False)
            session.commit()

            other_user_id = uuid.uuid4()
            other_ctx = SimpleNamespace(project=project, organisation=org, principal=SimpleNamespace(user_id=other_user_id), permissions=frozenset({"knowledge.read"}), has_permission=lambda p: p in {"knowledge.read"})
            other_tech_graph = proj_svc.get_graph(project_ctx=other_ctx, graph_type="technology-stack")
            assert "Redis" not in {n.label for n in other_tech_graph.nodes}
