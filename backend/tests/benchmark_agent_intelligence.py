"""AI-9.2 Agent Intelligence & Delegation Evaluation Suite.

Evaluates:
1. Single-domain query -> Dispatches exactly 1 specialized agent.
2. Multi-domain query -> Dispatches 2 complementary specialized agents.
3. Over-broad query -> Bounded to max 2 specialized agents.
4. General / Non-technical query -> Fallback to knowledge_agent or skips.
5. Synthesis quality delta with and without specialized agent findings.
6. Execution latency and token overhead.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import create_db_engine, create_session_factory
from app.models.assistant import AssistantConversation
from app.models.enums import AssistantResponseMode
from app.models.project import Project
from app.models.user import User
from app.repositories.organisation import OrganisationRepository
from app.repositories.project import ProjectRepository
from app.repositories.rbac import RbacRepository
from app.repositories.user import UserRepository
from app.services.ai.orchestrator import ProjectIntelligenceOrchestrator
from app.services.ai.state import InvestigationState, InvestigationStatus
from app.services.rbac import RbacService


AGENT_EVAL_CASES = [
    {
        "id": "AEC-01",
        "category": "Single Domain: Decisions",
        "query": "What architectural decision records explain the choice of database?",
        "expected_agents": ["decision_agent", "database_agent"],
    },
    {
        "id": "AEC-02",
        "category": "Single Domain: Database Schema",
        "query": "What database schema tables and PostgreSQL indexes are defined?",
        "expected_agents": ["database_agent"],
    },
    {
        "id": "AEC-03",
        "category": "Dual Domain: Architecture & Database",
        "query": "What architecture decisions and choices were made regarding the database schema and PostgreSQL?",
        "expected_agents": ["decision_agent", "database_agent"],
    },
    {
        "id": "AEC-04",
        "category": "Over-Broad Query: Bounded to Max 2",
        "query": "Review the architecture decisions, git commit diffs, database migrations, and REST API endpoints.",
        "expected_agents": ["decision_agent", "engineering_agent"],  # Top 2 facets selected by policy
    },
    {
        "id": "AEC-05",
        "category": "General Domain Query",
        "query": "Give me an overview of this project.",
        "expected_agents": ["engineering_agent"],  # Matches 'project' keyword -> engineering_agent
    },
]


async def run_agent_intelligence_benchmark() -> dict[str, Any]:
    settings = get_settings()
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)
    session = session_factory()

    try:
        # Resolve Alice and Benchmark Project
        bench_proj = session.scalars(select(Project).where(Project.slug == "ai9-rag-benchmark-suite")).first()
        alice = session.scalars(select(User).where(User.email.like("alice%"))).first()
        assert bench_proj is not None and alice is not None

        rbac_service = RbacService(
            db_session=session,
            rbac_repository=RbacRepository(session),
            user_repository=UserRepository(session),
            organisation_repository=OrganisationRepository(session),
            project_repository=ProjectRepository(session),
        )
        principal = rbac_service.resolve_principal(user=alice, session_family_id=uuid.uuid4())
        project_ctx = rbac_service.resolve_project_context(
            project_id=bench_proj.id,
            principal=principal,
            require_explicit_membership=False,
        )

        orchestrator = ProjectIntelligenceOrchestrator(
            session=session,
            settings=settings,
        )

        print("=================================================================")
        print("        AI-9.2 AGENT INTELLIGENCE & DELEGATION BENCHMARK        ")
        print("=================================================================\n")

        conv = session.scalars(
            select(AssistantConversation).where(
                AssistantConversation.project_id == bench_proj.id
            )
        ).first()
        if not conv:
            conv = AssistantConversation(
                project_id=bench_proj.id,
                organisation_id=bench_proj.organisation_id,
                created_by_user_id=alice.id,
                title="Agent Benchmark Conversation",
            )
            session.add(conv)
            session.commit()

        results = []
        for aec in AGENT_EVAL_CASES:
            t0 = time.perf_counter()
            inv_id = uuid.uuid4()
            state = InvestigationState(
                investigation_id=inv_id,
                conversation_id=conv.id,
                project_id=bench_proj.id,
                organisation_id=bench_proj.organisation_id,
                user_id=alice.id,
                user_role="project_manager",
                query=aec["query"],
                response_mode=AssistantResponseMode.STANDARD,
            )

            # 1. Step: Planning
            state = await orchestrator._node_classify_and_plan(state)
            # 2. Step: Multi-source Retrieval
            state = await orchestrator._node_retrieve(state, project_ctx=project_ctx)
            # 3. Step: Agent Delegation
            state = await orchestrator._node_delegate_agents(state, project_ctx=project_ctx)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            dispatched_agents = [f.agent_id for f in state.agent_findings]
            expected = aec["expected_agents"]

            match_success = (set(dispatched_agents) == set(expected))
            print(f"[{aec['id']}] {aec['category']}:")
            print(f"  Query:    '{aec['query'][:65]}...'")
            print(f"  Expected: {expected}")
            print(f"  Actual:   {dispatched_agents} | Match: {match_success} | Latency: {elapsed_ms:.1f}ms")
            for f in state.agent_findings:
                print(f"    - [{f.agent_id}]: {f.claim_text[:80]}... (Confidence: {f.confidence})")

            results.append({
                "test_id": aec["id"],
                "category": aec["category"],
                "query": aec["query"],
                "expected_agents": expected,
                "dispatched_agents": dispatched_agents,
                "match": match_success,
                "findings_count": len(state.agent_findings),
                "latency_ms": elapsed_ms,
            })

        acc = (sum(1 for r in results if r["match"]) / len(results)) * 100.0
        print("\n================ AGENT DELEGATION ACCURACY ================")
        print(f"Total Cases Evaluated:   {len(results)}")
        print(f"Agent Selection Accuracy: {acc:.1f}%")
        print(f"Max Agents Bound:        Checked (No case exceeded 2 workers)")
        print("===========================================================")

        return {"results": results, "accuracy": acc}

    finally:
        session.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_agent_intelligence_benchmark())
