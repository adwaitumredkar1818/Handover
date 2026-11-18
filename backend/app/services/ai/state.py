"""Typed models and state container for the Handover Project Intelligence Engine."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import AssistantAnswerStatus, AssistantResponseMode
from app.schemas.assistant import (
    AssistantCitationResponse,
    DeepExtractPayload,
    DeepThinkPayload,
    FactualClaim,
    ResearchReportPayload,
)


class InvestigationStatus(str, enum.Enum):
    """Lifecycle statuses for an investigation session."""

    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_USER = "waiting_for_user"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PlanStepStatus(str, enum.Enum):
    """Status of an individual step in the investigation plan."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class InvestigationPlanStep(BaseModel):
    """An observable step in the investigation plan shown to the user."""

    step_id: str
    title: str
    description: str
    status: PlanStepStatus = PlanStepStatus.PENDING
    assigned_agent: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    output_summary: str | None = None


class AgentFinding(BaseModel):
    """Structured insight or observation produced by a specialized agent."""

    finding_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    agent_name: str
    claim_text: str
    supporting_citations: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    is_contradiction: bool = False
    unresolved_questions: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ToolCallRequest(BaseModel):
    """A tool invocation requested by an agent or the orchestrator."""

    call_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    is_consequential: bool = False
    approval_required: bool = False
    approved: bool | None = None
    rejection_reason: str | None = None


class ToolCallResult(BaseModel):
    """Output generated from an authorized tool execution."""

    call_id: str
    tool_id: str
    success: bool
    data: Any | None = None
    error_message: str | None = None
    execution_duration_ms: int = 0


class InvestigationState(BaseModel):
    """The central typed state container passed through the state graph."""

    investigation_id: uuid.UUID
    conversation_id: uuid.UUID
    project_id: uuid.UUID
    organisation_id: uuid.UUID
    user_id: uuid.UUID
    user_role: str

    # User Request & Execution Mode
    query: str
    response_mode: AssistantResponseMode = AssistantResponseMode.STANDARD
    target_domains: list[str] = Field(default_factory=list)

    # Lifecycle & Graph Execution
    status: InvestigationStatus = InvestigationStatus.CREATED
    current_node: str = "init"
    iteration_count: int = 0
    max_iterations: int = 5
    plan_steps: list[InvestigationPlanStep] = Field(default_factory=list)

    # Telemetry & Budgets
    tokens_consumed: int = 0
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Multi-Source Retrieval Context
    expanded_queries: list[str] = Field(default_factory=list)
    search_keywords: list[str] = Field(default_factory=list)
    evidence_prompt: str = ""
    citations_manifest: list[AssistantCitationResponse] = Field(default_factory=list)

    # Findings & Tool States
    agent_findings: list[AgentFinding] = Field(default_factory=list)
    pending_tool_calls: list[ToolCallRequest] = Field(default_factory=list)
    completed_tool_results: list[ToolCallResult] = Field(default_factory=list)

    # Terminal Validated Synthesis
    raw_answer: str = ""
    answer_status: AssistantAnswerStatus = AssistantAnswerStatus.ANSWERED
    claims: list[FactualClaim] = Field(default_factory=list)
    validated_citations: list[AssistantCitationResponse] = Field(default_factory=list)
    uncertainty: str | None = None
    conflicts: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    suggested_followups: list[str] = Field(default_factory=list)

    # Specialized Payloads
    research_report: ResearchReportPayload | None = None
    deep_think: DeepThinkPayload | None = None
    deep_extract: DeepExtractPayload | None = None

    # Error handling
    error_message: str | None = None
