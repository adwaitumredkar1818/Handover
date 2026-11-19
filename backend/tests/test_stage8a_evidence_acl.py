"""Stage 8A — Evidence-Level ACL Enforcement & Provenance Security Tests.

Covers all 14 mandatory Stage 8A security scenarios (ACL-T01 through ACL-T14),
list/detail consistency, derived-assessment & revision redaction, error-message
safety, and batched SQL query performance verification using isolated test fixtures.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.models.enums import (
    ConflictPriority,
    ConflictResolutionState,
    ConflictType,
    EvidenceProcessingStatus,
    EvidenceSourceType,
    IssueResolutionState,
    RoleName,
    SourcePermissionVerificationStatus,
    SourceVisibilityPolicy,
    TemporalComparison,
    VerificationCaseStatus,
    VerificationCategory,
    VerificationIssueType,
)
from app.models.evidence import EvidenceItem
from app.models.integration import SourceAccessPolicy, SourceConnection
from app.models.knowledge import KnowledgeEvidenceLink, KnowledgeItem
from app.models.verification import (
    VerificationCase,
    VerificationConflict,
    VerificationEvidenceRef,
    VerificationFindingRevision,
    VerificationIssue,
)
from app.services.integrations.access_policy import SourceAccessPolicyService
from tests.conftest import (
    invite_and_accept_member,
    isolated_auth_app,
    register_and_login_user,
)


def _create_org_and_project(client: TestClient, headers: dict[str, str], suffix: str) -> tuple[str, str]:
    org_res = client.post(
        "/api/v1/organisations",
        headers=headers,
        json={"name": f"Stage8A Org {suffix}", "slug": f"s8a-org-{suffix}-{uuid.uuid4().hex[:6]}"},
    )
    assert org_res.status_code == 201, org_res.text
    org_id = org_res.json()["id"]

    proj_res = client.post(
        f"/api/v1/organisations/{org_id}/projects",
        headers=headers,
        json={"name": f"Stage8A Proj {suffix}", "slug": f"s8a-proj-{suffix}-{uuid.uuid4().hex[:6]}"},
    )
    assert proj_res.status_code == 201, proj_res.text
    return org_id, proj_res.json()["id"]


def _add_member(
    client: TestClient,
    *,
    org_id: str,
    proj_id: str,
    owner_headers: dict[str, str],
    user,
    role_name: str = RoleName.PROJECT_MEMBER.value,
) -> None:
    invite_and_accept_member(
        client,
        organisation_id=org_id,
        inviter_headers=owner_headers,
        invitee=user,
        role_name="org_member",
    )
    res = client.post(
        f"/api/v1/projects/{proj_id}/members",
        headers=owner_headers,
        json={"user_id": str(user.user_id), "role_name": role_name},
    )
    assert res.status_code in (200, 201), res.text


def _seed_source_and_evidence(
    session: Session,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    owner_id: uuid.UUID,
    title: str,
    acl_scope: str = "project_members",
    allowed_user_ids: list[str] | None = None,
    sync_status: str = SourcePermissionVerificationStatus.VERIFIED.value,
    visibility_policy: str | None = None,
    source_type: str = EvidenceSourceType.GITHUB.value,
    deleted: bool = False,
) -> EvidenceItem:
    policy_id = None
    conn_id = None
    if acl_scope == "source_restricted" or allowed_user_ids is not None or sync_status != SourcePermissionVerificationStatus.VERIFIED.value:
        conn = SourceConnection(
            organisation_id=org_id,
            provider=source_type if source_type in ("github", "jira", "slack") else "github",
            display_name=f"Conn {title[:30]}",
            status="active",
            created_by_user_id=owner_id,
        )
        session.add(conn)
        session.flush()
        conn_id = conn.id
        vis = visibility_policy or (
            SourceVisibilityPolicy.VERIFIED_SOURCE_ACL.value
            if acl_scope == "source_restricted"
            else SourceVisibilityPolicy.PROJECT_MEMBERS_VERIFIED.value
        )
        policy = SourceAccessPolicy(
            organisation_id=org_id,
            project_id=project_id,
            source_connection_id=conn.id,
            provider=conn.provider,
            scope_identifier=f"scope-{uuid.uuid4().hex[:10]}",
            visibility_policy=vis,
            sync_permission_status=sync_status,
            authorised_by_user_id=owner_id,
            allowed_user_ids=allowed_user_ids if allowed_user_ids is not None else [],
        )
        session.add(policy)
        session.flush()
        policy_id = policy.id

    ev = EvidenceItem(
        organisation_id=org_id,
        project_id=project_id,
        source_connection_id=conn_id,
        source_access_policy_id=policy_id,
        source_type=source_type,
        source_provider=source_type,
        source_external_id=f"ext-{uuid.uuid4().hex[:12]}",
        source_url=f"https://github.com/org/repo/blob/main/{uuid.uuid4().hex[:8]}.md",
        source_author_identity="secret-author-handle" if acl_scope == "source_restricted" else "public-author",
        title=title,
        content_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        uploaded_by_user_id=owner_id,
        category="project_document",
        acl_scope=acl_scope,
        processing_status=(
            EvidenceProcessingStatus.DELETED.value if deleted else EvidenceProcessingStatus.EXTRACTED.value
        ),
        deleted_at=datetime.now(UTC) if deleted else None,
    )
    session.add(ev)
    session.flush()
    return ev


def _seed_case_with_evidence(
    session: Session,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    title: str,
    claim: str,
    evidences: list[EvidenceItem],
    status: str = VerificationCaseStatus.CANDIDATE.value,
    domain: str = "technical_architecture",
    person_name: str | None = None,
    machine_assessment: dict | None = None,
    revisions: list[tuple[int, str, bool, str | None]] | None = None,
) -> VerificationCase:
    ki = KnowledgeItem(
        organisation_id=org_id,
        project_id=project_id,
        category=domain,
        title=title,
        structured_summary=claim,
        support_classification="direct",
        structured_payload={},
        extraction_model="test-model",
        prompt_version="test-v1",
        fingerprint=uuid.uuid4().hex,
    )
    session.add(ki)
    session.flush()

    case = VerificationCase(
        organisation_id=org_id,
        project_id=project_id,
        target_type="knowledge_item",
        target_id=ki.id,
        domain=domain,
        title=title,
        original_ai_claim=claim,
        current_claim=claim,
        person_name=person_name,
        source_provider=evidences[0].source_type if evidences else None,
        case_status=status,
        priority="high",
        machine_assessment_json=machine_assessment or {},
    )
    session.add(case)
    session.flush()

    for ev in evidences:
        session.add(
            KnowledgeEvidenceLink(
                organisation_id=org_id,
                project_id=project_id,
                knowledge_item_id=ki.id,
                evidence_id=ev.id,
                support_type="direct",
                supporting_excerpt=f"Excerpt from {ev.title}",
            )
        )
        session.add(
            VerificationEvidenceRef(
                organisation_id=org_id,
                project_id=project_id,
                case_id=case.id,
                evidence_item_id=ev.id,
                relationship_to_finding="supports",
                excerpt=f"Excerpt from {ev.title}",
                location_label="Section 1",
            )
        )

    if revisions:
        for rev_no, text, is_ai, reason in revisions:
            session.add(
                VerificationFindingRevision(
                    organisation_id=org_id,
                    project_id=project_id,
                    case_id=case.id,
                    revision_number=rev_no,
                    claim_text=text,
                    domain=domain,
                    is_ai_original=is_ai,
                    edit_reason=reason,
                )
            )
    session.flush()
    return case


def test_acl_t01_to_t06_conflict_side_isolation_and_fail_closed_null_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ACL-T01..ACL-T06: Both allowed, A-only, B-only, neither allowed, null ref, deleted/missing ref."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        owner = register_and_login_user(client, email="s8a-owner1@example.com", full_name="Owner")
        reviewer_a = register_and_login_user(client, email="s8a-reva@example.com", full_name="Reviewer A")
        reviewer_b = register_and_login_user(client, email="s8a-revb@example.com", full_name="Reviewer B")
        restricted_member = register_and_login_user(client, email="s8a-mem@example.com", full_name="Member")
        org_id_s, proj_id_s = _create_org_and_project(client, owner.headers, "t01-t06")
        org_id, proj_id = uuid.UUID(org_id_s), uuid.UUID(proj_id_s)

        _add_member(client, org_id=org_id_s, proj_id=proj_id_s, owner_headers=owner.headers, user=reviewer_a, role_name=RoleName.REVIEWER.value)
        _add_member(client, org_id=org_id_s, proj_id=proj_id_s, owner_headers=owner.headers, user=reviewer_b, role_name=RoleName.REVIEWER.value)
        _add_member(client, org_id=org_id_s, proj_id=proj_id_s, owner_headers=owner.headers, user=restricted_member, role_name=RoleName.PROJECT_MEMBER.value)

        with ctx.session_factory() as db:
            ev_pub_a = _seed_source_and_evidence(db, org_id=org_id, project_id=proj_id, owner_id=owner.user_id, title="Public Spec A")
            ev_pub_b = _seed_source_and_evidence(db, org_id=org_id, project_id=proj_id, owner_id=owner.user_id, title="Public Spec B")
            ev_only_a = _seed_source_and_evidence(
                db,
                org_id=org_id,
                project_id=proj_id,
                owner_id=owner.user_id,
                title="Classified Alpha Vault",
                acl_scope="source_restricted",
                allowed_user_ids=[str(owner.user_id), str(reviewer_a.user_id)],
            )
            ev_only_b = _seed_source_and_evidence(
                db,
                org_id=org_id,
                project_id=proj_id,
                owner_id=owner.user_id,
                title="Classified Beta Ledger",
                acl_scope="source_restricted",
                allowed_user_ids=[str(owner.user_id), str(reviewer_b.user_id)],
            )
            ev_deleted = _seed_source_and_evidence(
                db,
                org_id=org_id,
                project_id=proj_id,
                owner_id=owner.user_id,
                title="Soft Deleted Secret Doc",
                acl_scope="project_members",
                deleted=True,
            )

            case_pub = _seed_case_with_evidence(
                db, org_id=org_id, project_id=proj_id, title="Public Finding", claim="Public claim", evidences=[ev_pub_a]
            )
            case_priv = _seed_case_with_evidence(
                db, org_id=org_id, project_id=proj_id, title="Classified Alpha Finding", claim="Secret alpha claim", evidences=[ev_only_a]
            )

            # C1: Both accessible (ACL-T01)
            c_both = VerificationConflict(
                organisation_id=org_id,
                project_id=proj_id,
                case_id=case_pub.id,
                related_finding_id=case_pub.id,
                conflict_type=ConflictType.DECISION_CONFLICT.value,
                claim_a_text="Public claim alpha one",
                claim_a_source_evidence_id=ev_pub_a.id,
                claim_b_text="Public claim beta two",
                claim_b_source_evidence_id=ev_pub_b.id,
                side_a_source_title=ev_pub_a.title,
                side_a_provider="github",
                side_b_source_title=ev_pub_b.title,
                side_b_provider="github",
                explanation="Public decision divergence between Spec A and Spec B",
                priority=ConflictPriority.MEDIUM.value,
                temporal_comparison=TemporalComparison.SIMULTANEOUS.value,
                resolution_state=ConflictResolutionState.UNRESOLVED.value,
            )
            # C2: Side A (only reviewer_a/owner) vs Side B (only reviewer_b/owner) -> tests ACL-T02, ACL-T03, ACL-T04!
            c_split = VerificationConflict(
                organisation_id=org_id,
                project_id=proj_id,
                case_id=case_priv.id,
                related_finding_id=case_priv.id,
                conflict_type=ConflictType.TECHNICAL_CONFLICT.value,
                claim_a_text="ALPHA_VAULT_SECRET_TOKEN_991 uses HSM",
                claim_a_source_evidence_id=ev_only_a.id,
                claim_b_text="BETA_LEDGER_SECRET_TOKEN_882 uses KMS",
                claim_b_source_evidence_id=ev_only_b.id,
                side_a_source_title=ev_only_a.title,
                side_a_provider="github",
                side_b_source_title=ev_only_b.title,
                side_b_provider="jira",
                explanation="Divergence between Classified Alpha Vault and Classified Beta Ledger",
                authoritative_claim_text="Canonical secret from Classified Beta Ledger",
                investigation_notes="Private investigator notes mentioning BETA_LEDGER_SECRET_TOKEN_882",
                priority=ConflictPriority.CRITICAL.value,
                temporal_comparison=TemporalComparison.SIMULTANEOUS.value,
                resolution_state=ConflictResolutionState.UNRESOLVED.value,
            )
            # C3: Both evidence references NULL (ACL-T05 fail closed)
            c_null = VerificationConflict(
                organisation_id=org_id,
                project_id=proj_id,
                case_id=case_pub.id,
                conflict_type=ConflictType.STATUS_CONFLICT.value,
                claim_a_text="ORPHAN_NULL_CLAIM_A",
                claim_a_source_evidence_id=None,
                claim_b_text="ORPHAN_NULL_CLAIM_B",
                claim_b_source_evidence_id=None,
                side_a_source_title="Null Source A",
                side_a_provider="github",
                side_b_source_title="Null Source B",
                side_b_provider="jira",
                explanation="Orphan conflict with null evidence references",
                priority=ConflictPriority.HIGH.value,
                temporal_comparison=TemporalComparison.AMBIGUOUS.value,
                resolution_state=ConflictResolutionState.UNRESOLVED.value,
            )
            # C4: Deleted / unavailable evidence on both sides (ACL-T06 fail closed)
            c_deleted = VerificationConflict(
                organisation_id=org_id,
                project_id=proj_id,
                case_id=case_pub.id,
                conflict_type=ConflictType.OWNERSHIP_CONFLICT.value,
                claim_a_text="DELETED_EVIDENCE_CLAIM_A",
                claim_a_source_evidence_id=ev_deleted.id,
                claim_b_text="DELETED_EVIDENCE_CLAIM_B",
                claim_b_source_evidence_id=None,
                side_a_source_title=ev_deleted.title,
                side_a_provider="github",
                side_b_source_title="Unavailable Source",
                side_b_provider="github",
                explanation="Deleted evidence conflict",
                priority=ConflictPriority.LOW.value,
                temporal_comparison=TemporalComparison.AMBIGUOUS.value,
                resolution_state=ConflictResolutionState.UNRESOLVED.value,
            )
            db.add_all([c_both, c_split, c_null, c_deleted])
            db.commit()
            c_both_id, c_split_id, c_null_id, c_del_id = str(c_both.id), str(c_split.id), str(c_null.id), str(c_deleted.id)

        # ACL-T01: Owner sees C1 and C2 (both sides), NEVER sees C3 (null) or C4 (deleted)
        owner_list = client.get(f"/api/v1/projects/{proj_id_s}/conflicts", headers=owner.headers)
        assert owner_list.status_code == 200
        owner_ids = {item["id"] for item in owner_list.json()["items"]}
        assert owner_ids == {c_both_id, c_split_id}
        assert owner_list.json()["total_count"] == 2

        owner_split = client.get(f"/api/v1/projects/{proj_id_s}/conflicts/{c_split_id}", headers=owner.headers)
        assert owner_split.status_code == 200
        assert owner_split.json()["side_a"]["is_accessible"] is True
        assert owner_split.json()["side_b"]["is_accessible"] is True
        assert "ALPHA_VAULT_SECRET_TOKEN_991" in owner_split.json()["side_a"]["claim_text"]
        assert "BETA_LEDGER_SECRET_TOKEN_882" in owner_split.json()["side_b"]["claim_text"]

        # ACL-T02: Reviewer A can access Side A, NOT Side B
        reva_list = client.get(f"/api/v1/projects/{proj_id_s}/conflicts", headers=reviewer_a.headers)
        assert reva_list.status_code == 200
        reva_split_row = next(i for i in reva_list.json()["items"] if i["id"] == c_split_id)
        assert reva_split_row["side_a_title"] == "Classified Alpha Vault"
        assert reva_split_row["side_b_title"] == "[Restricted source]"
        assert "Classified Beta Ledger" not in str(reva_split_row)

        reva_detail = client.get(f"/api/v1/projects/{proj_id_s}/conflicts/{c_split_id}", headers=reviewer_a.headers)
        assert reva_detail.status_code == 200
        rd = reva_detail.json()
        assert rd["side_a"]["is_accessible"] is True
        assert "ALPHA_VAULT_SECRET_TOKEN_991" in rd["side_a"]["claim_text"]
        assert rd["side_b"]["is_accessible"] is False
        assert rd["side_b"]["title"] == "[Restricted source]"
        assert rd["side_b"]["evidence_item_id"] is None
        assert rd["side_b"]["source_url"] is None
        assert rd["side_b"]["author"] is None
        assert "BETA_LEDGER_SECRET_TOKEN_882" not in str(rd)
        assert "Classified Beta Ledger" not in str(rd)
        assert "[Explanation redacted" in rd["explanation"]
        assert "[Content redacted" in (rd["authoritative_claim_text"] or "")

        # ACL-T03: Reviewer B can access Side B, NOT Side A
        revb_detail = client.get(f"/api/v1/projects/{proj_id_s}/conflicts/{c_split_id}", headers=reviewer_b.headers)
        assert revb_detail.status_code == 200
        rb = revb_detail.json()
        assert rb["side_b"]["is_accessible"] is True
        assert "BETA_LEDGER_SECRET_TOKEN_882" in rb["side_b"]["claim_text"]
        assert rb["side_a"]["is_accessible"] is False
        assert rb["side_a"]["title"] == "[Restricted source]"
        assert "ALPHA_VAULT_SECRET_TOKEN_991" not in str(rb)
        assert "Classified Alpha Vault" not in str(rb)
        assert rb["related_finding_title"] == "[Restricted finding]"

        # ACL-T04: Restricted member has access to NEITHER side of C2 -> omitted from list & dashboard, 403 on detail!
        mem_dash = client.get(f"/api/v1/projects/{proj_id_s}/conflicts/dashboard", headers=restricted_member.headers)
        assert mem_dash.status_code == 200
        assert mem_dash.json()["total_conflicts"] == 1  # ONLY c_both!
        assert mem_dash.json()["critical_priority"] == 0

        mem_list = client.get(f"/api/v1/projects/{proj_id_s}/conflicts", headers=restricted_member.headers)
        assert mem_list.status_code == 200
        assert [i["id"] for i in mem_list.json()["items"]] == [c_both_id]
        assert mem_list.json()["total_count"] == 1

        mem_split = client.get(f"/api/v1/projects/{proj_id_s}/conflicts/{c_split_id}", headers=restricted_member.headers)
        assert mem_split.status_code == 403
        assert "Classified Alpha" not in mem_split.text
        assert "Classified Beta" not in mem_split.text
        assert "ALPHA_VAULT" not in mem_split.text

        # ACL-T05 (null evidence) & ACL-T06 (deleted evidence) fail closed with 403 and zero leakage even for owner!
        for blocked_id, forbidden_token in ((c_null_id, "ORPHAN_NULL"), (c_del_id, "DELETED_EVIDENCE")):
            res = client.get(f"/api/v1/projects/{proj_id_s}/conflicts/{blocked_id}", headers=owner.headers)
            assert res.status_code == 403
            assert forbidden_token not in res.text


def test_acl_t07_exception_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """ACL-T07: Exception inside ACL evaluation fails closed without leaking restricted content."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        owner = register_and_login_user(client, email="s8a-t07-owner@example.com", full_name="Owner")
        member = register_and_login_user(client, email="s8a-t07-mem@example.com", full_name="Member")
        org_id_s, proj_id_s = _create_org_and_project(client, owner.headers, "t07")
        org_id, proj_id = uuid.UUID(org_id_s), uuid.UUID(proj_id_s)
        _add_member(client, org_id=org_id_s, proj_id=proj_id_s, owner_headers=owner.headers, user=member)

        with ctx.session_factory() as db:
            ev = _seed_source_and_evidence(db, org_id=org_id, project_id=proj_id, owner_id=owner.user_id, title="Sensitive Doc T07")
            case = _seed_case_with_evidence(
                db, org_id=org_id, project_id=proj_id, title="Sensitive Case T07", claim="SECRET_T07_PAYLOAD", evidences=[ev]
            )
            conf = VerificationConflict(
                organisation_id=org_id,
                project_id=proj_id,
                case_id=case.id,
                conflict_type=ConflictType.DECISION_CONFLICT.value,
                claim_a_text="SECRET_T07_CONFLICT_A",
                claim_a_source_evidence_id=ev.id,
                claim_b_text="SECRET_T07_CONFLICT_B",
                claim_b_source_evidence_id=ev.id,
                side_a_source_title=ev.title,
                side_b_source_title=ev.title,
                explanation="T07 explanation",
                priority="high",
                temporal_comparison=TemporalComparison.SIMULTANEOUS.value,
                resolution_state=ConflictResolutionState.UNRESOLVED.value,
            )
            db.add(conf)
            db.commit()
            case_id, conf_id = str(case.id), str(conf.id)

        def _boom(*args, **kwargs):
            raise RuntimeError("Simulated ACL policy failure")

        monkeypatch.setattr(SourceAccessPolicyService, "can_user_access_evidence", _boom)

        # Conflict list, dashboard, detail all fail closed
        assert client.get(f"/api/v1/projects/{proj_id_s}/conflicts", headers=member.headers).json()["total_count"] == 0
        assert client.get(f"/api/v1/projects/{proj_id_s}/conflicts/dashboard", headers=member.headers).json()["total_conflicts"] == 0
        conf_res = client.get(f"/api/v1/projects/{proj_id_s}/conflicts/{conf_id}", headers=member.headers)
        assert conf_res.status_code == 403
        assert "SECRET_T07" not in conf_res.text

        # Verification queue, summary, detail all fail closed
        assert client.get(f"/api/v1/projects/{proj_id_s}/verification/queue", headers=member.headers).json()["total"] == 0
        assert client.get(f"/api/v1/projects/{proj_id_s}/verification/summary", headers=member.headers).json()["total_cases"] == 0
        case_res = client.get(f"/api/v1/projects/{proj_id_s}/verification/cases/{case_id}", headers=member.headers)
        assert case_res.status_code == 200
        assert case_res.json()["restricted_evidence_count"] == 1
        assert "SECRET_T07" not in case_res.text


def test_acl_t08_t09_search_oracle_counts_facets_and_pagination_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ACL-T08 & ACL-T09: Restricted claims/titles cannot be discovered via search, counts, facets, or pagination."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        owner = register_and_login_user(client, email="s8a-t08-owner@example.com", full_name="Owner")
        member = register_and_login_user(client, email="s8a-t08-mem@example.com", full_name="Member")
        org_id_s, proj_id_s = _create_org_and_project(client, owner.headers, "t08-t09")
        org_id, proj_id = uuid.UUID(org_id_s), uuid.UUID(proj_id_s)
        _add_member(client, org_id=org_id_s, proj_id=proj_id_s, owner_headers=owner.headers, user=member)

        with ctx.session_factory() as db:
            ev_pub = _seed_source_and_evidence(db, org_id=org_id, project_id=proj_id, owner_id=owner.user_id, title="Open Handbook")
            ev_priv = _seed_source_and_evidence(
                db,
                org_id=org_id,
                project_id=proj_id,
                owner_id=owner.user_id,
                title="Zebra Executive Vault",
                acl_scope="source_restricted",
                allowed_user_ids=[str(owner.user_id)],
                source_type=EvidenceSourceType.JIRA.value,
            )
            # 2 public findings, 3 restricted findings
            for idx in range(2):
                _seed_case_with_evidence(
                    db,
                    org_id=org_id,
                    project_id=proj_id,
                    title=f"Public Finding {idx}",
                    claim=f"Public claim content {idx}",
                    evidences=[ev_pub],
                    domain="work_items",
                    person_name="Public Dev",
                )
            priv_cases = []
            for idx in range(3):
                pc = _seed_case_with_evidence(
                    db,
                    org_id=org_id,
                    project_id=proj_id,
                    title=f"Secret Finding {idx}",
                    claim=f"UNIQUE_SECRET_ORACLE_TOKEN_{idx}",
                    evidences=[ev_priv],
                    domain="bugs_blockers_risks",
                    person_name="Secret CISO",
                    status=VerificationCaseStatus.CONFLICTED.value,
                )
                priv_cases.append(pc)

            # 1 partial conflict (pub vs priv) + 1 fully private conflict (priv vs priv)
            c_partial = VerificationConflict(
                organisation_id=org_id,
                project_id=proj_id,
                case_id=priv_cases[0].id,
                conflict_type=ConflictType.DECISION_CONFLICT.value,
                claim_a_text="PUBLIC_VISIBLE_MARKER_777",
                claim_a_source_evidence_id=ev_pub.id,
                claim_b_text="RESTRICTED_CONFLICT_ORACLE_XYZ",
                claim_b_source_evidence_id=ev_priv.id,
                side_a_source_title=ev_pub.title,
                side_b_source_title=ev_priv.title,
                explanation="Mentions RESTRICTED_EXPLANATION_ORACLE_999",
                priority="high",
                temporal_comparison=TemporalComparison.SIMULTANEOUS.value,
                resolution_state=ConflictResolutionState.UNRESOLVED.value,
            )
            c_full_priv = VerificationConflict(
                organisation_id=org_id,
                project_id=proj_id,
                case_id=priv_cases[1].id,
                conflict_type=ConflictType.TECHNICAL_CONFLICT.value,
                claim_a_text="FULLY_PRIVATE_CONFLICT_A",
                claim_a_source_evidence_id=ev_priv.id,
                claim_b_text="FULLY_PRIVATE_CONFLICT_B",
                claim_b_source_evidence_id=ev_priv.id,
                side_a_source_title=ev_priv.title,
                side_b_source_title=ev_priv.title,
                explanation="Fully private explanation",
                priority="critical",
                temporal_comparison=TemporalComparison.SIMULTANEOUS.value,
                resolution_state=ConflictResolutionState.UNRESOLVED.value,
            )
            db.add_all([c_partial, c_full_priv])
            db.commit()

        # ACL-T08: Search oracle blocked on Verification Queue & Conflict List
        assert client.get(f"/api/v1/projects/{proj_id_s}/verification/queue?search=UNIQUE_SECRET_ORACLE_TOKEN_0", headers=member.headers).json()["total"] == 0
        assert client.get(f"/api/v1/projects/{proj_id_s}/verification/queue?search=UNIQUE_SECRET_ORACLE_TOKEN_0", headers=owner.headers).json()["total"] == 1

        assert client.get(f"/api/v1/projects/{proj_id_s}/conflicts?search=RESTRICTED_CONFLICT_ORACLE_XYZ", headers=member.headers).json()["total_count"] == 0
        assert client.get(f"/api/v1/projects/{proj_id_s}/conflicts?search=RESTRICTED_EXPLANATION_ORACLE_999", headers=member.headers).json()["total_count"] == 0
        assert client.get(f"/api/v1/projects/{proj_id_s}/conflicts?search=Zebra", headers=member.headers).json()["total_count"] == 0
        # Searching the accessible Side A marker DOES succeed for member
        assert client.get(f"/api/v1/projects/{proj_id_s}/conflicts?search=PUBLIC_VISIBLE_MARKER_777", headers=member.headers).json()["total_count"] == 1
        # Owner CAN search restricted markers
        assert client.get(f"/api/v1/projects/{proj_id_s}/conflicts?search=RESTRICTED_CONFLICT_ORACLE_XYZ", headers=owner.headers).json()["total_count"] == 1

        # ACL-T09: Counts, facets, and pagination do not leak restricted records
        mem_sum = client.get(f"/api/v1/projects/{proj_id_s}/verification/summary", headers=member.headers).json()
        own_sum = client.get(f"/api/v1/projects/{proj_id_s}/verification/summary", headers=owner.headers).json()
        assert mem_sum["total_cases"] == 2
        assert mem_sum["conflicted_count"] == 0
        assert own_sum["total_cases"] == 5
        assert own_sum["conflicted_count"] == 3

        mem_q_p1 = client.get(f"/api/v1/projects/{proj_id_s}/verification/queue?limit=1&offset=0", headers=member.headers).json()
        mem_q_p2 = client.get(f"/api/v1/projects/{proj_id_s}/verification/queue?limit=1&offset=1", headers=member.headers).json()
        mem_q_p3 = client.get(f"/api/v1/projects/{proj_id_s}/verification/queue?limit=1&offset=2", headers=member.headers).json()
        assert mem_q_p1["total"] == 2
        assert len(mem_q_p1["items"]) == 1
        assert len(mem_q_p2["items"]) == 1
        assert len(mem_q_p3["items"]) == 0
        # Facets must NOT leak restricted domain, source, or person!
        assert "bugs_blockers_risks" not in mem_q_p1["available_domains"]
        assert "jira" not in mem_q_p1["available_sources"]
        assert "Secret CISO" not in mem_q_p1["available_people"]

        mem_dash = client.get(f"/api/v1/projects/{proj_id_s}/conflicts/dashboard", headers=member.headers).json()
        own_dash = client.get(f"/api/v1/projects/{proj_id_s}/conflicts/dashboard", headers=owner.headers).json()
        assert mem_dash["total_conflicts"] == 1
        assert mem_dash["critical_priority"] == 0
        assert own_dash["total_conflicts"] == 2
        assert own_dash["critical_priority"] == 1


def test_acl_t10_t11_t12_machine_assessment_revisions_and_authorized_reviewer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ACL-T10, ACL-T11, ACL-T12: Machine assessment titles & historical revisions redacted for unauthorized viewer, preserved for authorized reviewer."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        owner = register_and_login_user(client, email="s8a-t10-owner@example.com", full_name="Owner")
        auth_rev = register_and_login_user(client, email="s8a-t10-rev@example.com", full_name="Authorized Reviewer")
        unauth_mem = register_and_login_user(client, email="s8a-t10-mem@example.com", full_name="Unauthorized Member")
        org_id_s, proj_id_s = _create_org_and_project(client, owner.headers, "t10-t12")
        org_id, proj_id = uuid.UUID(org_id_s), uuid.UUID(proj_id_s)
        _add_member(client, org_id=org_id_s, proj_id=proj_id_s, owner_headers=owner.headers, user=auth_rev, role_name=RoleName.REVIEWER.value)
        _add_member(client, org_id=org_id_s, proj_id=proj_id_s, owner_headers=owner.headers, user=unauth_mem, role_name=RoleName.PROJECT_MEMBER.value)

        with ctx.session_factory() as db:
            ev_pub = _seed_source_and_evidence(db, org_id=org_id, project_id=proj_id, owner_id=owner.user_id, title="Public Architecture ADR")
            ev_priv = _seed_source_and_evidence(
                db,
                org_id=org_id,
                project_id=proj_id,
                owner_id=owner.user_id,
                title="TopSecret M&A Acquisition Memo",
                acl_scope="source_restricted",
                allowed_user_ids=[str(owner.user_id), str(auth_rev.user_id)],
            )

            # Case 1 (ACL-T10): Public finding whose machine_assessment references the restricted source title & contradiction
            case_ma = _seed_case_with_evidence(
                db,
                org_id=org_id,
                project_id=proj_id,
                title="Primary Billing Architecture",
                claim="Billing runs on Stripe v2.",
                evidences=[ev_pub],
                machine_assessment={
                    "priority_reason": "Superseded by TopSecret M&A Acquisition Memo",
                    "freshness_assessment": {
                        "status": "superseded",
                        "age_days": 45,
                        "explanation": "Superseded by TopSecret M&A Acquisition Memo dated yesterday.",
                        "superseded_by_record_title": "TopSecret M&A Acquisition Memo",
                        "superseded_by_evidence_id": str(ev_priv.id),
                        "reverification_required": True,
                        "recommendations": ["Review TopSecret M&A Acquisition Memo"],
                    },
                    "contradiction_analysis": {
                        "has_contradiction": True,
                        "contradiction_count": 1,
                        "summary": "Conflicts with TopSecret M&A Acquisition Memo",
                        "contradictions": [
                            {
                                "conflict_type": "decision_conflict",
                                "explanation": "Public Architecture ADR vs TopSecret M&A Acquisition Memo",
                                "severity": "high",
                                "side_a_evidence_id": str(ev_pub.id),
                                "side_a_title": "Public Architecture ADR",
                                "side_a_claim": "Billing runs on Stripe v2.",
                                "side_a_provider": "github",
                                "side_b_evidence_id": str(ev_priv.id),
                                "side_b_title": "TopSecret M&A Acquisition Memo",
                                "side_b_claim": "SECRET_ACQUISITION_BILLING_MIGRATION",
                                "side_b_provider": "jira",
                            }
                        ],
                    },
                },
            )
            db.add(
                VerificationIssue(
                    organisation_id=org_id,
                    project_id=proj_id,
                    case_id=case_ma.id,
                    verification_category=VerificationCategory.CONFLICTING_EVIDENCE.value,
                    issue_type=VerificationIssueType.CONFLICTING_SOURCES.value,
                    severity="high",
                    description="Contradicts TopSecret M&A Acquisition Memo",
                    conflicting_evidence_id=ev_priv.id,
                    resolution_state=IssueResolutionState.OPEN.value,
                )
            )

            # Case 2 (ACL-T11): Finding backed by restricted evidence with historical revisions
            case_rev = _seed_case_with_evidence(
                db,
                org_id=org_id,
                project_id=proj_id,
                title="Acquisition Integration Plan",
                claim="CURRENT_SECRET_REVISION_V2",
                evidences=[ev_priv],
                revisions=[
                    (1, "HISTORICAL_SECRET_REVISION_V1_DO_NOT_LEAK", True, "Initial AI extraction"),
                    (2, "CURRENT_SECRET_REVISION_V2", False, "Updated from TopSecret M&A Acquisition Memo"),
                ],
            )
            db.commit()
            case_ma_id, case_rev_id = str(case_ma.id), str(case_rev.id)

        # ACL-T10: Unauthorized member inspecting Case 1 sees public evidence, ZERO restricted titles/claims in assessment or issues!
        unauth_ma = client.get(f"/api/v1/projects/{proj_id_s}/verification/cases/{case_ma_id}", headers=unauth_mem.headers)
        assert unauth_ma.status_code == 200
        body_ma = unauth_ma.json()
        assert "TopSecret M&A Acquisition Memo" not in unauth_ma.text
        assert "SECRET_ACQUISITION_BILLING_MIGRATION" not in unauth_ma.text
        assert body_ma["freshness_assessment"]["superseded_by_record_title"] == "[Restricted source]"
        assert body_ma["contradiction_analysis"]["contradictions"][0]["side_b_title"] == "[Restricted source]"
        assert "[Content redacted" in body_ma["contradiction_analysis"]["contradictions"][0]["side_b_claim"]
        assert body_ma["issues"][0]["conflicting_evidence_id"] is None
        assert "[Issue details redacted" in body_ma["issues"][0]["description"]

        # ACL-T11: Unauthorized member inspecting Case 2 sees ZERO restricted claim or historical revision text!
        unauth_rev = client.get(f"/api/v1/projects/{proj_id_s}/verification/cases/{case_rev_id}", headers=unauth_mem.headers)
        assert unauth_rev.status_code == 200
        body_rev = unauth_rev.json()
        assert body_rev["restricted_evidence_count"] == 1
        assert body_rev["title"] == "[Restricted finding]"
        assert "HISTORICAL_SECRET_REVISION_V1" not in unauth_rev.text
        assert "CURRENT_SECRET_REVISION_V2" not in unauth_rev.text
        assert "TopSecret M&A Acquisition Memo" not in unauth_rev.text
        assert all("[Content redacted" in r["claim_text"] for r in body_rev["revisions"])
        assert all(r["edit_reason"] is None for r in body_rev["revisions"])

        # ACL-T12: Authorized reviewer retains FULL legitimate access to both cases!
        auth_ma = client.get(f"/api/v1/projects/{proj_id_s}/verification/cases/{case_ma_id}", headers=auth_rev.headers)
        assert auth_ma.status_code == 200
        assert auth_ma.json()["freshness_assessment"]["superseded_by_record_title"] == "TopSecret M&A Acquisition Memo"
        assert "SECRET_ACQUISITION_BILLING_MIGRATION" in auth_ma.text

        auth_rev_res = client.get(f"/api/v1/projects/{proj_id_s}/verification/cases/{case_rev_id}", headers=auth_rev.headers)
        assert auth_rev_res.status_code == 200
        assert auth_rev_res.json()["restricted_evidence_count"] == 0
        assert "HISTORICAL_SECRET_REVISION_V1_DO_NOT_LEAK" in auth_rev_res.text
        assert "CURRENT_SECRET_REVISION_V2" in auth_rev_res.text


def test_acl_t13_t14_cross_project_rbac_and_batch_query_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ACL-T13, ACL-T14 & Performance: Cross-project isolation, RBAC enforcement, and batched ACL query budget."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        owner_a = register_and_login_user(client, email="s8a-t13-ownera@example.com", full_name="Owner A")
        owner_b = register_and_login_user(client, email="s8a-t13-ownerb@example.com", full_name="Owner B")
        viewer_a = register_and_login_user(client, email="s8a-t13-viewera@example.com", full_name="Viewer A")

        org_a_s, proj_a_s = _create_org_and_project(client, owner_a.headers, "t13-a")
        org_b_s, proj_b_s = _create_org_and_project(client, owner_b.headers, "t13-b")
        org_a, proj_a = uuid.UUID(org_a_s), uuid.UUID(proj_a_s)
        org_b, proj_b = uuid.UUID(org_b_s), uuid.UUID(proj_b_s)
        _add_member(client, org_id=org_a_s, proj_id=proj_a_s, owner_headers=owner_a.headers, user=viewer_a, role_name=RoleName.PROJECT_MEMBER.value)

        with ctx.session_factory() as db:
            # Seed 15 cases & 15 conflicts in Project A to verify batched query count (no N+1)
            ev_list = [
                _seed_source_and_evidence(db, org_id=org_a, project_id=proj_a, owner_id=owner_a.user_id, title=f"Doc {i}")
                for i in range(15)
            ]
            cases = [
                _seed_case_with_evidence(db, org_id=org_a, project_id=proj_a, title=f"Case {i}", claim=f"Claim {i}", evidences=[ev_list[i]])
                for i in range(15)
            ]
            conflicts = []
            for i in range(15):
                cf = VerificationConflict(
                    organisation_id=org_a,
                    project_id=proj_a,
                    case_id=cases[i].id,
                    conflict_type=ConflictType.DECISION_CONFLICT.value,
                    claim_a_text=f"Claim A {i}",
                    claim_a_source_evidence_id=ev_list[i].id,
                    claim_b_text=f"Claim B {i}",
                    claim_b_source_evidence_id=ev_list[(i + 1) % 15].id,
                    side_a_source_title=ev_list[i].title,
                    side_b_source_title=ev_list[(i + 1) % 15].title,
                    explanation=f"Explanation {i}",
                    priority="medium",
                    temporal_comparison=TemporalComparison.SIMULTANEOUS.value,
                    resolution_state=ConflictResolutionState.UNRESOLVED.value,
                )
                conflicts.append(cf)
            db.add_all(conflicts)

            # Seed a Project B conflict referencing a cross-project Project A evidence ID (must fail closed!)
            case_b = _seed_case_with_evidence(db, org_id=org_b, project_id=proj_b, title="Case B", claim="Claim B", evidences=[])
            cross_conf = VerificationConflict(
                organisation_id=org_b,
                project_id=proj_b,
                case_id=case_b.id,
                conflict_type=ConflictType.DECISION_CONFLICT.value,
                claim_a_text="CROSS_PROJECT_LEAK_ATTEMPT",
                claim_a_source_evidence_id=ev_list[0].id,  # belongs to Project A!
                claim_b_text="CROSS_PROJECT_LEAK_ATTEMPT_B",
                claim_b_source_evidence_id=ev_list[1].id,  # belongs to Project A!
                side_a_source_title="Project A Doc",
                side_b_source_title="Project A Doc 2",
                explanation="Cross project attempt",
                priority="high",
                temporal_comparison=TemporalComparison.SIMULTANEOUS.value,
                resolution_state=ConflictResolutionState.UNRESOLVED.value,
            )
            db.add(cross_conf)
            db.commit()
            case_a_id, conf_a_id, cross_conf_id = str(cases[0].id), str(conflicts[0].id), str(cross_conf.id)

        # ACL-T13: Cross-project IDs cannot bypass ACL or project isolation
        assert client.get(f"/api/v1/projects/{proj_b_s}/conflicts/{conf_a_id}", headers=owner_b.headers).status_code == 404
        assert client.get(f"/api/v1/projects/{proj_b_s}/verification/cases/{case_a_id}", headers=owner_b.headers).status_code == 404
        assert client.get(f"/api/v1/projects/{proj_a_s}/conflicts", headers=owner_b.headers).status_code in (403, 404)
        # Cross-project evidence ID inside Project B conflict fails closed!
        cross_res = client.get(f"/api/v1/projects/{proj_b_s}/conflicts/{cross_conf_id}", headers=owner_b.headers)
        assert cross_res.status_code == 403
        assert "CROSS_PROJECT_LEAK_ATTEMPT" not in cross_res.text

        # ACL-T14: RBAC restrictions remain enforced (unauthenticated -> 401; viewer cannot mutate -> 403)
        assert client.get(f"/api/v1/projects/{proj_a_s}/conflicts").status_code == 401
        assert client.get(f"/api/v1/projects/{proj_a_s}/verification/queue").status_code == 401
        assert (
            client.post(
                f"/api/v1/projects/{proj_a_s}/conflicts/{conf_a_id}/resolve",
                headers=viewer_a.headers,
                json={"resolution_strategy": "reconciled", "resolution_notes": "Unauthorized attempt"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/v1/projects/{proj_a_s}/verification/cases/{case_a_id}/approve",
                headers=viewer_a.headers,
                json={"reviewer_note": "Unauthorized approve"},
            ).status_code
            == 403
        )

        # Performance check: Verify O(1) batched SQL query counts on ACL/data queries (zero N+1 across 15 items / 30 refs!)
        acl_queries: list[str] = []

        def _count_queries(_conn, _cursor, statement, *_args, **_kwargs):
            low = statement.lower()
            if any(
                tbl in low
                for tbl in (
                    "evidence_items",
                    "source_access_policies",
                    "verification_conflicts",
                    "verification_cases",
                    "verification_evidence_refs",
                    "verification_issues",
                )
            ):
                acl_queries.append(statement.splitlines()[0])

        event.listen(ctx.engine, "before_cursor_execute", _count_queries)
        try:
            acl_queries.clear()
            r1 = client.get(f"/api/v1/projects/{proj_a_s}/conflicts", headers=owner_a.headers)
            assert r1.status_code == 200 and r1.json()["total_count"] == 15
            conflict_list_queries = len(acl_queries)

            acl_queries.clear()
            r2 = client.get(f"/api/v1/projects/{proj_a_s}/verification/queue", headers=owner_a.headers)
            assert r2.status_code == 200 and r2.json()["total"] == 15
            queue_list_queries = len(acl_queries)
        finally:
            event.remove(ctx.engine, "before_cursor_execute", _count_queries)

        # Strictly O(1) batched evaluation (independent of N=15 items / 30 evidence refs)
        assert conflict_list_queries <= 6, f"N+1 detected on conflict list: {conflict_list_queries}"
        assert queue_list_queries <= 8, f"N+1 detected on verification queue: {queue_list_queries}"
