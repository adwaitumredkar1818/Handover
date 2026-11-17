"""FastAPI HTTP endpoints for Project Knowledge Assistant (Module 5 / AI Assistant Area).

Provides:
- Project conversation management (creation, history, update, deletion)
- Evidence-grounded natural language question answering
- Multi-domain query classification and entity extraction
- Permission-aware hybrid RAG execution and attribution
- Source citation manifest validation and hallucination checks
- Epistemic uncertainty, conflict detection, and abstention handling
- Response quality feedback and retrieval diagnostic telemetry
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import (
    get_app_settings,
    get_db_session,
    get_hybrid_retrieval_service,
    get_llm_client,
    require_project_permission,
)
from app.core.config import Settings
from app.models.enums import AssistantConversationStatus
from app.schemas.assistant import (
    AssistantAnswerResponse,
    AssistantFeedbackRequest,
    AssistantFeedbackResponse,
    ConversationCreateRequest,
    ConversationDetailResponse,
    ConversationResponse,
    ConversationUpdateRequest,
    QuestionRequest,
    RetrievalDiagnosticsResponse,
)
from app.services.assistant import ProjectKnowledgeAssistantService
from app.services.assistant_llm import AssistantLLMReasoner
from app.services.assistant_retrieval import AssistantRetrievalService
from app.services.ai.orchestrator import ProjectIntelligenceOrchestrator
from app.services.ai.registry import InvestigationRuntimeRegistry
from app.services.ai.state import InvestigationState, InvestigationStatus
from app.services.llm import StructuredLLMClient
from app.services.rbac import ProjectContext
from app.services.retrieval import HybridRetrievalService

router = APIRouter(prefix="/projects/{project_id}/assistant", tags=["Project Knowledge Assistant"])


def _get_assistant_service(
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_app_settings),
    hybrid_service: HybridRetrievalService = Depends(get_hybrid_retrieval_service),
    llm_client: StructuredLLMClient = Depends(get_llm_client),
) -> ProjectKnowledgeAssistantService:
    """Dependency provider assembling the full Project Knowledge Assistant stack."""
    retrieval_svc = AssistantRetrievalService(
        session=session,
        settings=settings,
        hybrid_retrieval_service=hybrid_service,
    )
    llm_reasoner = AssistantLLMReasoner(
        settings=settings,
        llm_client=llm_client,
    )
    return ProjectKnowledgeAssistantService(
        session=session,
        settings=settings,
        retrieval_service=retrieval_svc,
        llm_reasoner=llm_reasoner,
    )


def _get_orchestrator(
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_app_settings),
    hybrid_service: HybridRetrievalService = Depends(get_hybrid_retrieval_service),
    llm_client: StructuredLLMClient = Depends(get_llm_client),
) -> ProjectIntelligenceOrchestrator:
    """Dependency provider assembling the Project Intelligence Orchestrator."""
    retrieval_svc = AssistantRetrievalService(
        session=session,
        settings=settings,
        hybrid_retrieval_service=hybrid_service,
    )
    llm_reasoner = AssistantLLMReasoner(
        settings=settings,
        llm_client=llm_client,
    )
    return ProjectIntelligenceOrchestrator(
        session=session,
        settings=settings,
        retrieval_service=retrieval_svc,
        llm_reasoner=llm_reasoner,
    )


# ---------------------------------------------------------------------------
# Conversation Management Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new assistant conversation",
)
def create_conversation(
    project_id: uuid.UUID,
    payload: ConversationCreateRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("assistant.chat"))],
    assistant_service: Annotated[ProjectKnowledgeAssistantService, Depends(_get_assistant_service)],
) -> ConversationResponse:
    """Create a new private conversation session for the authenticated user."""
    return assistant_service.create_conversation(
        project_ctx=project_ctx,
        title=payload.title,
        metadata_json=payload.metadata_json,
    )


@router.get(
    "/conversations",
    response_model=list[ConversationResponse],
    summary="List caller's conversations in the project",
)
def list_conversations(
    project_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("assistant.read"))],
    assistant_service: Annotated[ProjectKnowledgeAssistantService, Depends(_get_assistant_service)],
    status: AssistantConversationStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[ConversationResponse]:
    """Retrieve all conversations created by the caller in this project."""
    return assistant_service.list_conversations(
        project_ctx=project_ctx,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
    summary="Get conversation detail with message turns and citations",
)
def get_conversation_detail(
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("assistant.read"))],
    assistant_service: Annotated[ProjectKnowledgeAssistantService, Depends(_get_assistant_service)],
) -> ConversationDetailResponse:
    """Retrieve complete message thread, structured payloads, and cited sources."""
    return assistant_service.get_conversation_detail(
        project_ctx=project_ctx,
        conversation_id=conversation_id,
    )


@router.patch(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
    summary="Update conversation title or status",
)
def update_conversation(
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    payload: ConversationUpdateRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("assistant.chat"))],
    assistant_service: Annotated[ProjectKnowledgeAssistantService, Depends(_get_assistant_service)],
) -> ConversationResponse:
    """Update title or archive/activate a conversation."""
    return assistant_service.update_conversation(
        project_ctx=project_ctx,
        conversation_id=conversation_id,
        title=payload.title,
        status=payload.status,
    )


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an assistant conversation",
)
def delete_conversation(
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("assistant.chat"))],
    assistant_service: Annotated[ProjectKnowledgeAssistantService, Depends(_get_assistant_service)],
) -> None:
    """Delete a conversation, associated message history, and citations."""
    assistant_service.delete_conversation(
        project_ctx=project_ctx,
        conversation_id=conversation_id,
    )


# ---------------------------------------------------------------------------
# Question Answering Turn Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=AssistantAnswerResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask a question and receive an evidence-grounded answer",
)
def ask_question(
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    payload: QuestionRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("assistant.chat"))],
    assistant_service: Annotated[ProjectKnowledgeAssistantService, Depends(_get_assistant_service)],
) -> AssistantAnswerResponse:
    """Submit a user prompt, execute permission-aware hybrid RAG, and return cited answer."""
    return assistant_service.ask_question(
        project_ctx=project_ctx,
        conversation_id=conversation_id,
        request=payload,
    )


# ---------------------------------------------------------------------------
# Investigation & Real-Time SSE Streaming Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/conversations/{conversation_id}/investigations",
    status_code=status.HTTP_201_CREATED,
    summary="Create a new investigation and dispatch state graph",
)
async def create_investigation(
    request: Request,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    payload: QuestionRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("assistant.chat"))],
    settings: Annotated[Settings, Depends(get_app_settings)],
    hybrid_service: Annotated[HybridRetrievalService, Depends(get_hybrid_retrieval_service)],
    llm_client: Annotated[StructuredLLMClient, Depends(get_llm_client)],
) -> dict[str, Any]:
    """Start an asynchronous, multi-step investigation session and return its ID."""
    investigation_id = uuid.uuid4()
    state = InvestigationState(
        investigation_id=investigation_id,
        conversation_id=conversation_id,
        project_id=project_id,
        organisation_id=project_ctx.organisation.id,
        user_id=project_ctx.principal.user.id,
        user_role=getattr(getattr(project_ctx.project_membership, "role", None), "name", str(getattr(project_ctx.project_membership, "role", "member"))),
        query=payload.question,
        response_mode=payload.response_mode,
        target_domains=[d.value for d in payload.include_domains] if payload.include_domains else [],
    )

    # Launch state graph execution in the background with a dedicated database session
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        from app.db.session import create_session_factory
        session_factory = create_session_factory(request.app.state.db_engine)

    async def _execute_investigation_in_background() -> None:
        with session_factory() as bg_session:
            bg_retrieval_svc = AssistantRetrievalService(
                session=bg_session,
                settings=settings,
                hybrid_retrieval_service=hybrid_service,
            )
            bg_llm_reasoner = AssistantLLMReasoner(
                settings=settings,
                llm_client=llm_client,
            )
            bg_orchestrator = ProjectIntelligenceOrchestrator(
                session=bg_session,
                settings=settings,
                retrieval_service=bg_retrieval_svc,
                llm_reasoner=bg_llm_reasoner,
            )
            await bg_orchestrator.run_investigation(state, project_ctx)

    import asyncio
    asyncio.create_task(_execute_investigation_in_background())

    return {
        "investigation_id": str(investigation_id),
        "conversation_id": str(conversation_id),
        "status": "queued",
        "query": payload.question,
        "mode": payload.response_mode.value,
        "events_url": f"/api/v1/projects/{project_id}/assistant/investigations/{investigation_id}/events",
    }


@router.get(
    "/investigations/{investigation_id}/events",
    summary="Subscribe to live investigation progress over Server-Sent Events (SSE)",
)
async def stream_investigation_events(
    project_id: uuid.UUID,
    investigation_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("assistant.read"))],
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """Stream real-time investigation events with automatic Last-Event-ID resumption."""
    registry = InvestigationRuntimeRegistry.get_instance()
    state = registry.get_state(investigation_id)

    async def event_generator():
        since_seq = 0
        all_historical = registry.get_event_history(investigation_id, since_sequence=0)
        latest_seq = max((h.sequence_number for h in all_historical), default=0)

        # Robust cursor validation: distinguish valid, missing, malformed, and future cursors
        if last_event_id is not None:
            if not last_event_id.isdigit():
                # Malformed cursor: emit explicit cursor_reset event and replay from beginning
                yield f"event: cursor_reset\ndata: {{\"error\": \"Malformed Last-Event-ID: {last_event_id}\", \"expected\": \"integer\", \"replaying_from\": 0}}\n\n"
                since_seq = 0
            else:
                parsed_seq = int(last_event_id)
                if parsed_seq > latest_seq and latest_seq > 0:
                    # Future cursor: client claims cursor beyond server state.
                    # Send explicit cursor_error and reset to latest state to prevent silent drop
                    yield f"event: cursor_error\ndata: {{\"error\": \"Cursor {parsed_seq} exceeds latest server sequence {latest_seq}\", \"action\": \"resync\", \"latest_sequence\": {latest_seq}}}\n\n"
                    since_seq = latest_seq
                else:
                    since_seq = parsed_seq

        # 1. Replay historical events
        historical = registry.get_event_history(investigation_id, since_sequence=since_seq)
        for h_event in historical:
            yield h_event.to_sse_format()

        # If already completed or failed, close stream
        latest_state = registry.get_state(investigation_id)
        if latest_state and latest_state.status in {
            InvestigationStatus.COMPLETED,
            InvestigationStatus.FAILED,
            InvestigationStatus.CANCELLED,
        }:
            return

        # 2. Subscribe to live events
        queue = await registry.subscribe(investigation_id)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield event.to_sse_format()
                    if event.event_type in {"investigation_completed", "investigation_failed", "investigation_cancelled"}:
                        break
                except asyncio.TimeoutError:
                    # Send periodic keep-alive comment to keep cloud proxies alive
                    yield ": keep-alive\n\n"
                    # Check terminal state
                    cur_state = registry.get_state(investigation_id)
                    if cur_state and cur_state.status in {
                        InvestigationStatus.COMPLETED,
                        InvestigationStatus.FAILED,
                        InvestigationStatus.CANCELLED,
                    }:
                        break
        finally:
            await registry.unsubscribe(investigation_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/investigations/{investigation_id}",
    summary="Get current state of an investigation",
)
def get_investigation_state(
    project_id: uuid.UUID,
    investigation_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("assistant.read"))],
) -> dict[str, Any]:
    """Inspect current plan, node, and findings of an ongoing or completed investigation."""
    registry = InvestigationRuntimeRegistry.get_instance()
    state = registry.get_state(investigation_id)
    if not state:
        raise NotFoundError("Investigation not found or expired from runtime.", code="INVESTIGATION_NOT_FOUND")

    if state.project_id != project_id:
        raise ForbiddenError("Investigation belongs to another project.", code="FORBIDDEN_INVESTIGATION")

    return state.model_dump()


# ---------------------------------------------------------------------------
# Feedback & Diagnostics Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/messages/{message_id}/feedback",
    response_model=AssistantFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit user feedback for an assistant response turn",
)
def submit_feedback(
    project_id: uuid.UUID,
    message_id: uuid.UUID,
    payload: AssistantFeedbackRequest,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("assistant.feedback"))],
    assistant_service: Annotated[ProjectKnowledgeAssistantService, Depends(_get_assistant_service)],
) -> AssistantFeedbackResponse:
    """Record helpfulness or accuracy feedback on an assistant message."""
    return assistant_service.submit_feedback(
        project_ctx=project_ctx,
        message_id=message_id,
        request=payload,
    )


@router.get(
    "/diagnostics/retrieval/{run_id}",
    response_model=RetrievalDiagnosticsResponse,
    summary="Get audit retrieval telemetry diagnostics",
)
def get_retrieval_diagnostics(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("assistant.read"))],
    assistant_service: Annotated[ProjectKnowledgeAssistantService, Depends(_get_assistant_service)],
) -> RetrievalDiagnosticsResponse:
    """Inspect detailed retrieval telemetry, candidate counts, and query classification."""
    return assistant_service.get_retrieval_diagnostics(
        project_ctx=project_ctx,
        run_id=run_id,
    )
