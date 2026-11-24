"""Deterministic Tool Registry and Secure Execution Sandbox for Project Intelligence."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Callable

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.config import get_settings
from app.core.cache.redis_client import RedisConnectionManager
from app.core.exceptions import ForbiddenError
from app.db.session import create_db_engine, create_session_factory
from app.models.audit import AuditLog
from app.models.enums import AuditOutcome
from app.services.ai.state import ToolCallRequest, ToolCallResult
from app.services.rbac import ProjectContext

logger = logging.getLogger("app.services.ai.tools")


class ToolExecutionState:
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


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
    _redis_mgr: RedisConnectionManager | None = None
    _session_factory: Any | None = None

    @classmethod
    def set_session_factory(cls, session_factory: Any) -> None:
        cls._session_factory = session_factory

    @classmethod
    def _get_session_factory(cls) -> Any:
        if cls._session_factory is None:
            try:
                settings = get_settings()
                engine = create_db_engine(settings)
                cls._session_factory = create_session_factory(engine)
            except Exception as exc:
                logger.debug("Failed to initialize DB session factory in ToolRegistry: %s", exc)
        return cls._session_factory

    @classmethod
    def _get_redis(cls):
        if cls._redis_mgr is None:
            try:
                settings = get_settings()
                cls._redis_mgr = RedisConnectionManager(settings)
                cls._redis_mgr.initialize()
            except Exception as exc:
                logger.debug("Redis manager initialization skipped or unavailable: %s", exc)
        if cls._redis_mgr:
            try:
                return cls._redis_mgr.get_client()
            except Exception:
                return None
        return None

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
    def _check_and_claim_pg_idempotency(
        cls,
        *,
        fingerprint: str,
        tool_id: str,
        project_ctx: ProjectContext,
        arguments: dict[str, Any],
    ) -> tuple[bool, str | None]:
        """Atomically claim execution rights in PostgreSQL audit_logs table.
        
        Returns (allowed, error_message).
        """
        session_factory = cls._get_session_factory()
        if not session_factory:
            return True, None

        session = session_factory()
        try:
            # Query existing lifecycle record for this fingerprint
            existing = session.scalars(
                select(AuditLog).where(
                    AuditLog.event_type == "tool.execution.state",
                    AuditLog.resource_id == fingerprint,
                )
            ).first()

            if existing:
                state = existing.event_metadata.get("state") if existing.event_metadata else None
                if state in (ToolExecutionState.EXECUTING, ToolExecutionState.SUCCEEDED):
                    return False, f"Idempotency gate: This exact operation is currently {state}."
                if state == ToolExecutionState.FAILED:
                    # Update to EXECUTING to retry safely
                    existing.outcome = AuditOutcome.SUCCESS.value
                    existing.event_metadata = {
                        "state": ToolExecutionState.EXECUTING,
                        "tool_id": tool_id,
                        "arguments": arguments,
                    }
                    session.commit()
                    return True, None

            # Convert UUIDs safely, handling mocks gracefully
            actor_id = getattr(getattr(getattr(project_ctx, "principal", None), "user", None), "id", None)
            org_id = getattr(getattr(project_ctx, "project", None), "organisation_id", None)
            proj_id = getattr(getattr(project_ctx, "project", None), "id", None)
            
            import uuid
            def _to_uuid(val: Any) -> uuid.UUID | None:
                if isinstance(val, uuid.UUID):
                    return val
                if isinstance(val, str):
                    try:
                        return uuid.UUID(val)
                    except ValueError:
                        return None
                return None

            claim_log = AuditLog(
                actor_user_id=_to_uuid(actor_id),
                organisation_id=_to_uuid(org_id),
                project_id=_to_uuid(proj_id),
                event_type="tool.execution.state",
                resource_type="tool_execution",
                resource_id=fingerprint,
                outcome=AuditOutcome.SUCCESS.value,
                event_metadata={
                    "state": ToolExecutionState.EXECUTING,
                    "tool_id": tool_id,
                    "arguments": arguments,
                },
            )
            session.add(claim_log)
            session.commit()
            return True, None
        except Exception as exc:
            session.rollback()
            logger.warning("PostgreSQL idempotency claim failed or encountered conflict: %s", exc)
            return False, f"Idempotency conflict or database error: {exc}"
        finally:
            session.close()

    @classmethod
    def _update_pg_idempotency_state(
        cls,
        *,
        fingerprint: str,
        state: str,
        result_data: Any | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update terminal execution state in PostgreSQL audit_logs table."""
        session_factory = cls._get_session_factory()
        if not session_factory:
            return

        session = session_factory()
        try:
            existing = session.scalars(
                select(AuditLog).where(
                    AuditLog.event_type == "tool.execution.state",
                    AuditLog.resource_id == fingerprint,
                )
            ).first()
            if existing:
                meta = dict(existing.event_metadata or {})
                meta["state"] = state
                if result_data is not None:
                    meta["result_preview"] = str(result_data)[:200]
                if error_message is not None:
                    meta["error"] = error_message
                existing.event_metadata = meta
                if state == ToolExecutionState.FAILED:
                    existing.outcome = AuditOutcome.ERROR.value
                session.commit()
        except Exception as exc:
            session.rollback()
            logger.warning("Failed to update PostgreSQL idempotency state to %s: %s", state, exc)
        finally:
            session.close()

    @classmethod
    def execute_tool(
        cls,
        *,
        request: ToolCallRequest,
        project_ctx: ProjectContext,
    ) -> ToolCallResult:
        """Execute tool in a secure sandbox strictly enforcing caller's ProjectContext."""
        if not project_ctx or not getattr(project_ctx, "project", None):
            raise ForbiddenError("Missing authorized ProjectContext.", code="PROJECT_CONTEXT_REQUIRED")

        tool_def = cls.get_tool(request.tool_id)
        if not tool_def:
            return ToolCallResult(
                call_id=request.call_id,
                tool_id=request.tool_id,
                success=False,
                error_message=f"Tool '{request.tool_id}' not found in registry.",
            )

        # 0. Strict Project Boundary & Workstation Environment Anti-Inspection
        active_pid_str = str(project_ctx.project.id)
        arg_project_id = request.arguments.get("project_id")
        if arg_project_id is not None and str(arg_project_id) != active_pid_str:
            raise ForbiddenError(
                f"Cross-project tool execution forbidden: active project is {active_pid_str}, attempted {arg_project_id}",
                code="CROSS_PROJECT_TOOL_FORBIDDEN",
            )

        # Check for arbitrary host filesystem inspection in arguments
        for arg_key, arg_val in request.arguments.items():
            if isinstance(arg_val, str):
                import re
                if re.search(r"\b(?:[a-zA-Z]:\\(?:Windows|Users|Program Files)|/(?:etc|proc|sys|root|home))\b", arg_val, re.IGNORECASE):
                    raise ForbiddenError(
                        f"Access to host environment path in argument '{arg_key}' is strictly forbidden.",
                        code="ENV_INSPECTION_FORBIDDEN",
                    )

        # 1. RBAC Permission check
        if not project_ctx.has_permission(tool_def.required_permission):
            raise ForbiddenError(
                f"Principal lacks required permission '{tool_def.required_permission}' to execute tool {tool_def.name}.",
                code="TOOL_PERMISSION_DENIED",
            )

        # 2. Human approval check for consequential actions
        fingerprint: str | None = None
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

            # 1. Distributed Redis lock as immediate atomic fast-path claim across processes
            r = cls._get_redis()
            if r:
                try:
                    # SET with NX=True atomically claims execution rights across distributed workers
                    acquired = r.set(f"tool:idempotency:{fingerprint}", "executing", nx=True, ex=604800)
                    if not acquired:
                        return ToolCallResult(
                            call_id=request.call_id,
                            tool_id=request.tool_id,
                            success=False,
                            error_message="Idempotency gate: This exact approved operation has already been executed or is currently in flight.",
                        )
                except Exception as exc:
                    logger.debug("Redis idempotency check error: %s", exc)

            # 2. Authoritative check & atomic claim in PostgreSQL
            allowed, err_msg = cls._check_and_claim_pg_idempotency(
                fingerprint=fingerprint,
                tool_id=request.tool_id,
                project_ctx=project_ctx,
                arguments=request.arguments,
            )
            if not allowed:
                return ToolCallResult(
                    call_id=request.call_id,
                    tool_id=request.tool_id,
                    success=False,
                    error_message=err_msg or "Idempotency gate: This exact approved operation has already been executed.",
                )

        # 3. Dispatch handler under caller's ProjectContext
        handler = cls._handlers.get(request.tool_id)
        if not handler:
            if tool_def.is_consequential and fingerprint:
                cls._update_pg_idempotency_state(
                    fingerprint=fingerprint,
                    state=ToolExecutionState.FAILED,
                    error_message="Tool handler not implemented.",
                )
            return ToolCallResult(
                call_id=request.call_id,
                tool_id=request.tool_id,
                success=False,
                error_message="Tool handler not implemented.",
            )

        try:
            result = handler(project_ctx=project_ctx, **request.arguments)
            if tool_def.is_consequential and fingerprint:
                cls._executed_approvals.add(fingerprint)
                # Update PostgreSQL authoritative state to SUCCEEDED
                cls._update_pg_idempotency_state(
                    fingerprint=fingerprint,
                    state=ToolExecutionState.SUCCEEDED,
                    result_data=result,
                )
                r = cls._get_redis()
                if r:
                    try:
                        # Distributed lock with 7-day TTL to survive process restarts
                        r.set(f"tool:idempotency:{fingerprint}", "executed", ex=604800)
                    except Exception as exc:
                        logger.warning("Failed to record distributed idempotency key in Redis: %s", exc)

            return ToolCallResult(
                call_id=request.call_id,
                tool_id=request.tool_id,
                success=True,
                data=result,
            )
        except Exception as exc:
            logger.exception("Tool execution failed: %s", exc)
            if tool_def.is_consequential and fingerprint:
                cls._update_pg_idempotency_state(
                    fingerprint=fingerprint,
                    state=ToolExecutionState.FAILED,
                    error_message=str(exc),
                )
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
