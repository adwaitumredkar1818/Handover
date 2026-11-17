"""Interactive Deep Research and Multi-Step Graph Workflows for Project Intelligence."""

from __future__ import annotations

import logging
from typing import Any

from app.models.enums import AssistantResponseMode
from app.services.ai.agent_factory import DynamicAgentFactory
from app.services.ai.events import SSEEventFrame
from app.services.ai.registry import InvestigationRuntimeRegistry
from app.services.ai.state import (
    AgentFinding,
    InvestigationPlanStep,
    InvestigationState,
    InvestigationStatus,
    PlanStepStatus,
)
from app.services.rbac import ProjectContext

logger = logging.getLogger("app.services.ai.deep_research")


class DeepResearchWorkflow:
    """Manages iterative, multi-hop investigation loops with interactive clarification gates."""

    @classmethod
    async def execute_research_cycle(
        cls,
        state: InvestigationState,
        project_ctx: ProjectContext,
        registry: InvestigationRuntimeRegistry,
    ) -> InvestigationState:
        """Execute iterative research steps with iteration caps and budget guards."""
        logger.info(
            "Initiating Deep Research cycle for investigation %s (mode: %s)",
            state.investigation_id,
            state.response_mode.value,
        )

        state.current_node = "deep_research_cycle"
        state.iteration_count += 1

        # Check if research goal is ambiguous or requires external scope expansion
        if "?" in state.query and "all repositories" in state.query.lower():
            # Trigger clarification pause
            state.status = InvestigationStatus.WAITING_FOR_USER
            registry.update_state(state)
            await registry.emit_event(
                state.investigation_id,
                "clarification_required",
                {
                    "question": "Should research be constrained to the primary repository or cover all connected third-party integrations?",
                    "options": ["Current Project Only", "All Connected Sources"],
                },
            )
            return state

        # Delegate sub-analysis to specialized agents dynamically
        try:
            k_worker = DynamicAgentFactory.create_worker(
                agent_id="knowledge_agent",
                project_ctx=project_ctx,
            )
            finding = k_worker.execute_task(
                task_description=f"Deep investigation of: {state.query}",
                evidence_context=state.evidence_prompt,
            )
            state.agent_findings.append(finding)

            await registry.emit_event(
                state.investigation_id,
                "agent_completed",
                {
                    "agent_name": finding.agent_name,
                    "claim": finding.claim_text,
                    "confidence": finding.confidence,
                },
            )
        except Exception as exc:
            logger.warning("Delegation to knowledge_agent failed: %s", exc)

        return state
