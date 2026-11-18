"""Integration tests for Advanced RAG and Hybrid Working Memory."""

from __future__ import annotations

import uuid
from app.services.ai.memory import ProjectDerivedMemoryItem, ProjectWorkingMemoryService


def test_working_memory_recording_and_provenance() -> None:
    """Verify that derived working memory preserves evidence provenance and confidence."""
    # Pass None as session since tests use the in-memory cache
    service = ProjectWorkingMemoryService(session=None)  # type: ignore[arg-type]
    project_id = uuid.uuid4()

    item = service.record_derived_insight(
        project_id=project_id,
        topic="Authentication Architecture",
        insight_text="FastAPI JWT with Argon2id is the sole platform identity authority.",
        supporting_citations=["S1", "S2"],
        confidence=0.98,
        is_hypothesis=False,
    )

    assert item.project_id == project_id
    assert item.topic == "Authentication Architecture"
    assert "S1" in item.supporting_citations
    assert item.confidence == 0.98

    # Query memory
    results = service.get_working_memory(project_id, topic="Authentication")
    assert len(results) == 1
    assert results[0].insight_text == item.insight_text
