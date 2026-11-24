"""Pydantic v2 schemas for Project Knowledge Assistant APIs.

Platform: The Handover
Module: Project Knowledge Assistant (Module 5 / AI Assistant Area)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    AssistantAnswerStatus,
    AssistantConversationStatus,
    AssistantFeedbackType,
    AssistantQueryType,
    AssistantResponseMode,
    AssistantSenderType,
    KnowledgeCategory,
)


# ---------------------------------------------------------------------------
# Conversation Schemas
# ---------------------------------------------------------------------------


class ConversationCreateRequest(BaseModel):
    """Create a new assistant conversation in a project."""

    title: str | None = Field(None, max_length=255, description="Optional custom title for the conversation")
    metadata_json: dict[str, Any] | None = Field(default=None, description="Optional conversation metadata")


class ConversationUpdateRequest(BaseModel):
    """Update an existing assistant conversation."""

    title: str | None = Field(None, min_length=1, max_length=255)
    status: AssistantConversationStatus | None = None
    metadata_json: dict[str, Any] | None = None


class ConversationResponse(BaseModel):
    """Conversation summary metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organisation_id: uuid.UUID
    project_id: uuid.UUID
    created_by_user_id: uuid.UUID
    title: str
    status: AssistantConversationStatus
    metadata_json: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None = None


# ---------------------------------------------------------------------------
# Citation & Claim Schemas
# ---------------------------------------------------------------------------


class FactualClaim(BaseModel):
    """A single factual claim extracted from an answer with supporting citation labels."""

    claim_text: str = Field(..., description="The factual statement made in the answer")
    citation_labels: list[str] = Field(default_factory=list, description="Referenced citation labels e.g. ['S1', 'S2']")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score for this claim")


class AssistantCitationResponse(BaseModel):
    """Full attribution metadata for an evidence citation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    citation_label: str = Field(..., description="Stable citation reference tag e.g. S1, S2")
    evidence_id: uuid.UUID
    chunk_id: uuid.UUID | None = None
    knowledge_item_id: uuid.UUID | None = None
    source_title: str
    source_provider: str
    source_url: str | None = None
    source_external_id: str | None = None
    author: str | None = None
    source_timestamp: datetime | None = None
    page_number: int | None = None
    section_title: str | None = None
    excerpt: str
    is_verified: bool = False


# ---------------------------------------------------------------------------
# Mode-Specific Structured Payloads (Deep Research, Deep Think, Deep Extract)
# ---------------------------------------------------------------------------


class ResearchReportSection(BaseModel):
    """A major topical section in a Deep Research report."""

    section_title: str
    content: str
    citation_labels: list[str] = Field(default_factory=list)
    key_takeaways: list[str] = Field(default_factory=list)


class ResearchReportPayload(BaseModel):
    """Comprehensive multi-section synthesis produced in DEEP RESEARCH mode."""

    executive_summary: str
    sections: list[ResearchReportSection] = Field(default_factory=list)
    cross_source_corroboration: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    coverage_assessment: str | None = None


class CausalStep(BaseModel):
    """A single link in a causal or dependency chain produced in DEEP THINK mode."""

    step_number: int
    event_or_decision: str
    actor_or_source: str | None = None
    consequences: list[str] = Field(default_factory=list)
    citation_labels: list[str] = Field(default_factory=list)


class DeepThinkPayload(BaseModel):
    """Causal, multi-hop, and counterfactual analysis produced in DEEP THINK mode."""

    core_hypothesis: str
    causal_chain: list[CausalStep] = Field(default_factory=list)
    alternative_explanations: list[str] = Field(default_factory=list)
    tradeoffs_and_risks: list[str] = Field(default_factory=list)
    synthesis_reasoning: str


class ExtractedRecord(BaseModel):
    """A structured entity record with field-level provenance in DEEP EXTRACT mode."""

    entity_name: str
    category: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    field_citations: dict[str, list[str]] = Field(default_factory=dict)
    status_or_state: str | None = None


class DeepExtractPayload(BaseModel):
    """Structured entity and tabular extraction produced in DEEP EXTRACT mode."""

    target_schema: str
    columns: list[str] = Field(default_factory=list)
    records: list[ExtractedRecord] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    summary: str


# ---------------------------------------------------------------------------
# Message & Q&A Schemas
# ---------------------------------------------------------------------------


class QuestionRequest(BaseModel):
    """User prompt / question submitted to the assistant."""

    question: str = Field(..., min_length=2, max_length=10000, description="The user's natural language question")
    mode: str = Field(default="hybrid", description="Retrieval mode: hybrid, keyword, semantic")
    response_mode: AssistantResponseMode = Field(
        default=AssistantResponseMode.STANDARD,
        description="Response reasoning mode: standard, deep_research, deep_think, deep_extract",
    )
    include_domains: list[KnowledgeCategory] | None = Field(
        default=None,
        description="Optional filter to restrict retrieval to specific Knowledge Intelligence domains",
    )
    max_citations: int = Field(default=8, ge=1, le=25, description="Maximum number of evidence citations to include")
    handover_case_id: uuid.UUID | None = Field(
        default=None,
        description="Optional handover case UUID to ground the answer with approved/published handover sections and evidence",
    )
    package_version_id: uuid.UUID | None = Field(
        default=None,
        description="Optional handover package version UUID to target a specific snapshot",
    )
    current_section: str | None = Field(
        default=None,
        max_length=120,
        description="Optional current handover section key or domain focus",
    )


class AssistantAnswerPayload(BaseModel):
    """Structured LLM output payload produced by Qwen3 8B."""

    answer: str = Field(..., description="Evidence-grounded comprehensive answer with [S#] citations")
    answer_status: AssistantAnswerStatus = Field(
        default=AssistantAnswerStatus.ANSWERED,
        description="Epistemic status of the answer",
    )
    response_mode: AssistantResponseMode = Field(
        default=AssistantResponseMode.STANDARD,
        description="Active response mode",
    )
    claims: list[FactualClaim] = Field(default_factory=list, description="Atomic factual claims making up the answer")
    uncertainty: str | None = Field(default=None, description="Explicit uncertainty statement if evidence is partial")
    conflicts: list[str] = Field(default_factory=list, description="Conflicting facts or inconsistencies across sources")
    missing_information: list[str] = Field(default_factory=list, description="Missing context or unconfirmed details")
    suggested_followup_questions: list[str] = Field(
        default_factory=list,
        description="Relevant follow-up questions to help the user dive deeper",
    )
    research_report: ResearchReportPayload | None = Field(
        default=None,
        description="Structured report generated in DEEP RESEARCH mode",
    )
    deep_think: DeepThinkPayload | None = Field(
        default=None,
        description="Causal analysis generated in DEEP THINK mode",
    )
    deep_extract: DeepExtractPayload | None = Field(
        default=None,
        description="Structured table/records generated in DEEP EXTRACT mode",
    )


class AssistantAnswerResponse(BaseModel):
    """Response returned upon successfully answering a question."""

    message_id: uuid.UUID
    conversation_id: uuid.UUID
    answer: str
    answer_status: AssistantAnswerStatus
    response_mode: AssistantResponseMode = AssistantResponseMode.STANDARD
    query_type: AssistantQueryType
    claims: list[FactualClaim] = Field(default_factory=list)
    citations: list[AssistantCitationResponse] = Field(default_factory=list)
    uncertainty: str | None = None
    conflicts: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    suggested_followup_questions: list[str] = Field(default_factory=list)
    research_report: ResearchReportPayload | None = None
    deep_think: DeepThinkPayload | None = None
    deep_extract: DeepExtractPayload | None = None
    model_name: str
    retrieval_run_id: uuid.UUID | None = None
    duration_ms: int = 0
    created_at: datetime


class AssistantMessageResponse(BaseModel):
    """Single message in a conversation thread."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_type: AssistantSenderType
    content: str
    answer_status: AssistantAnswerStatus | None = None
    structured_payload_json: dict[str, Any] | None = None
    citations: list[AssistantCitationResponse] = Field(default_factory=list)
    model_name: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    duration_ms: int | None = None
    retrieval_run_id: uuid.UUID | None = None
    created_at: datetime


class ConversationDetailResponse(BaseModel):
    """Full conversation history including ordered messages and their citations."""

    conversation: ConversationResponse
    messages: list[AssistantMessageResponse]


# ---------------------------------------------------------------------------
# Feedback & Telemetry Schemas
# ---------------------------------------------------------------------------


class AssistantFeedbackRequest(BaseModel):
    """Submit user feedback for an assistant response."""

    feedback_type: AssistantFeedbackType
    comment: str | None = Field(default=None, max_length=2000)


class AssistantFeedbackResponse(BaseModel):
    """Recorded feedback record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    message_id: uuid.UUID
    user_id: uuid.UUID
    feedback_type: AssistantFeedbackType
    comment: str | None = None
    created_at: datetime


class RetrievalDiagnosticsResponse(BaseModel):
    """Audit diagnostics for an assistant retrieval run."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    user_id: uuid.UUID
    query_text: str
    query_type: str
    retrieval_mode: str
    candidates_found: int
    candidates_authorized: int
    duration_ms: int
    diagnostics_json: dict[str, Any]
    created_at: datetime
