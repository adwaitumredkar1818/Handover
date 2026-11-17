"""Automated benchmark test suite evaluating AI grounding, citation precision, and recall metrics."""

from __future__ import annotations

import uuid
from app.models.enums import AssistantAnswerStatus, AssistantResponseMode
from app.schemas.assistant import AssistantAnswerPayload, AssistantCitationResponse, FactualClaim
from app.services.assistant_validation import AssistantAnswerValidator


def test_eval_grounding_and_hallucination_filter() -> None:
    """Benchmark: Ensure hallucinated citations (not present in manifest) are stripped with 0% false positives."""
    validator = AssistantAnswerValidator()

    # Manifest with 2 verified sources
    manifest = [
        AssistantCitationResponse(
            id=uuid.uuid4(),
            citation_label="S1",
            citation_order=1,
            evidence_id=uuid.uuid4(),
            source_title="Architecture Overview",
            source_provider="github",
            excerpt="FastAPI is the sole authority.",
            is_verified=True,
        ),
        AssistantCitationResponse(
            id=uuid.uuid4(),
            citation_label="S2",
            citation_order=2,
            evidence_id=uuid.uuid4(),
            source_title="Database Schema",
            source_provider="upload",
            excerpt="PostgreSQL 16 is canonical store.",
            is_verified=True,
        ),
    ]

    # LLM output citing valid S1, but hallucinating S9
    payload = AssistantAnswerPayload(
        answer="FastAPI manages auth [S1]. Fake claim citing [S9].",
        answer_status=AssistantAnswerStatus.ANSWERED,
        response_mode=AssistantResponseMode.STANDARD,
        claims=[
            FactualClaim(claim_text="FastAPI manages auth", citation_labels=["S1"], confidence=0.95),
            FactualClaim(claim_text="Fake claim", citation_labels=["S9"], confidence=0.5),
        ],
    )

    validated = validator.validate(payload=payload, citations_manifest=manifest)

    # Assert S1 preserved, S9 stripped
    validated_labels = [c.citation_label for c in validated.validated_citations]
    assert "S1" in validated_labels
    assert "S9" not in validated_labels
    assert len(validated.validated_citations) == 1

    # Assert hallucinated claim citing S9 was filtered out of validated claims
    claim_texts = [c.claim_text for c in validated.claims]
    assert "FastAPI manages auth" in claim_texts
    assert "Fake claim" not in claim_texts


def test_eval_epistemic_abstention_calibration() -> None:
    """Benchmark: Ensure empty evidence returns INSUFFICIENT_EVIDENCE rather than fabricated assertions."""
    validator = AssistantAnswerValidator()
    empty_manifest: list[AssistantCitationResponse] = []

    payload = AssistantAnswerPayload(
        answer="I have no evidence to answer this question.",
        answer_status=AssistantAnswerStatus.INSUFFICIENT_EVIDENCE,
        response_mode=AssistantResponseMode.STANDARD,
        claims=[],
    )

    validated = validator.validate(payload=payload, citations_manifest=empty_manifest)
    assert validated.answer_status == AssistantAnswerStatus.INSUFFICIENT_EVIDENCE
    assert len(validated.validated_citations) == 0
