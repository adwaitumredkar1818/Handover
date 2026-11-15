"""Unit tests for Advanced Project Knowledge Assistant multi-mode reasoning and retrieval expansion."""

import uuid
from app.models.enums import AssistantAnswerStatus, AssistantQueryType, AssistantResponseMode
from app.schemas.assistant import (
    AssistantAnswerPayload,
    AssistantCitationResponse,
    CausalStep,
    DeepExtractPayload,
    DeepThinkPayload,
    ExtractedRecord,
    FactualClaim,
    QuestionRequest,
    ResearchReportPayload,
    ResearchReportSection,
)
from app.services.assistant_query import AssistantQueryClassifier, ClassifiedQuery
from app.services.assistant_validation import AssistantAnswerValidator


def test_query_expansion():
    classifier = AssistantQueryClassifier()
    classified = classifier.classify("How are citation priorities determined across different evidence types?")
    
    assert classified.raw_query == "How are citation priorities determined across different evidence types?"
    assert len(classified.expanded_queries) >= 2
    # Check that expansion picked up citation/ranking/fusion concepts
    expansions_str = " ".join(classified.expanded_queries).lower()
    assert "citation" in expansions_str or "priority" in expansions_str
    assert "ranking" in expansions_str or "scoring" in expansions_str


def test_query_expansion_auth():
    classifier = AssistantQueryClassifier()
    classified = classifier.classify("What is the platform identity and jwt authentication architecture?")
    expansions_str = " ".join(classified.expanded_queries).lower()
    assert "argon2id" in expansions_str or "session" in expansions_str or "jwt" in expansions_str


def test_validator_preserves_deep_research():
    validator = AssistantAnswerValidator()
    
    cit = AssistantCitationResponse(
        citation_label="S1",
        evidence_id=uuid.uuid4(),
        source_title="Architecture Spec",
        source_provider="document_upload",
        excerpt="Platform uses hybrid retrieval.",
        is_verified=True,
    )
    
    report = ResearchReportPayload(
        executive_summary="Executive summary test",
        sections=[
            ResearchReportSection(
                section_title="Architecture",
                content="Architecture details citing [S1]",
                citation_labels=["S1"],
                key_takeaways=["Hybrid retrieval confirmed"],
            )
        ],
        cross_source_corroboration=["Matches documentation."],
        recommendations=["Continue indexing."],
        coverage_assessment="High",
    )
    
    payload = AssistantAnswerPayload(
        answer="Report text citing [S1]",
        answer_status=AssistantAnswerStatus.ANSWERED,
        response_mode=AssistantResponseMode.DEEP_RESEARCH,
        claims=[
            FactualClaim(claim_text="Platform uses hybrid retrieval.", citation_labels=["S1"], confidence=0.95)
        ],
        research_report=report,
    )
    
    validated = validator.validate(payload=payload, citations_manifest=[cit])
    assert validated.answer_status == AssistantAnswerStatus.ANSWERED
    assert validated.response_mode == AssistantResponseMode.DEEP_RESEARCH
    assert validated.research_report is not None
    assert validated.research_report.executive_summary == "Executive summary test"
    assert len(validated.validated_citations) == 1
    assert validated.validated_citations[0].citation_label == "S1"


def test_validator_preserves_deep_think():
    validator = AssistantAnswerValidator()
    
    cit = AssistantCitationResponse(
        citation_label="S1",
        evidence_id=uuid.uuid4(),
        source_title="Risk Analysis",
        source_provider="github",
        excerpt="VRAM contention on RTX 4050.",
        is_verified=True,
    )
    
    think = DeepThinkPayload(
        core_hypothesis="VRAM contention triggers process kill",
        causal_chain=[
            CausalStep(
                step_number=1,
                event_or_decision="Ollama runs Qwen3 8B and GLM OCR concurrently",
                actor_or_source="S1",
                consequences=["VRAM exceeds 6GB limit"],
                citation_labels=["S1"],
            )
        ],
        alternative_explanations=["Separate GPUs could prevent contention"],
        tradeoffs_and_risks=["Single job scheduler required"],
        synthesis_reasoning="Serial execution avoids swapping",
    )
    
    payload = AssistantAnswerPayload(
        answer="Analysis text citing [S1]",
        answer_status=AssistantAnswerStatus.ANSWERED,
        response_mode=AssistantResponseMode.DEEP_THINK,
        claims=[
            FactualClaim(claim_text="VRAM exceeds limit on concurrent load.", citation_labels=["S1"], confidence=0.9)
        ],
        deep_think=think,
    )
    
    validated = validator.validate(payload=payload, citations_manifest=[cit])
    assert validated.answer_status == AssistantAnswerStatus.ANSWERED
    assert validated.response_mode == AssistantResponseMode.DEEP_THINK
    assert validated.deep_think is not None
    assert len(validated.deep_think.causal_chain) == 1
    assert validated.deep_think.causal_chain[0].step_number == 1


def test_validator_preserves_deep_extract():
    validator = AssistantAnswerValidator()
    
    cit = AssistantCitationResponse(
        citation_label="S1",
        evidence_id=uuid.uuid4(),
        source_title="Components Spec",
        source_provider="document_upload",
        excerpt="Module A belongs to Core.",
        is_verified=True,
    )
    
    extract = DeepExtractPayload(
        target_schema="Core Modules",
        columns=["Module", "Category"],
        records=[
            ExtractedRecord(
                entity_name="Module A",
                category="Core",
                attributes={"Owner": "Platform Team"},
                field_citations={"Owner": ["S1"]},
                status_or_state="Active",
            )
        ],
        missing_fields=[],
        summary="Extracted 1 module",
    )
    
    payload = AssistantAnswerPayload(
        answer="Table text citing [S1]",
        answer_status=AssistantAnswerStatus.ANSWERED,
        response_mode=AssistantResponseMode.DEEP_EXTRACT,
        claims=[
            FactualClaim(claim_text="Module A belongs to Core.", citation_labels=["S1"], confidence=0.9)
        ],
        deep_extract=extract,
    )
    
    validated = validator.validate(payload=payload, citations_manifest=[cit])
    assert validated.answer_status == AssistantAnswerStatus.ANSWERED
    assert validated.response_mode == AssistantResponseMode.DEEP_EXTRACT
    assert validated.deep_extract is not None
    assert len(validated.deep_extract.records) == 1
    assert validated.deep_extract.records[0].entity_name == "Module A"


def test_question_request_schema():
    req = QuestionRequest(
        question="How are citation priorities determined?",
        response_mode=AssistantResponseMode.DEEP_RESEARCH,
    )
    assert req.response_mode == AssistantResponseMode.DEEP_RESEARCH
