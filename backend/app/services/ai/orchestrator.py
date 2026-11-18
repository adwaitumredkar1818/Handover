"""Native Typed State Graph Orchestrator for the Project Intelligence Engine."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.enums import (
    AssistantAnswerStatus,
    AssistantResponseMode,
    AssistantSenderType,
    KnowledgeCategory,
)
from app.repositories.assistant import (
    AssistantCitationRepository,
    AssistantConversationRepository,
    AssistantMessageRepository,
    AssistantRetrievalRunRepository,
)
from app.services.ai.agent_factory import DynamicAgentFactory
from app.services.ai.agent_registry import AgentRegistry
from app.services.ai.registry import InvestigationRuntimeRegistry
from app.services.ai.state import (
    AgentFinding,
    InvestigationPlanStep,
    InvestigationState,
    InvestigationStatus,
    PlanStepStatus,
)
from app.services.assistant_llm import AssistantLLMReasoner
from app.services.assistant_query import AssistantQueryClassifier, ClassifiedQuery
from app.services.assistant_retrieval import AssistantRetrievalResult, AssistantRetrievalService
from app.services.assistant_validation import AssistantAnswerValidator, ValidatedAssistantAnswer
from app.services.rbac import ProjectContext

logger = logging.getLogger("app.services.ai.orchestrator")


class ProjectIntelligenceOrchestrator:
    """Coordinates multi-step graph nodes, durable events, and epistemic synthesis."""

    def __init__(
        self,
        *,
        session: Session,
        settings: Settings,
        retrieval_service: AssistantRetrievalService | None = None,
        llm_reasoner: AssistantLLMReasoner | None = None,
        validator: AssistantAnswerValidator | None = None,
        query_classifier: AssistantQueryClassifier | None = None,
        registry: InvestigationRuntimeRegistry | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.retrieval_service = retrieval_service or AssistantRetrievalService(
            session=session,
            settings=settings,
        )
        self.llm_reasoner = llm_reasoner or AssistantLLMReasoner(settings=settings)
        self.validator = validator or AssistantAnswerValidator()
        self.classifier = query_classifier or AssistantQueryClassifier()
        self.registry = registry or InvestigationRuntimeRegistry.get_instance()

        self.conversation_repo = AssistantConversationRepository(session)
        self.message_repo = AssistantMessageRepository(session)
        self.citation_repo = AssistantCitationRepository(session)
        self.retrieval_run_repo = AssistantRetrievalRunRepository(session)

    # -----------------------------------------------------------------------
    # Graph Execution Pipeline
    # -----------------------------------------------------------------------

    async def run_investigation(
        self,
        state: InvestigationState,
        project_ctx: ProjectContext,
    ) -> InvestigationState:
        """Execute the state graph step-by-step with real-time SSE event dispatch."""
        self.registry.register(state)
        await self.registry.emit_event(
            state.investigation_id,
            "investigation_created",
            {"query": state.query, "mode": state.response_mode.value},
        )

        try:
            # Node 1: Intent Classification & Query Planning
            state = await self._node_classify_and_plan(state)
            if state.status == InvestigationStatus.CANCELLED:
                return state

            # Node 2: Multi-Source Permission-Aware Retrieval
            state = await self._node_retrieve(state, project_ctx)
            if state.status == InvestigationStatus.CANCELLED:
                return state

            # Node 2.5: Dynamic Specialized Agent Delegation
            state = await self._node_delegate_agents(state, project_ctx)
            if state.status == InvestigationStatus.CANCELLED:
                return state

            # Node 3: Specialized Reasoning & Synthesis
            state = await self._node_synthesize(state)
            if state.status == InvestigationStatus.CANCELLED:
                return state

            # Node 4: Epistemic Validation & Anti-Hallucination Gate
            state = await self._node_validate(state)

            # Node 5: Persistence to Canonical PostgreSQL
            state = await self._node_persist(state, project_ctx)

            state.status = InvestigationStatus.COMPLETED
            self.registry.update_state(state)

            await self.registry.emit_event(
                state.investigation_id,
                "investigation_completed",
                {
                    "answer_status": state.answer_status.value,
                    "citations_count": len(state.validated_citations),
                },
            )

        except Exception as exc:
            logger.exception("Investigation failed unexpectedly: %s", exc)
            state.status = InvestigationStatus.FAILED
            state.error_message = str(exc)
            self.registry.update_state(state)
            await self.registry.emit_event(
                state.investigation_id,
                "investigation_failed",
                {"error": str(exc)},
            )

        return state

    # -----------------------------------------------------------------------
    # Discrete State Machine Nodes
    # -----------------------------------------------------------------------

    async def _node_classify_and_plan(self, state: InvestigationState) -> InvestigationState:
        """Classify query intent, extract entities, and construct initial investigation plan."""
        state.current_node = "classify_and_plan"
        await self.registry.emit_event(
            state.investigation_id,
            "node_started",
            {"node": state.current_node},
        )

        classified: ClassifiedQuery = self.classifier.classify(state.query)
        state.expanded_queries = classified.expanded_queries
        state.search_keywords = classified.search_keywords
        state.target_domains = [c.value for c in classified.target_categories]

        # Generate observable plan steps based on mode
        steps: list[InvestigationPlanStep] = [
            InvestigationPlanStep(
                step_id="step_1",
                title="Query Analysis & Expansion",
                description="Classified technical entities and formulated subqueries",
                status=PlanStepStatus.COMPLETED,
            ),
            InvestigationPlanStep(
                step_id="step_2",
                title="Multi-Source Evidence Retrieval",
                description="Query ChromaDB vector store, PostgreSQL knowledge items, and timeline",
                status=PlanStepStatus.PENDING,
            ),
            InvestigationPlanStep(
                step_id="step_3",
                title="Evidence Synthesis & Analysis",
                description="Engage Qwen3 8B reasoner to analyze facts and construct findings",
                status=PlanStepStatus.PENDING,
            ),
            InvestigationPlanStep(
                step_id="step_4",
                title="Epistemic Verification & Citation Audit",
                description="Verify grounded citations, check contradictions, and audit claims",
                status=PlanStepStatus.PENDING,
            ),
        ]
        state.plan_steps = steps
        self.registry.update_state(state)

        await self.registry.emit_event(
            state.investigation_id,
            "plan_created",
            {"steps": [s.model_dump() for s in steps]},
        )
        return state

    async def _node_retrieve(
        self,
        state: InvestigationState,
        project_ctx: ProjectContext,
    ) -> InvestigationState:
        """Execute permission-aware hybrid retrieval across expanded queries."""
        state.current_node = "retrieve_evidence"
        self._update_step_status(state, "step_2", PlanStepStatus.RUNNING)

        await self.registry.emit_event(
            state.investigation_id,
            "retrieval_started",
            {"expanded_queries": state.expanded_queries},
        )

        classified = self.classifier.classify(state.query)
        classified.expanded_queries = state.expanded_queries
        classified.search_keywords = state.search_keywords

        retrieval_res: AssistantRetrievalResult = self.retrieval_service.retrieve(
            project_ctx=project_ctx,
            classified_query=classified,
            search_mode="hybrid",
            response_mode=state.response_mode,
            max_citations=12 if state.response_mode == AssistantResponseMode.DEEP_RESEARCH else 8,
        )

        state.evidence_prompt = retrieval_res.evidence_prompt
        state.citations_manifest = retrieval_res.citations_manifest
        self._update_step_status(state, "step_2", PlanStepStatus.COMPLETED)
        self.registry.update_state(state)

        await self.registry.emit_event(
            state.investigation_id,
            "retrieval_progress",
            {
                "candidates_found": retrieval_res.candidates_found,
                "candidates_authorized": retrieval_res.candidates_authorized,
                "citations_count": len(retrieval_res.citations_manifest),
            },
        )

        # Emit discovered evidence items for real-time frontend cards
        for cit in retrieval_res.citations_manifest[:5]:
            await self.registry.emit_event(
                state.investigation_id,
                "evidence_discovered",
                {
                    "citation_label": cit.citation_label,
                    "title": cit.source_title,
                    "provider": cit.source_provider,
                    "excerpt": cit.excerpt[:150],
                },
            )

        return state

    async def _node_delegate_agents(
        self,
        state: InvestigationState,
        project_ctx: ProjectContext,
    ) -> InvestigationState:
        """Dynamically instantiate and dispatch approved specialized agents based on query scope.
        
        Supports bounded multi-agent collaboration (max 2 agents) executed sequentially
        to respect the single-GPU concurrency semaphore on RTX 4050 6GB VRAM.
        """
        state.current_node = "delegate_agents"
        self.registry.update_state(state)

        # Policy-based multi-agent selection based on query facets
        query_lower = state.query.lower()
        candidate_agent_ids: list[str] = []

        if any(w in query_lower for w in ("architecture", "adr", "decision", "choice", "design")):
            candidate_agent_ids.append("decision_agent")
        if any(w in query_lower for w in ("code", "commit", "pr", "pull request", "git", "function", "diff")):
            candidate_agent_ids.append("engineering_agent")
        if any(w in query_lower for w in ("database", "table", "schema", "postgres", "sql", "migration", "column")):
            candidate_agent_ids.append("database_agent")
        if any(w in query_lower for w in ("api", "endpoint", "route", "openapi", "rest")):
            candidate_agent_ids.append("api_agent")
        if any(w in query_lower for w in ("handover", "transition", "checklist", "readiness")):
            candidate_agent_ids.append("planning_agent")

        # Fallback to knowledge_agent if no specific domain triggered
        if not candidate_agent_ids:
            candidate_agent_ids.append("knowledge_agent")

        # Enforce bounded execution (max 2 agents) to preserve token budget & latency
        selected_agent_ids = candidate_agent_ids[:2]

        for target_agent_id in selected_agent_ids:
            agent_def = AgentRegistry.get(target_agent_id)
            if not agent_def:
                continue

            # Emit agent_selected event
            await self.registry.emit_event(
                state.investigation_id,
                "agent_selected",
                {
                    "agent_id": agent_def.agent_id,
                    "agent_name": agent_def.name,
                    "role": agent_def.role,
                },
            )

            try:
                # Dynamically instantiate worker bound to caller's ProjectContext
                worker = DynamicAgentFactory.create_worker(
                    agent_id=agent_def.agent_id,
                    project_ctx=project_ctx,
                )

                await self.registry.emit_event(
                    state.investigation_id,
                    "agent_started",
                    {"worker_id": worker.worker_id, "agent_id": agent_def.agent_id},
                )

                # Execute bounded subtask using retrieved evidence context
                evidence_summary = (
                    state.evidence_prompt[:400]
                    if state.evidence_prompt
                    else "No prior evidence chunks retrieved."
                )
                finding: AgentFinding = worker.execute_task(
                    task_description=f"Analyze {agent_def.role} findings for query: {state.query[:80]}",
                    evidence_context=evidence_summary,
                )

                # Link discovered citation labels if any exist
                if state.citations_manifest:
                    finding.supporting_citations = [state.citations_manifest[0].citation_label]

                state.agent_findings.append(finding)
                self.registry.update_state(state)

                await self.registry.emit_event(
                    state.investigation_id,
                    "agent_completed",
                    {
                        "worker_id": worker.worker_id,
                        "agent_id": agent_def.agent_id,
                        "claim_text": finding.claim_text,
                        "confidence": finding.confidence,
                    },
                )

                await self.registry.emit_event(
                    state.investigation_id,
                    "agent_findings_accepted",
                    {"finding_id": finding.finding_id, "agent_id": agent_def.agent_id},
                )
            except Exception as exc:
                logger.warning("Agent worker '%s' execution failed non-fatally: %s", target_agent_id, exc)
                await self.registry.emit_event(
                    state.investigation_id,
                    "agent_failed",
                    {"agent_id": target_agent_id, "error": str(exc)},
                )

        return state

    async def _node_synthesize(self, state: InvestigationState) -> InvestigationState:
        """Call structured Qwen3 8B reasoner to synthesize evidence and produce findings."""
        state.current_node = "synthesize_findings"
        self._update_step_status(state, "step_3", PlanStepStatus.RUNNING)

        await self.registry.emit_event(
            state.investigation_id,
            "synthesis_started",
            {"mode": state.response_mode.value},
        )

        available_labels = [c.citation_label for c in state.citations_manifest]
        
        # Integrate dynamic agent findings into synthesis prompt context
        combined_evidence = state.evidence_prompt or ""
        if state.agent_findings:
            agent_summary_lines = ["\n\n--- SPECIALIZED AGENT FINDINGS ---"]
            for f in state.agent_findings:
                agent_summary_lines.append(f"[{f.agent_id}]: {f.claim_text}")
            combined_evidence += "\n".join(agent_summary_lines)

        payload, telemetry = self.llm_reasoner.generate_answer(
            question=state.query,
            evidence_prompt=combined_evidence,
            response_mode=state.response_mode,
            available_citation_labels=available_labels,
        )

        state.raw_answer = payload.answer
        state.answer_status = payload.answer_status
        state.claims = payload.claims
        state.uncertainty = payload.uncertainty
        state.conflicts = payload.conflicts
        state.missing_information = payload.missing_information
        state.suggested_followups = payload.suggested_followup_questions
        state.research_report = payload.research_report
        state.deep_think = payload.deep_think
        state.deep_extract = payload.deep_extract
        state.tokens_consumed = telemetry.get("completion_tokens", 0)

        self._update_step_status(state, "step_3", PlanStepStatus.COMPLETED)
        self.registry.update_state(state)

        # Emit incremental text delta frames for live UI display
        words = payload.answer.split(" ")
        chunk_size = 10
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i : i + chunk_size]) + " "
            await self.registry.emit_event(
                state.investigation_id,
                "token_delta",
                {"delta": chunk},
            )
            # Brief yield to simulate streaming cadence without blocking
            await asyncio.sleep(0.01)

        return state

    async def _node_validate(self, state: InvestigationState) -> InvestigationState:
        """Audit citations, verify claims, and validate epistemic status."""
        state.current_node = "validate_claims"
        self._update_step_status(state, "step_4", PlanStepStatus.RUNNING)

        from app.schemas.assistant import AssistantAnswerPayload

        payload = AssistantAnswerPayload(
            answer=state.raw_answer,
            answer_status=state.answer_status,
            response_mode=state.response_mode,
            claims=state.claims,
            uncertainty=state.uncertainty,
            conflicts=state.conflicts,
            missing_information=state.missing_information,
            suggested_followup_questions=state.suggested_followups,
            research_report=state.research_report,
            deep_think=state.deep_think,
            deep_extract=state.deep_extract,
        )

        validated: ValidatedAssistantAnswer = self.validator.validate(
            payload=payload,
            citations_manifest=state.citations_manifest,
        )

        state.raw_answer = validated.answer
        state.answer_status = validated.answer_status
        state.claims = validated.claims
        state.validated_citations = validated.validated_citations
        state.uncertainty = validated.uncertainty
        state.conflicts = validated.conflicts
        state.missing_information = validated.missing_information

        self._update_step_status(state, "step_4", PlanStepStatus.COMPLETED)
        self.registry.update_state(state)

        await self.registry.emit_event(
            state.investigation_id,
            "final_answer",
            {
                "answer": validated.answer,
                "answer_status": validated.answer_status.value,
                "claims_count": len(validated.claims),
                "citations": [c.model_dump() for c in validated.validated_citations],
                "uncertainty": validated.uncertainty,
                "conflicts": validated.conflicts,
                "missing_information": validated.missing_information,
                "research_report": validated.research_report.model_dump() if validated.research_report else None,
                "deep_think": validated.deep_think.model_dump() if validated.deep_think else None,
                "deep_extract": validated.deep_extract.model_dump() if validated.deep_extract else None,
            },
        )
        return state

    async def _node_persist(
        self,
        state: InvestigationState,
        project_ctx: ProjectContext,
    ) -> InvestigationState:
        """Persist user turn, assistant message, citations, and investigation trace."""
        # Persist Assistant Message Turn
        structured_payload = {
            "investigation_id": str(state.investigation_id),
            "response_mode": state.response_mode.value,
            "plan_steps": [s.model_dump() for s in state.plan_steps],
            "claims": [c.model_dump() for c in state.claims],
            "uncertainty": state.uncertainty,
            "conflicts": state.conflicts,
            "missing_information": state.missing_information,
            "suggested_followup_questions": state.suggested_followups,
            "research_report": state.research_report.model_dump() if state.research_report else None,
            "deep_think": state.deep_think.model_dump() if state.deep_think else None,
            "deep_extract": state.deep_extract.model_dump() if state.deep_extract else None,
        }

        assistant_message = self.message_repo.create(
            conversation_id=state.conversation_id,
            organisation_id=project_ctx.organisation.id,
            project_id=project_ctx.project.id,
            sender_type=AssistantSenderType.ASSISTANT,
            content=state.raw_answer,
            answer_status=state.answer_status,
            structured_payload_json=structured_payload,
            model_name="qwen3:8b",
            completion_tokens=state.tokens_consumed,
        )

        # Persist Citations
        citations_to_persist = []
        for order, cit in enumerate(state.validated_citations, start=1):
            citations_to_persist.append(
                {
                    "message_id": assistant_message.id,
                    "organisation_id": project_ctx.organisation.id,
                    "project_id": project_ctx.project.id,
                    "citation_label": cit.citation_label,
                    "citation_order": order,
                    "evidence_id": cit.evidence_id,
                    "chunk_id": cit.chunk_id,
                    "knowledge_item_id": cit.knowledge_item_id,
                    "source_title": cit.source_title,
                    "source_provider": cit.source_provider,
                    "source_url": cit.source_url,
                    "section_title": cit.section_title,
                    "page_number": cit.page_number,
                    "excerpt": cit.excerpt,
                    "is_verified": cit.is_verified,
                }
            )

        self.citation_repo.create_batch(citations_to_persist)
        self.conversation_repo.touch_last_message(state.conversation_id)
        return state

    def _update_step_status(
        self,
        state: InvestigationState,
        step_id: str,
        status: PlanStepStatus,
    ) -> None:
        for s in state.plan_steps:
            if s.step_id == step_id:
                s.status = status
                break
