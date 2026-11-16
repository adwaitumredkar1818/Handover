"""Tests for team roster extraction, human-in-the-loop reconciliation, and GitHub contribution attribution."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.enums import (
    ContributionCategory,
    IdentityMatchMethod,
    ReconciliationStatus,
    ResponsibilityAlignment,
)
from app.models.evidence import EvidenceContent, EvidenceItem
from app.models.team_roster import ContributionAttribution, TeamRosterMember
from app.services.contribution_attribution import ContributionAttributionService
from app.services.roster_extraction import (
    TeamRosterExtractionService,
    _extract_roster_rows_from_text,
)
from tests.conftest import isolated_auth_app, register_and_login_user


def test_roster_extraction_and_reconciliation_logic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test TeamRosterExtractionService parsing tabular text and reconciling against project members."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        db_factory = ctx.session_factory
        user = register_and_login_user(
            client,
            email="sarah.architect@example.com",
            full_name="Sarah Connor",
        )

        org_res = client.post(
            "/api/v1/organisations",
            headers=user.headers,
            json={"name": "Cyberdyne Org", "slug": f"cyberdyne-{uuid.uuid4().hex[:6]}"},
        )
        org_id = org_res.json()["id"]

        proj_res = client.post(
            f"/api/v1/organisations/{org_id}/projects",
            headers=user.headers,
            json={"name": "Defense Net", "slug": f"defense-net-{uuid.uuid4().hex[:6]}"},
        )
        project_id = proj_res.json()["id"]

        with db_factory() as db:
            # Create a mock team roster evidence item
            ev = EvidenceItem(
                id=uuid.uuid4(),
                organisation_id=uuid.UUID(org_id),
                project_id=uuid.UUID(project_id),
                source_type="document_upload",
                category="team_roster",
                document_category="team_roster",
                title="Project Defense Net - Official Team Roster v1.0",
                source_external_id="roster-doc-001",
                content_hash="b" * 64,
                original_filename="team_roster.docx",
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            db.add(ev)
            db.commit()
            db.refresh(ev)
            evidence_id = ev.id

            sample_roster_content = """
# Project Team Roster & Ownership Matrix

| Member ID | Full Name | Email | Role | Responsibilities | Component Ownership | GitHub Username | Git Commit Email |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| M-101 | Sarah Connor | sarah.architect@example.com | Chief Architect | System architecture, distributed consensus, security audits | core-kernel, auth-service | sarah-connor | sarah.architect@example.com |
| M-102 | Kyle Reese | reese.kyle@example.com | Senior Infrastructure Engineer | Cloud deployment, Docker, CI/CD pipelines, Kubernetes | infra-helm, terraform-aws | reese-ops | kyle@resistance.org |
| M-103 | John Connor | john.c@example.com | Lead Frontend Developer | Next.js user interface, design system, accessibility | web-portal, design-tokens | john-connor-dev | john@resistance.org |
"""

            content = EvidenceContent(
                evidence_id=evidence_id,
                extracted_text=sample_roster_content,
                char_count=len(sample_roster_content),
                word_count=len(sample_roster_content.split()),
            )
            db.add(content)
            db.commit()

            extracted_members = _extract_roster_rows_from_text(sample_roster_content)
            assert len(extracted_members) == 3

            m1 = extracted_members[0]
            assert m1["full_name"] == "Sarah Connor"
            assert m1["email"] == "sarah.architect@example.com"
            assert m1["role_name"] == "Chief Architect"
            assert any("architecture" in r.lower() for r in m1["primary_responsibilities"])
            assert m1["github_username"] == "sarah-connor"

            m2 = extracted_members[1]
            assert m2["full_name"] == "Kyle Reese"
            assert m2["github_username"] == "reese-ops"

            # Run reconciliation against database
            extractor = TeamRosterExtractionService(session=db, settings=ctx.settings)
            persisted = extractor.extract_and_reconcile(evidence_id=evidence_id)
            assert len(persisted) == 3

            # Sarah should be MATCHED because she is already a member of the project
            sarah_rec = next(m for m in persisted if m.full_name == "Sarah Connor")
            assert sarah_rec.reconciliation_status == ReconciliationStatus.MATCHED.value
            assert sarah_rec.matched_project_membership_id is not None
            assert sarah_rec.reconciliation_confidence >= 0.9

            # Kyle and John should be NEW_CANDIDATE because they are not yet members of the project
            kyle_rec = next(m for m in persisted if m.full_name == "Kyle Reese")
            assert kyle_rec.reconciliation_status == ReconciliationStatus.NEW_CANDIDATE.value
            assert kyle_rec.matched_project_membership_id is None


def test_contribution_attribution_and_classification(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test ContributionAttributionService resolving identity and evaluating responsibility alignment."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        db_factory = ctx.session_factory
        user = register_and_login_user(
            client,
            email="alice.lead@example.com",
            full_name="Alice Developer",
        )

        org_res = client.post(
            "/api/v1/organisations",
            headers=user.headers,
            json={"name": "Atelier Org", "slug": f"atelier-{uuid.uuid4().hex[:6]}"},
        )
        org_id = org_res.json()["id"]

        proj_res = client.post(
            f"/api/v1/organisations/{org_id}/projects",
            headers=user.headers,
            json={"name": "Atelier Platform", "slug": f"atelier-plat-{uuid.uuid4().hex[:6]}"},
        )
        project_id = proj_res.json()["id"]

        with db_factory() as db:
            # Seed doc evidence for roster member FK
            doc_ev = EvidenceItem(
                id=uuid.uuid4(),
                organisation_id=uuid.UUID(org_id),
                project_id=uuid.UUID(project_id),
                source_type="document_upload",
                category="team_roster",
                title="Roster Source Document",
                source_external_id="roster-doc-seed-001",
                content_hash="d" * 64,
            )
            db.add(doc_ev)
            db.commit()

            # Create a roster member
            roster_member = TeamRosterMember(
                id=uuid.uuid4(),
                project_id=uuid.UUID(project_id),
                evidence_item_id=doc_ev.id,
                full_name="Alice Developer",
                email="alice.lead@example.com",
                role_name="Lead Security Architect",
                primary_responsibilities=["Cryptographic primitives", "Token encryption", "security architecture"],
                component_ownership=["backend/app/core/security.py", "backend/app/services/token_encryption.py"],
                github_username="alice-sec",
                git_commit_email="alice.lead@example.com",
                reconciliation_status=ReconciliationStatus.MATCHED.value,
            )
            db.add(roster_member)
            db.commit()

            # Create commit evidence
            commit_ev = EvidenceItem(
                id=uuid.uuid4(),
                organisation_id=uuid.UUID(org_id),
                project_id=uuid.UUID(project_id),
                source_type="github",
                category="commit",
                title="feat(security): implement AES-256-GCM envelope encryption for private storage",
                source_external_id="gh-commit-abc1234",
                content_hash="c" * 64,
                source_author_identity="alice-sec",
                metadata_json={
                    "github_author_login": "alice-sec",
                    "git_author_email": "alice.lead@example.com",
                    "files_changed": [
                        "backend/app/core/security.py",
                        "backend/app/services/token_encryption.py",
                    ],
                },
            )
            db.add(commit_ev)
            db.commit()

            service = ContributionAttributionService(db)
            attr = service.attribute_evidence(commit_ev)
            assert attr is not None
            assert attr.contributor_identifier == "alice-sec"
            assert attr.matched_roster_member_id == roster_member.id
            assert attr.match_method == IdentityMatchMethod.EXACT_GITHUB_USERNAME.value
            assert attr.contribution_category == ContributionCategory.SECURITY.value
            assert attr.responsibility_alignment == ResponsibilityAlignment.ALIGNED.value
            assert "aligns with declared responsibility" in attr.alignment_explanation


def test_team_roster_and_attribution_api_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test GET /roster/members, PATCH /roster/members/{id}/reconcile, and GET /roster/attributions."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        db_factory = ctx.session_factory
        user = register_and_login_user(
            client,
            email="manager@example.com",
            full_name="Project Manager",
        )

        org_res = client.post(
            "/api/v1/organisations",
            headers=user.headers,
            json={"name": "Manager Org", "slug": f"manager-org-{uuid.uuid4().hex[:6]}"},
        )
        org_id = org_res.json()["id"]

        proj_res = client.post(
            f"/api/v1/organisations/{org_id}/projects",
            headers=user.headers,
            json={"name": "Roster API Project", "slug": f"roster-api-{uuid.uuid4().hex[:6]}"},
        )
        project_id = proj_res.json()["id"]

        # Seed member and attribution
        member_id = uuid.uuid4()
        with db_factory() as db:
            doc_ev = EvidenceItem(
                id=uuid.uuid4(),
                organisation_id=uuid.UUID(org_id),
                project_id=uuid.UUID(project_id),
                source_type="document_upload",
                category="team_roster",
                title="Roster Document",
                source_external_id="roster-api-001",
                content_hash="e" * 64,
            )
            commit_ev = EvidenceItem(
                id=uuid.uuid4(),
                organisation_id=uuid.UUID(org_id),
                project_id=uuid.UUID(project_id),
                source_type="github",
                category="commit",
                title="feat(frontend): add navigation menu",
                source_external_id="commit-api-001",
                content_hash="f" * 64,
                source_author_identity="bob-eng",
            )
            db.add_all([doc_ev, commit_ev])
            db.commit()

            m = TeamRosterMember(
                id=member_id,
                project_id=uuid.UUID(project_id),
                evidence_item_id=doc_ev.id,
                full_name="Bob Engineer",
                email="bob@example.com",
                role_name="Senior Frontend Engineer",
                primary_responsibilities=["React components"],
                component_ownership=["frontend"],
                github_username="bob-eng",
                reconciliation_status=ReconciliationStatus.NEW_CANDIDATE.value,
            )
            db.add(m)
            db.commit()

            attr = ContributionAttribution(
                id=uuid.uuid4(),
                project_id=uuid.UUID(project_id),
                evidence_item_id=commit_ev.id,
                contributor_identifier="bob-eng",
                identifier_type="github_username",
                matched_roster_member_id=member_id,
                match_method=IdentityMatchMethod.EXACT_GITHUB_USERNAME.value,
                match_confidence=1.0,
                contribution_category=ContributionCategory.FRONTEND_DEVELOPMENT.value,
                responsibility_alignment=ResponsibilityAlignment.ALIGNED.value,
                alignment_explanation="Frontend react commit matching declared role.",
            )
            db.add(attr)
            db.commit()

        # 1. List members
        list_res = client.get(f"/api/v1/projects/{project_id}/roster/members", headers=user.headers)
        assert list_res.status_code == 200
        members_data = list_res.json()
        assert len(members_data) == 1
        assert members_data[0]["full_name"] == "Bob Engineer"
        assert members_data[0]["reconciliation_status"] == ReconciliationStatus.NEW_CANDIDATE.value

        # 2. Reconcile member
        patch_res = client.patch(
            f"/api/v1/projects/{project_id}/roster/members/{member_id}/reconcile",
            headers=user.headers,
            json={
                "reconciliation_status": ReconciliationStatus.MATCHED.value,
                "reconciliation_notes": "Manually confirmed by project manager",
            },
        )
        assert patch_res.status_code == 200
        assert patch_res.json()["reconciliation_status"] == ReconciliationStatus.MATCHED.value

        # 3. List attributions
        attrs_res = client.get(f"/api/v1/projects/{project_id}/roster/attributions", headers=user.headers)
        assert attrs_res.status_code == 200
        attrs_data = attrs_res.json()
        assert len(attrs_data) == 1
        assert attrs_data[0]["contributor_identifier"] == "bob-eng"
        assert attrs_data[0]["responsibility_alignment"] == ResponsibilityAlignment.ALIGNED.value
