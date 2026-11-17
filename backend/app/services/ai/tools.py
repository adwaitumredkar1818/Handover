"""Deterministic Tool Registry and Secure Execution Sandbox for Project Intelligence."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Callable

from pydantic import BaseModel, Field

from app.core.exceptions import ForbiddenError
from app.services.ai.state import ToolCallRequest, ToolCallResult
from app.services.rbac import ProjectContext

logger = logging.getLogger("app.services.ai.tools")


class ToolDefinition(BaseModel):
    """Specification of an authorized deterministic tool."""

    tool_id: str
    name: str
    description: str
    is_consequential: bool = False
    required_permission: str = "assistant.chat"
    argument_schema: dict[str, Any] = Field(default_factory=dict)


class ToolRegistry:
    """Catalog of approved project tools and execution dispatchers."""

    _tools: dict[str, ToolDefinition] = {}
    _handlers: dict[str, Callable[..., Any]] = {}
    _executed_approvals: set[str] = set()

    @classmethod
    def register_tool(
        cls,
        definition: ToolDefinition,
        handler: Callable[..., Any],
    ) -> None:
        cls._tools[definition.tool_id] = definition
        cls._handlers[definition.tool_id] = handler

    @classmethod
    def get_tool(cls, tool_id: str) -> ToolDefinition | None:
        return cls._tools.get(tool_id)

    @classmethod
    def list_tools(cls) -> list[ToolDefinition]:
        return list(cls._tools.values())

    @classmethod
    def _compute_approval_fingerprint(
        cls,
        *,
        tool_id: str,
        user_id: str,
        project_id: str,
        arguments: dict[str, Any],
    ) -> str:
        """Compute SHA-256 fingerprint binding tool, user, project, and exact arguments."""
        normalized_args = json.dumps(arguments, sort_keys=True, default=str)
        raw = f"{tool_id}:{user_id}:{project_id}:{normalized_args}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    def execute_tool(
        cls,
        *,
        request: ToolCallRequest,
        project_ctx: ProjectContext,
    ) -> ToolCallResult:
        """Execute tool in a secure sandbox strictly enforcing caller's ProjectContext."""
        tool_def = cls.get_tool(request.tool_id)
        if not tool_def:
            return ToolCallResult(
                call_id=request.call_id,
                tool_id=request.tool_id,
                success=False,
                error_message=f"Tool '{request.tool_id}' not found in registry.",
            )

        # 1. RBAC Permission check
        if not project_ctx.has_permission(tool_def.required_permission):
            raise ForbiddenError(
                f"Principal lacks required permission '{tool_def.required_permission}' to execute tool {tool_def.name}.",
                code="TOOL_PERMISSION_DENIED",
            )

        # 2. Human approval check for consequential actions
        if tool_def.is_consequential:
            if request.approved is not True:
                return ToolCallResult(
                    call_id=request.call_id,
                    tool_id=request.tool_id,
                    success=False,
                    error_message="Consequential tool execution requires explicit human approval.",
                )

            # Idempotency check: prevent duplicate execution of the same approved operation
            fingerprint = cls._compute_approval_fingerprint(
                tool_id=request.tool_id,
                user_id=str(project_ctx.principal.user.id),
                project_id=str(project_ctx.project.id),
                arguments=request.arguments,
            )
            if fingerprint in cls._executed_approvals:
                return ToolCallResult(
                    call_id=request.call_id,
                    tool_id=request.tool_id,
                    success=False,
                    error_message="Idempotency gate: This exact approved operation has already been executed.",
                )

        # 3. Dispatch handler under caller's ProjectContext
        handler = cls._handlers.get(request.tool_id)
        if not handler:
            return ToolCallResult(
                call_id=request.call_id,
                tool_id=request.tool_id,
                success=False,
                error_message="Tool handler not implemented.",
            )

        try:
            result = handler(project_ctx=project_ctx, **request.arguments)
            if tool_def.is_consequential:
                fingerprint = cls._compute_approval_fingerprint(
                    tool_id=request.tool_id,
                    user_id=str(project_ctx.principal.user.id),
                    project_id=str(project_ctx.project.id),
                    arguments=request.arguments,
                )
                cls._executed_approvals.add(fingerprint)

            return ToolCallResult(
                call_id=request.call_id,
                tool_id=request.tool_id,
                success=True,
                data=result,
            )
        except Exception as exc:
            logger.exception("Tool execution failed: %s", exc)
            return ToolCallResult(
                call_id=request.call_id,
                tool_id=request.tool_id,
                success=False,
                error_message=str(exc),
            )


# ---------------------------------------------------------------------------
# Default Tool Initializations
# ---------------------------------------------------------------------------


def _dummy_search_knowledge(project_ctx: ProjectContext, query: str = "") -> dict[str, Any]:
    return {"query": query, "project_id": str(project_ctx.project.id), "status": "executed"}


def _dummy_approve_handover_task(project_ctx: ProjectContext, task_id: str = "") -> dict[str, Any]:
    return {"task_id": task_id, "approved_by": project_ctx.principal.user.email, "status": "approved"}


ToolRegistry.register_tool(
    ToolDefinition(
        tool_id="search_knowledge",
        name="Search Knowledge",
        description="Search reconstructed 8-domain project knowledge items.",
        is_consequential=False,
        required_permission="assistant.chat",
    ),
    _dummy_search_knowledge,
)

ToolRegistry.register_tool(
    ToolDefinition(
        tool_id="approve_handover_task",
        name="Approve Handover Task",
        description="Consequential action to mark a handover checklist task as approved.",
        is_consequential=True,
        required_permission="project.manage",
    ),
    _dummy_approve_handover_task,
)
