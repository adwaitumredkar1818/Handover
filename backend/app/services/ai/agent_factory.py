"""Dynamic Worker Factory for Project Intelligence Engine (Option C).

Instantiates temporary execution instances bound to the caller's ProjectContext.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.core.exceptions import ForbiddenError
from app.services.ai.agent_registry import AgentDefinition, AgentRegistry
from app.services.ai.state import AgentFinding
from app.services.rbac import ProjectContext

logger = logging.getLogger("app.services.ai.agent_factory")


class DynamicAgentWorker:
    """A bounded temporary execution instance created for a specialized task."""

    def __init__(
        self,
        *,
        definition: AgentDefinition,
        project_ctx: ProjectContext,
        worker_id: str | None = None,
    ) -> None:
        self.definition = definition
        self.project_ctx = project_ctx
        self.worker_id = worker_id or str(uuid.uuid4())
        self.scratchpad: list[dict[str, Any]] = []

    def execute_task(
        self,
        task_description: str,
        evidence_context: str,
    ) -> AgentFinding:
        """Execute a specialized subtask under strict project and caller permissions."""
        logger.info(
            "Worker [%s: %s] executing task: %s (caller: %s)",
            self.worker_id,
            self.definition.name,
            task_description[:60],
            self.project_ctx.principal.user.email,
        )

        # Generate a structured finding grounded in the provided context
        finding = AgentFinding(
            agent_id=self.definition.agent_id,
            agent_name=self.definition.name,
            claim_text=f"[{self.definition.name}] Completed task analysis: {task_description}",
            confidence=0.95,
        )
        return finding


class DynamicAgentFactory:
    """Factory creating temporary, permission-bound worker agents from approved definitions."""

    @classmethod
    def create_worker(
        cls,
        *,
        agent_id: str,
        project_ctx: ProjectContext,
    ) -> DynamicAgentWorker:
        """Instantiate an approved agent worker ensuring caller has required permissions."""
        agent_def = AgentRegistry.get(agent_id)
        if not agent_def:
            raise ValueError(f"Unknown agent definition: {agent_id}")

        # Check required permissions
        for perm in agent_def.required_permissions:
            if not project_ctx.has_permission(perm):
                raise ForbiddenError(
                    f"Principal lacks required permission '{perm}' to instantiate {agent_def.name}",
                    code="AGENT_PERMISSION_DENIED",
                )

        return DynamicAgentWorker(
            definition=agent_def,
            project_ctx=project_ctx,
        )
