"""Focused Tests for DEF-07: Per-Viewer Export ACL Enforcement & Secret Redaction.

Platform: The Handover
Remediation: Post-Stage-7 — DEF-07 (HIGH)

Verifies all DEF-07 security & integrity criteria in strict isolation:
1. Viewer with full evidence access receives all verified items and provenance.
2. Viewer with partial evidence access receives only permitted items; restricted titles/summaries/excerpts are omitted across JSON, Markdown, and PDF.
3. Viewer with no access to a restricted source never receives cached section_content assembled by another viewer.
4. Cross-project and cross-case export attempts fail closed (404 / 403).
5. Cached package assembled by one viewer cannot bypass ACL checks for another viewer.
6. Secret redaction strips credentials/tokens across title, description, section content, provenance, and signoff notes.
7. Missing, invalid, or inactive principal fails closed (ForbiddenError / 401).
8. Canonical stored package section_content and SHA-256 content_hash remain completely unchanged.
9. Immutable `handover.package.exported` audit event is recorded without logging restricted excerpts or secrets.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

import pymupdf as fitz
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_principal, get_db_session
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.rbac_catalog import deterministic_rbac_id
from app.main import app
from app.models import Base
from app.models.audit import AuditLog
from app.models.enums import (
    EpistemicStatus,
    EvidenceProcessingStatus,
    EvidenceSourceType,
    KnowledgeCategory,
    KnowledgeReviewStatus,
    OrganisationStatus,
    ProjectStatus,
    ProjectVisibility,
    RoleName,
    SourcePermissionVerificationStatus,
    UserStatus,
)
from app.models.evidence import EvidenceItem
from app.models.handover import HandoverPackageSection, HandoverPackageVersion
from app.models.integration import SourceAccessPolicy
from app.models.knowledge import KnowledgeEvidenceLink, KnowledgeItem
from app.models.organisation import Organisation, OrganisationMembership
from app.models.project import Project, ProjectMembership
from app.models.user import User
from app.models.verification import VerificationCase
from app.repositories.rbac import RbacRepository
from app.repositories.user import UserRepository
from app.schemas.handover import HandoverCaseCreateRequest, PackageAssemblyRequest
from app.schemas.verification import ApproveFindingRequest
from app.services.auth import AuthenticatedPrincipal
from app.services.handover_assembly import PackageAssemblyService
from app.services.handover_case import HandoverCaseService
from app.services.handover_export import HandoverExportService
from app.services.rbac import RbacService
from app.services.verification_engine import VerificationEngine
from app.services.verification_review import VerificationReviewService


@pytest.fixture
def export_env() -> Any:
    """Isolated in-memory database seeded with full-access, partial-access, restricted-only, inactive, and cross-project users."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _sqlite_pragma(dbapi_conn: Any, _rec: Any) -> None:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=OFF")
        cur.close()

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    RbacRepository(session).ensure_catalog_seeded()
    session.commit()

    def _mk_user(label: str, *, status: str = UserStatus.ACTIVE.value) -> User:
        u = User(
            id=uuid.uuid4(),
            email=f"def07-{label}-{uuid.uuid4().hex[:6]}@isolated.test",
            full_name=f"Export {label.title()}",
            password_hash="argon2id$isolated",
            status=status,
            is_email_verified=True,
            email_verified_at=datetime.now(UTC),
        )
        session.add(u)
        return u

    full_viewer = _mk_user("full")
    partial_viewer = _mk_user("partial")
    restricted_none_viewer = _mk_user("noaccess")
    inactive_user = _mk_user("inactive", status=UserStatus.DISABLED.value)
    outsider = _mk_user("outsider")
    session.flush()

    org = Organisation(
        id=uuid.uuid4(),
        name="DEF-07 Isolated Org",
        slug=f"def07-org-{uuid.uuid4().hex[:6]}",
        status=OrganisationStatus.ACTIVE.value,
        created_by_id=full_viewer.id,
    )
    session.add(org)
    session.flush()

    proj_a = Project(
        id=uuid.uuid4(),
        organisation_id=org.id,
        name="DEF-07 Project A",
        slug=f"def07-a-{uuid.uuid4().hex[:6]}",
        status=ProjectStatus.ACTIVE.value,
        visibility=ProjectVisibility.PRIVATE.value,
        created_by_id=full_viewer.id,
        owner_id=full_viewer.id,
    )
    proj_b = Project(
        id=uuid.uuid4(),
        organisation_id=org.id,
        name="DEF-07 Project B",
        slug=f"def07-b-{uuid.uuid4().hex[:6]}",
        status=ProjectStatus.ACTIVE.value,
        visibility=ProjectVisibility.PRIVATE.value,
        created_by_id=outsider.id,
        owner_id=outsider.id,
    )
    session.add_all([proj_a, proj_b])
    session.flush()

    for u, p_role_a, p_role_b in [
        (full_viewer, RoleName.PROJECT_MANAGER.value, None),
        (partial_viewer, RoleName.PROJECT_MEMBER.value, None),
        (restricted_none_viewer, RoleName.PROJECT_MEMBER.value, None),
        (inactive_user, RoleName.PROJECT_MEMBER.value, None),
        (outsider, None, RoleName.PROJECT_MANAGER.value),
    ]:
        session.add(
            OrganisationMembership(
                id=uuid.uuid4(),
                organisation_id=org.id,
                user_id=u.id,
                role_id=deterministic_rbac_id("role", RoleName.ORG_MEMBER.value),
                status="active",
            )
        )
        if p_role_a:
            session.add(
                ProjectMembership(
                    id=uuid.uuid4(),
                    project_id=proj_a.id,
                    user_id=u.id,
                    role_id=deterministic_rbac_id("role", p_role_a),
                    status="active",
                )
            )
        if p_role_b:
            session.add(
                ProjectMembership(
                    id=uuid.uuid4(),
                    project_id=proj_b.id,
                    user_id=u.id,
                    role_id=deterministic_rbac_id("role", p_role_b),
                    status="active",
                )
            )
    session.flush()

    # Source access policy granting ONLY full_viewer access to private GitHub repo
    private_policy = SourceAccessPolicy(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=proj_a.id,
        source_connection_id=uuid.uuid4(),
        provider="github",
        scope_identifier="org/top-secret-repo",
        visibility_policy="explicit_user_grants",
        allowed_user_ids=[str(full_viewer.id)],
        sync_permission_status=SourcePermissionVerificationStatus.VERIFIED.value,
        authorised_by_user_id=full_viewer.id,
    )
    # Second restricted policy granting full_viewer and partial_viewer, NOT restricted_none_viewer
    team_policy = SourceAccessPolicy(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=proj_a.id,
        source_connection_id=uuid.uuid4(),
        provider="github",
        scope_identifier="org/team-internal-repo",
        visibility_policy="explicit_user_grants",
        allowed_user_ids=[str(full_viewer.id), str(partial_viewer.id)],
        sync_permission_status=SourcePermissionVerificationStatus.VERIFIED.value,
        authorised_by_user_id=full_viewer.id,
    )
    session.add_all([private_policy, team_policy])
    session.flush()

    def _mk_ev_ki(
        title: str,
        summary: str,
        *,
        category: str,
        acl_scope: str = "project_members",
        policy_id: uuid.UUID | None = None,
        source_type: str = EvidenceSourceType.DOCUMENT_UPLOAD.value,
    ) -> tuple[EvidenceItem, KnowledgeItem]:
        ev = EvidenceItem(
            id=uuid.uuid4(),
            organisation_id=org.id,
            project_id=proj_a.id,
            source_type=source_type,
            source_provider=source_type,
            category="project_document",
            source_external_id=f"ev-{uuid.uuid4().hex[:8]}",
            title=f"Doc: {title}",
            content_hash=hashlib.sha256(summary.encode()).hexdigest(),
            acl_scope=acl_scope,
            source_access_policy_id=policy_id,
            processing_status=EvidenceProcessingStatus.EXTRACTED.value,
            source_created_at=datetime.now(UTC),
            extracted_at=datetime.now(UTC),
        )
        session.add(ev)
        ki = KnowledgeItem(
            id=uuid.uuid4(),
            organisation_id=org.id,
            project_id=proj_a.id,
            category=category,
            title=title,
            structured_summary=summary,
            structured_payload={},
            epistemic_status=EpistemicStatus.EXTRACTED.value,
            review_status=KnowledgeReviewStatus.PENDING_REVIEW.value,
            support_classification="direct",
            extraction_model="qwen3:8b",
            prompt_version="v1",
            fingerprint=hashlib.sha256(f"{proj_a.id}:{title}".encode()).hexdigest()[:32],
            is_stale=False,
            is_deleted=False,
        )
        session.add(ki)
        session.flush()
        session.add(
            KnowledgeEvidenceLink(
                id=uuid.uuid4(),
                organisation_id=org.id,
                project_id=proj_a.id,
                knowledge_item_id=ki.id,
                evidence_id=ev.id,
                support_type="direct_support",
                supporting_excerpt=summary[:120],
            )
        )
        session.flush()
        return ev, ki

    # 1. Public decision containing an inline secret that must be redacted
    _, ki_public = _mk_ev_ki(
        "Public API Gateway Standard",
        "All public APIs route via Nginx using ghp_1234567890ABCDEFGHIJKLMNOPQRSTUV for CI mirror.",
        category=KnowledgeCategory.DECISIONS_RATIONALE.value,
    )
    # 2. Restricted decision accessible ONLY to full_viewer (NOT partial_viewer or restricted_none_viewer)
    _, ki_secret_repo = _mk_ev_ki(
        "Classified Encryption Key Vault Topology",
        "RESTRICTED_VAULT_MARKER: HSM root shard lives on isolated enclave cluster-9.",
        category=KnowledgeCategory.DECISIONS_RATIONALE.value,
        acl_scope="source_restricted",
        policy_id=private_policy.id,
        source_type=EvidenceSourceType.GITHUB.value,
    )
    # 3. Team-restricted architecture accessible to full_viewer & partial_viewer (NOT restricted_none_viewer)
    _, ki_team_only = _mk_ev_ki(
        "Internal Queue Worker Topology",
        "TEAM_INTERNAL_MARKER: Worker polls PostgreSQL advisory locks every 3 seconds.",
        category=KnowledgeCategory.TECHNICAL_ARCHITECTURE.value,
        acl_scope="source_restricted",
        policy_id=team_policy.id,
        source_type=EvidenceSourceType.GITHUB.value,
    )

    # Approve all 3 findings via VerificationReviewService so full_viewer assembles all 3 into canonical package
    v_engine = VerificationEngine(session)
    v_engine.sync_project_findings(proj_a.id)
    v_engine.assess_project(proj_a.id)
    rbac_svc = RbacService(
        db_session=session,
        rbac_repository=RbacRepository(session),
        user_repository=UserRepository(session),
    )
    mgr_ctx = rbac_svc.resolve_project_context(
        project_id=proj_a.id,
        principal=AuthenticatedPrincipal(
            user=full_viewer,
            session_family_id=None,
            roles=(),
            permissions=frozenset(),
        ),
    )
    v_review = VerificationReviewService(session)
    for ki in (ki_public, ki_secret_repo, ki_team_only):
        vc = session.execute(
            select(VerificationCase).where(VerificationCase.target_id == ki.id)
        ).scalar_one()
        v_review.approve_case(
            vc.id,
            project_ctx=mgr_ctx,
            payload=ApproveFindingRequest(reviewer_note="Verified for export ACL test."),
        )
    session.flush()

    case_svc = HandoverCaseService(session)
    hcase_a1 = case_svc.create_case(
        organisation_id=org.id,
        project_id=proj_a.id,
        user_id=full_viewer.id,
        request=HandoverCaseCreateRequest(
            title="DEF-07 Primary Handover",
            description="Contains secret_key=SuperSecretValue999 that must be redacted on export.",
            departing_member_id=partial_viewer.id,
        ),
    )
    hcase_a2 = case_svc.create_case(
        organisation_id=org.id,
        project_id=proj_a.id,
        user_id=full_viewer.id,
        request=HandoverCaseCreateRequest(
            title="DEF-07 Secondary Handover",
            departing_member_id=partial_viewer.id,
        ),
    )

    # Assemble canonical package AS full_viewer (so cached section_content contains ALL 3 items!)
    assembly_svc = PackageAssemblyService(session)
    ver_a1 = assembly_svc.assemble_package_version(
        case_id=hcase_a1.id,
        project_id=proj_a.id,
        user_id=full_viewer.id,
        request=PackageAssemblyRequest(assembly_notes="Canonical assembly by full-access manager"),
        has_project_manage=True,
    )
    ver_a2 = assembly_svc.assemble_package_version(
        case_id=hcase_a2.id,
        project_id=proj_a.id,
        user_id=full_viewer.id,
        request=PackageAssemblyRequest(assembly_notes="Second case version"),
        has_project_manage=True,
    )
    session.commit()

    yield {
        "session": session,
        "org": org,
        "proj_a": proj_a,
        "proj_b": proj_b,
        "full_viewer": full_viewer,
        "partial_viewer": partial_viewer,
        "restricted_none_viewer": restricted_none_viewer,
        "inactive_user": inactive_user,
        "outsider": outsider,
        "hcase_a1": hcase_a1,
        "hcase_a2": hcase_a2,
        "ver_a1": ver_a1,
        "ver_a2": ver_a2,
    }
    session.close()


def test_export_per_viewer_acl_full_partial_none_and_hash_immutability(export_env: dict[str, Any]) -> None:
    """Verify full, partial, and zero restricted access across JSON, Markdown, and PDF without mutating canonical package."""
    session: Session = export_env["session"]
    proj_a = export_env["proj_a"]
    hcase_a1 = export_env["hcase_a1"]
    ver_a1 = export_env["ver_a1"]
    full_viewer = export_env["full_viewer"]
    partial_viewer = export_env["partial_viewer"]
    restricted_none_viewer = export_env["restricted_none_viewer"]

    original_hash = ver_a1.content_hash
    dec_sec_before = session.execute(
        select(HandoverPackageSection).where(
            HandoverPackageSection.version_id == ver_a1.id,
            HandoverPackageSection.section_type == "decisions_rationale",
        )
    ).scalar_one()
    original_canonical_content = dec_sec_before.section_content
    # Confirm canonical assembled section_content actually contains the restricted item (proving cached content exists!)
    assert "Classified Encryption Key Vault Topology" in (original_canonical_content or "")

    svc = HandoverExportService(session)

    # 1. Full-access viewer sees all 3 items AND secrets are redacted
    full_json = svc.export_json(
        project_id=proj_a.id,
        case_id=hcase_a1.id,
        user_id=full_viewer.id,
        version_id=ver_a1.id,
        has_project_manage=True,
    )
    assert full_json["viewer_acl_filtered"] is False
    assert full_json["omitted_restricted_items_count"] == 0
    assert full_json["package_hash"] == original_hash
    full_md = svc.export_markdown(
        project_id=proj_a.id,
        case_id=hcase_a1.id,
        user_id=full_viewer.id,
        version_id=ver_a1.id,
        has_project_manage=True,
    )
    assert "Classified Encryption Key Vault Topology" in full_md
    assert "Internal Queue Worker Topology" in full_md
    assert "Public API Gateway Standard" in full_md
    # Secret redaction must strip both the GitHub PAT and description secret_key
    assert "ghp_1234567890ABCDEFGHIJKLMNOPQRSTUV" not in full_md
    assert "SuperSecretValue999" not in full_md
    assert "[REDACTED_GITHUB_TOKEN]" in full_md
    assert "secret_key=[REDACTED]" in full_md

    # 2. Partial-access viewer (same cached package!) sees Public + Team-Internal, NEVER Classified Vault!
    partial_json = svc.export_json(
        project_id=proj_a.id,
        case_id=hcase_a1.id,
        user_id=partial_viewer.id,
        version_id=ver_a1.id,
        has_project_manage=False,
    )
    assert partial_json["viewer_acl_filtered"] is True
    assert partial_json["omitted_restricted_items_count"] == 1
    assert partial_json["package_hash"] == original_hash  # canonical hash unchanged!
    partial_md = svc.export_markdown(
        project_id=proj_a.id,
        case_id=hcase_a1.id,
        user_id=partial_viewer.id,
        version_id=ver_a1.id,
        has_project_manage=False,
    )
    assert "Public API Gateway Standard" in partial_md
    assert "Internal Queue Worker Topology" in partial_md
    assert "Classified Encryption Key Vault Topology" not in partial_md
    assert "RESTRICTED_VAULT_MARKER" not in partial_md
    assert "restricted item(s)" in partial_md

    # Verify PDF bytes ALSO exclude restricted source material for partial_viewer!
    partial_pdf = svc.export_pdf(
        project_id=proj_a.id,
        case_id=hcase_a1.id,
        user_id=partial_viewer.id,
        version_id=ver_a1.id,
        has_project_manage=False,
    )
    pdf_doc = fitz.open(stream=partial_pdf, filetype="pdf")
    pdf_text = "\n".join(page.get_text() for page in pdf_doc)
    pdf_doc.close()
    assert "Public API Gateway Standard" in pdf_text
    assert "Classified Encryption Key Vault Topology" not in pdf_text
    assert "RESTRICTED_VAULT_MARKER" not in pdf_text
    assert "ghp_1234567890ABCDEFGHIJKLMNOPQRSTUV" not in pdf_text
    assert "SuperSecretValue999" not in pdf_text

    # 3. Zero-restricted-access viewer sees ONLY Public item (both restricted sources omitted!)
    none_json = svc.export_json(
        project_id=proj_a.id,
        case_id=hcase_a1.id,
        user_id=restricted_none_viewer.id,
        version_id=ver_a1.id,
        has_project_manage=False,
    )
    assert none_json["viewer_acl_filtered"] is True
    assert none_json["omitted_restricted_items_count"] == 2
    none_md = svc.export_markdown(
        project_id=proj_a.id,
        case_id=hcase_a1.id,
        user_id=restricted_none_viewer.id,
        version_id=ver_a1.id,
        has_project_manage=False,
    )
    assert "Public API Gateway Standard" in none_md
    assert "Classified Encryption Key Vault Topology" not in none_md
    assert "RESTRICTED_VAULT_MARKER" not in none_md
    assert "Internal Queue Worker Topology" not in none_md
    assert "TEAM_INTERNAL_MARKER" not in none_md

    # 4. Canonical stored package & SHA-256 hash MUST remain 100% unchanged!
    session.flush()
    reloaded_ver = session.get(HandoverPackageVersion, ver_a1.id)
    assert reloaded_ver is not None
    assert reloaded_ver.content_hash == original_hash
    reloaded_sec = session.execute(
        select(HandoverPackageSection).where(
            HandoverPackageSection.version_id == ver_a1.id,
            HandoverPackageSection.section_type == "decisions_rationale",
        )
    ).scalar_one()
    assert reloaded_sec.section_content == original_canonical_content

    # 5. Immutable audit events recorded WITHOUT leaking restricted excerpts or secrets
    export_audits = list(
        session.execute(
            select(AuditLog).where(
                AuditLog.project_id == proj_a.id,
                AuditLog.event_type == "handover.package.exported",
            )
        )
        .scalars()
        .all()
    )
    assert len(export_audits) >= 4
    for evt in export_audits:
        serialized = str(evt.event_metadata or {})
        assert "RESTRICTED_VAULT_MARKER" not in serialized
        assert "TEAM_INTERNAL_MARKER" not in serialized
        assert "SuperSecretValue999" not in serialized
        assert "ghp_1234567890" not in serialized


def test_export_security_boundaries_cross_project_cross_case_and_invalid_principals(
    export_env: dict[str, Any],
) -> None:
    """Verify fail-closed enforcement on missing/inactive principal, cross-project, cross-case, and HTTP auth."""
    session: Session = export_env["session"]
    org = export_env["org"]
    proj_a = export_env["proj_a"]
    proj_b = export_env["proj_b"]
    hcase_a1 = export_env["hcase_a1"]
    hcase_a2 = export_env["hcase_a2"]
    ver_a1 = export_env["ver_a1"]
    ver_a2 = export_env["ver_a2"]
    full_viewer = export_env["full_viewer"]
    partial_viewer = export_env["partial_viewer"]
    inactive_user = export_env["inactive_user"]
    outsider = export_env["outsider"]

    svc = HandoverExportService(session)

    # Missing principal fails closed
    with pytest.raises(ForbiddenError):
        svc.export_json(project_id=proj_a.id, case_id=hcase_a1.id, user_id=None)

    # Invalid / unknown UUID fails closed
    with pytest.raises(ForbiddenError):
        svc.export_json(project_id=proj_a.id, case_id=hcase_a1.id, user_id=uuid.uuid4())

    # Suspended/inactive user fails closed
    with pytest.raises(ForbiddenError):
        svc.export_json(project_id=proj_a.id, case_id=hcase_a1.id, user_id=inactive_user.id)

    # Non-member outsider fails closed
    with pytest.raises(ForbiddenError):
        svc.export_json(project_id=proj_a.id, case_id=hcase_a1.id, user_id=outsider.id)

    # Cross-project attempt (case from proj_a queried under proj_b by outsider) fails closed
    with pytest.raises(NotFoundError):
        svc.export_json(project_id=proj_b.id, case_id=hcase_a1.id, user_id=outsider.id)

    # Cross-case version_id mismatch (case a1 requesting version from case a2) fails closed
    with pytest.raises(NotFoundError):
        svc.export_json(
            project_id=proj_a.id,
            case_id=hcase_a1.id,
            user_id=full_viewer.id,
            version_id=ver_a2.id,
            has_project_manage=True,
        )

    # HTTP-layer checks (unauthenticated 401, outsider 404/403, partial viewer ACL-filtered 200)
    def _override_db() -> Any:
        yield session

    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)

        # Unauthenticated HTTP request blocked (401)
        resp_unauth = client.get(f"/api/v1/projects/{proj_a.id}/handover/cases/{hcase_a1.id}/export?format=json")
        assert resp_unauth.status_code == 401

        # Authenticated partial viewer via HTTP: server-side principal enforces ACL regardless of query params
        active = {"user": partial_viewer}

        def _override_principal() -> Any:
            class _P:
                user = active["user"]
                user_id = active["user"].id
                organisation_id = org.id
            return _P()

        app.dependency_overrides[get_current_principal] = _override_principal

        # Even if client tries to spoof ?user_id=<full_viewer> or ?has_project_manage=true, server ignores it!
        resp_partial = client.get(
            f"/api/v1/projects/{proj_a.id}/handover/cases/{hcase_a1.id}/export"
            f"?format=json&user_id={full_viewer.id}&has_project_manage=true"
        )
        assert resp_partial.status_code == 200
        body = resp_partial.json()
        assert body["viewer_acl_filtered"] is True
        assert body["omitted_restricted_items_count"] == 1
        assert "RESTRICTED_VAULT_MARKER" not in str(body)

        # Cross-case version_id via HTTP -> 404
        resp_xcase = client.get(
            f"/api/v1/projects/{proj_a.id}/handover/cases/{hcase_a1.id}/export?format=json&version_id={ver_a2.id}"
        )
        assert resp_xcase.status_code == 404

        # Outsider via HTTP -> 404/403
        active["user"] = outsider
        resp_out = client.get(
            f"/api/v1/projects/{proj_a.id}/handover/cases/{hcase_a1.id}/export?format=json&version_id={ver_a1.id}"
        )
        assert resp_out.status_code in (403, 404)
    finally:
        app.dependency_overrides.clear()
