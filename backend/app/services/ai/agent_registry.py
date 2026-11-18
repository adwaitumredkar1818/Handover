"""Permanent Agent Registry (Option C) for the Project Intelligence Engine.

Maintains immutable, approved logical agent blueprints for dynamic worker instantiation.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("app.services.ai.agent_registry")


class AgentDefinition(BaseModel):
    """Immutable specification for an approved specialized agent."""

    agent_id: str
    name: str
    role: str
    description: str
    version: str = "1.0.0"
    system_instructions: str
    permitted_task_types: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    required_permissions: list[str] = Field(default_factory=list)
    max_iterations: int = 3
    timeout_seconds: float = 30.0


class AgentRegistry:
    """Central repository of approved logical agent specifications."""

    _registry: dict[str, AgentDefinition] = {}

    @classmethod
    def register(cls, agent_def: AgentDefinition) -> None:
        cls._registry[agent_def.agent_id] = agent_def

    @classmethod
    def get(cls, agent_id: str) -> AgentDefinition | None:
        return cls._registry.get(agent_id)

    @classmethod
    def list_all(cls) -> list[AgentDefinition]:
        return list(cls._registry.values())

    @classmethod
    def initialize_defaults(cls) -> None:
        """Register the 10 canonical specialized logical agent definitions."""
        cls.register(
            AgentDefinition(
                agent_id="knowledge_agent",
                name="Knowledge Agent",
                role="Domain Knowledge & Provenance Specialist",
                description="Specializes in retrieving and cross-referencing facts across the 8 project knowledge domains.",
                system_instructions="You are the Knowledge Agent. Synthesize facts strictly grounded in authorized evidence. Cite [S#] tags for all claims.",
                permitted_task_types=["knowledge_synthesis", "domain_query"],
                allowed_tools=["search_knowledge", "retrieve_evidence"],
                required_permissions=["assistant.chat"],
            )
        )
        cls.register(
            AgentDefinition(
                agent_id="engineering_agent",
                name="Engineering Agent",
                role="Software Architecture & Codebase Specialist",
                description="Analyzes code structures, git commits, pull requests, and technical implementation details.",
                system_instructions="You are the Engineering Agent. Investigate software architecture, API patterns, and code provenance.",
                permitted_task_types=["code_analysis", "architecture_review"],
                allowed_tools=["search_codebase", "query_git_history"],
                required_permissions=["assistant.chat"],
            )
        )
        cls.register(
            AgentDefinition(
                agent_id="project_agent",
                name="Project Agent",
                role="Work Progress & Tasks Specialist",
                description="Tracks Jira tickets, milestone progress, completed work, and unfinished project deliverables.",
                system_instructions="You are the Project Agent. Assess milestone status, issue progress, and task ownership.",
                permitted_task_types=["task_tracking", "milestone_audit"],
                allowed_tools=["retrieve_jira_issue", "query_timeline"],
                required_permissions=["assistant.chat"],
            )
        )
        cls.register(
            AgentDefinition(
                agent_id="decision_agent",
                name="Decision Agent",
                role="Architectural Decision Record (ADR) & Rationale Specialist",
                description="Traces historical design decisions, trade-offs, alternatives considered, and consensus rationale.",
                system_instructions="You are the Decision Agent. Identify the why behind project architectural decisions.",
                permitted_task_types=["decision_audit", "tradeoff_analysis"],
                allowed_tools=["search_knowledge", "query_relationships"],
                required_permissions=["assistant.chat"],
            )
        )
        cls.register(
            AgentDefinition(
                agent_id="security_agent",
                name="Security Agent",
                role="Application Security & Permission Auditor",
                description="Audits authentication boundaries, RLS policies, credential encryption, and source ACLs.",
                system_instructions="You are the Security Agent. Inspect access controls, token security, and privilege boundaries.",
                permitted_task_types=["security_audit", "access_check"],
                allowed_tools=["query_access_policies"],
                required_permissions=["assistant.admin"],
            )
        )
        cls.register(
            AgentDefinition(
                agent_id="database_agent",
                name="Database Agent",
                role="Data Model & PostgreSQL Schema Specialist",
                description="Explores schema definitions, migrations, relational foreign keys, and tsvector indexes.",
                system_instructions="You are the Database Agent. Review data models, entity relationships, and table schemas.",
                permitted_task_types=["schema_review"],
                allowed_tools=["search_knowledge"],
                required_permissions=["assistant.chat"],
            )
        )
        cls.register(
            AgentDefinition(
                agent_id="api_agent",
                name="API Agent",
                role="API Contracts & Integration Boundary Specialist",
                description="Examines OpenAPI endpoints, request/response schemas, SSE event frames, and integration webhooks.",
                system_instructions="You are the API Agent. Analyze interface boundaries, data contracts, and protocol definitions.",
                permitted_task_types=["api_audit"],
                allowed_tools=["search_knowledge"],
                required_permissions=["assistant.chat"],
            )
        )
        cls.register(
            AgentDefinition(
                agent_id="infrastructure_agent",
                name="Infrastructure Agent",
                role="DevOps, Docker & Runtime Gateway Specialist",
                description="Inspects Docker Compose configurations, Render deployment topology, and GPU concurrency locks.",
                system_instructions="You are the Infrastructure Agent. Review deployment infrastructure, network isolation, and runtime health.",
                permitted_task_types=["infra_audit"],
                allowed_tools=["query_gateway_health"],
                required_permissions=["assistant.admin"],
            )
        )
        cls.register(
            AgentDefinition(
                agent_id="analysis_agent",
                name="Analysis Agent",
                role="Cross-Source Evidence Corroboration Specialist",
                description="Detects contradictions, discrepancies, and consensus patterns across multi-source evidence.",
                system_instructions="You are the Analysis Agent. Corroborate facts across repositories, tickets, and documents.",
                permitted_task_types=["conflict_detection", "corroboration"],
                allowed_tools=["search_knowledge", "query_relationships"],
                required_permissions=["assistant.chat"],
            )
        )
        cls.register(
            AgentDefinition(
                agent_id="planning_agent",
                name="Planning Agent",
                role="Handover & Transition Plan Architect",
                description="Assembles role-appropriate transition packages, handover checklists, and readiness scores.",
                system_instructions="You are the Planning Agent. Formulate structured handover roadmaps and readiness assessments.",
                permitted_task_types=["handover_planning"],
                allowed_tools=["retrieve_handover_status"],
                required_permissions=["assistant.chat"],
            )
        )


# Initialize registry on load
AgentRegistry.initialize_defaults()
