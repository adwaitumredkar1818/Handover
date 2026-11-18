"""Tests for RAG grounding accuracy, contributor attribution, and team member identity sync."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.models.enums import ContributorReviewStatus, ContributorType
from app.services.contribution_attribution import (
    ContributionAttributionService,
    classify_contribution_domains,
    is_explicit_rag_evidence,
)
from app.services.extraction_prompts import ChunkPromptInput
from app.services.knowledge_validator import _is_technology_grounded
from app.services.work_grouping import WorkGroupingService


class TestStrictRagGrounding:
    """Verify RAG is never fabricated from unrelated substrings or general AI/storage terms."""

    def test_unrelated_substrings_and_ai_terms_do_not_trigger_rag(self) -> None:
        assert not is_explicit_rag_evidence("backend/app/services/storage.py")
        assert not is_explicit_rag_evidence("coverage_report.json")
        assert not is_explicit_rag_evidence("average_temperature.py")
        assert not is_explicit_rag_evidence("embeddings_service.py")
        assert not is_explicit_rag_evidence("vector_store.py")

        areas_storage, _, _ = classify_contribution_domains(
            "feat: implement local encrypted storage and test coverage",
            paths=["backend/app/services/storage.py", "tests/coverage_check.py"],
        )
        assert "RAG" not in areas_storage

        areas_ai, _, _ = classify_contribution_domains(
            "feat: add Ollama embeddings and vector search helper",
            paths=["backend/app/services/embeddings.py", "backend/app/services/vector_store.py"],
        )
        assert "RAG" not in areas_ai
        assert "AI/ML" in areas_ai or "Database" in areas_ai

    def test_explicit_rag_evidence_is_recognized(self) -> None:
        assert is_explicit_rag_evidence("backend/app/services/rag_pipeline.py")
        assert is_explicit_rag_evidence("Implement retrieval-augmented generation pipeline")

        areas_rag, _, _ = classify_contribution_domains(
            "feat: implement retrieval-augmented generation pipeline",
            paths=["backend/app/services/rag_pipeline.py"],
        )
        assert "RAG" in areas_rag

    def test_validator_rejects_ungrounded_rag_technology_on_storage_text(self) -> None:
        storage_text = "uses local encrypted storage and postgresql database with ollama llm."
        assert not _is_technology_grounded("RAG", storage_text)
        assert not _is_technology_grounded("RAG Pipeline", storage_text)
        assert _is_technology_grounded("PostgreSQL", storage_text)
        assert _is_technology_grounded("Ollama", storage_text)

    def test_validator_accepts_grounded_rag_technology(self) -> None:
        rag_text = "implements a hybrid rag pipeline combining chromadb and postgresql fts."
        assert _is_technology_grounded("RAG", rag_text)
        assert _is_technology_grounded("RAG Pipeline", rag_text)


class TestTeamMemberIdentitySync:
    """Verify project members appear in Relationship Explorer without false verification or authorship."""

    def test_new_member_without_github_shows_pending_identity_and_zero_contributions(self, monkeypatch) -> None:
        pm_id = uuid.uuid4()
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()

        pm = SimpleNamespace(
            id=pm_id,
            user_id=user_id,
            project_id=project_id,
            status="active",
            responsibility_description="Backend Lead",
            user=SimpleNamespace(id=user_id, full_name="Adwait Umredkar", email="adwait@example.com"),
            role=SimpleNamespace(name="project_contributor"),
        )

        class _FakeResult:
            def __init__(self, items):
                self._items = items

            def scalars(self):
                return self

            def all(self):
                return self._items

        calls = {"n": 0}

        class _FakeSession:
            def execute(self, _stmt):
                calls["n"] += 1
                if calls["n"] == 1:
                    return _FakeResult([])  # ContributionAttribution rows
                if calls["n"] == 2:
                    return _FakeResult([pm])  # ProjectMembership rows
                return _FakeResult([])  # UserSourceAuthorisation rows

        service = ContributionAttributionService(_FakeSession())  # type: ignore[arg-type]
        identities = service.list_contributor_identities(
            project_id=project_id,
            accessible_evidence_ids=set(),
            has_project_manage=True,
        )

        assert len(identities) == 1
        entry = identities[0]
        assert entry["display_name"] == "Adwait Umredkar"
        assert entry["contributor_type"] == ContributorType.CONFIRMED_MEMBER.value
        assert entry["contribution_count"] == 0
        assert entry["review_status"] == ContributorReviewStatus.PENDING.value
        assert entry["match_method"] == "pending_identity"

    def test_two_people_same_display_name_without_email_or_handle_are_not_merged(self) -> None:
        pm_id = uuid.uuid4()
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        ev_id = uuid.uuid4()

        pm = SimpleNamespace(
            id=pm_id,
            user_id=user_id,
            project_id=project_id,
            status="active",
            responsibility_description=None,
            user=SimpleNamespace(id=user_id, full_name="Alex Kumar", email="alex.kumar@company.com"),
            role=SimpleNamespace(name="project_member"),
        )
        attr = SimpleNamespace(
            id=uuid.uuid4(),
            project_id=project_id,
            evidence_item_id=ev_id,
            contributor_identifier="alex-oss",
            matched_project_membership_id=None,
            match_method=None,
            match_confidence=0.0,
            contribution_category="Backend Development",
            contributor_type=ContributorType.UNIDENTIFIED.value,
            review_status=ContributorReviewStatus.PENDING.value,
            evidence_item=SimpleNamespace(category="commit", title="feat: api handler"),
            metadata_json={
                "contributor_key": "gh:alex-oss",
                "github_author_login": "alex-oss",
                "git_author_name": "Alex Kumar",
                "git_author_email": "other.alex@external.org",
                "work_areas": ["Backend"],
            },
        )

        class _FakeResult:
            def __init__(self, items):
                self._items = items

            def scalars(self):
                return self

            def all(self):
                return self._items

        calls = {"n": 0}

        class _FakeSession:
            def execute(self, _stmt):
                calls["n"] += 1
                if calls["n"] == 1:
                    return _FakeResult([attr])
                if calls["n"] == 2:
                    return _FakeResult([pm])
                return _FakeResult([])

        service = ContributionAttributionService(_FakeSession())  # type: ignore[arg-type]
        identities = service.list_contributor_identities(
            project_id=project_id,
            accessible_evidence_ids={ev_id},
            has_project_manage=True,
        )

        # Must stay 2 distinct entries and NOT suggest or merge based on display name alone
        assert len(identities) == 2
        ext = next(i for i in identities if i["contributor_key"] == "gh:alex-oss")
        assert ext["matched_project_membership_id"] is None
        assert ext["suggested_project_membership_id"] is None
