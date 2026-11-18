"""AI-Assisted Verification Service using local Qwen3 8B.

Platform: The Handover
Module: Verification Center (Module 3 / Validation Area)

MANDATORY SAFEGUARD:
The AI is strictly advisory. It generates semantic explanations of contradictions
and formulates targeted clarification questions.
The AI NEVER approves, rejects, or independently marks any finding as verified.
Workflows are fail-safe: strict 5s timeout and deterministic fallbacks ensure
that verification operations continue seamlessly even if Ollama is unavailable.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.core.config import get_settings
from app.services.llm import LLMExecutionError, LLMGenerationRequest, OllamaLLMClient, StructuredLLMClient

logger = logging.getLogger("app.services.verification_ai")

_EXPLAIN_CONFLICT_PROMPT = """You are an expert project knowledge auditor.
Two pieces of project evidence appear contradictory.
Analyze them objectively and explain the nuance.

Claim A:
"{claim_a}"

Claim B:
"{claim_b}"

Additional Context:
"{context}"

Return a JSON object matching this schema:
{{
  "likely_cause": "<one sentence explaining why these sources diverge>",
  "nuance_explanation": "<concise analytical explanation of the differences>",
  "reconciliation_recommendation": "<suggested action for the human reviewer>",
  "clarification_questions": ["<question 1 to ask the author or team lead>", "<question 2>"]
}}
"""

_SUGGEST_CLARIFICATIONS_PROMPT = """You are an expert handover auditor.
A candidate project knowledge finding has incomplete context or missing rationale.

Finding Title: "{title}"
Finding Domain: "{domain}"
Current Summary: "{summary}"
Missing Context Area: "{missing_context}"

Formulate 2-3 precise, professional clarification questions to ask the departing team member.
Return a JSON object:
{{
  "questions": [
    {{
      "question": "<specific question to clarify rationale, scope, or operational procedure>",
      "purpose": "<why this knowledge is critical for the incoming successor>"
    }}
  ]
}}
"""


def _deterministic_fallback_conflict_explanation(
    claim_a: str,
    claim_b: str,
    context: str = "",
    conflict_type: str = "general",
) -> dict[str, Any]:
    """Deterministic, rule-based conflict explanation when LLM is offline or timed out."""
    norm_a = claim_a.lower()
    norm_b = claim_b.lower()

    # Detect common conflict patterns
    likely_cause = "Temporal or specification divergence between project sources."
    nuance = "Automated AI explanation unavailable; direct raw excerpts should be inspected."
    recommendation = "Review latest source timestamps and confirm canonical direction with team lead."
    questions = [
        "Which source represents the final accepted direction?",
        "Was the older decision or status explicitly superseded?",
    ]

    # Check for status divergence
    if any(w in norm_a for w in ("completed", "done", "closed", "resolved")) and any(
        w in norm_b for w in ("in_progress", "in progress", "blocked", "open", "pending")
    ):
        likely_cause = "Status discrepancy between task tracking and documentation/commit history."
        nuance = f"Claim A asserts the item is completed, while Claim B indicates ongoing or blocked activity."
        recommendation = "Verify live deployment or repository commits to confirm if work is genuinely complete."
        questions = [
            "Has this task been fully deployed to production, or is verification pending?",
            "Are there outstanding subtasks blocking completion?",
        ]
    elif any(w in norm_b for w in ("completed", "done", "closed", "resolved")) and any(
        w in norm_a for w in ("in_progress", "in progress", "blocked", "open", "pending")
    ):
        likely_cause = "Status discrepancy: newer activity marks the item complete while earlier notes show pending."
        nuance = "Claim B appears to reflect a later status update completing the item."
        recommendation = "Accept newer completion status if verified by merge commit or closed ticket."
        questions = ["Confirm if the later source closed this item permanently."]

    # Check for architectural divergence (auth, db, storage)
    elif ("argon2" in norm_a and "supabase" in norm_b) or ("supabase" in norm_a and "argon2" in norm_b):
        likely_cause = "Authentication architecture evolution from local Argon2id hashing to Supabase OAuth."
        nuance = "Earlier specifications planned self-hosted Argon2id sessions, while later implementations adopted Supabase OAuth."
        recommendation = "Confirm whether Supabase OAuth has completely replaced Argon2id or if dual support is retained."
        questions = [
            "Is Argon2id authentication still active anywhere, or was it deprecated in favor of Supabase?",
            "What session validation middleware is used in production?",
        ]
    elif ("sqlite" in norm_a and "postgres" in norm_b) or ("postgres" in norm_a and "sqlite" in norm_b):
        likely_cause = "Database persistence layer migration from SQLite development prototype to PostgreSQL."
        nuance = "One source references SQLite for local development while the other specifies PostgreSQL for deployment."
        recommendation = "Reconcile configuration: designate PostgreSQL as production canonical."
        questions = ["Is SQLite used strictly in local unit tests, with PostgreSQL as the production database?"]

    return {
        "likely_cause": likely_cause,
        "nuance_explanation": nuance,
        "reconciliation_recommendation": recommendation,
        "clarification_questions": questions,
    }


def _deterministic_fallback_clarifications(
    title: str,
    domain: str,
    summary: str,
    missing_context: str,
) -> list[dict[str, str]]:
    """Deterministic, rule-based clarification questions when LLM is offline or timed out."""
    norm_ctx = missing_context.lower()

    if "rationale" in norm_ctx or "decision" in norm_ctx:
        return [
            {
                "question": f"What was the technical and architectural rationale behind choosing '{title}'?",
                "purpose": "Provide incoming engineers with context on why alternatives were discarded.",
            },
            {
                "question": f"Were any benchmarks, trade-offs, or constraints evaluated when deciding '{title}'?",
                "purpose": "Prevent regressions and clarify performance assumptions.",
            },
        ]
    elif "ownership" in norm_ctx or "attribution" in norm_ctx:
        return [
            {
                "question": f"Who is the designated primary owner and fallback maintainer for '{title}'?",
                "purpose": "Ensure operational escalation paths are known to incoming team.",
            },
            {
                "question": f"Which team member approved the architectural direction for '{title}'?",
                "purpose": "Establish governance traceability.",
            },
        ]
    elif "operational" in norm_ctx or "deployment" in norm_ctx or "runbook" in norm_ctx:
        return [
            {
                "question": f"What operational runbook or deployment steps are required to manage '{title}' in production?",
                "purpose": "Ensure zero-downtime maintenance and smooth handover.",
            },
            {
                "question": f"Are there specific monitoring alerts or health check endpoints for '{title}'?",
                "purpose": "Support incident management and proactive monitoring.",
            },
        ]
    elif "dependencies" in norm_ctx:
        return [
            {
                "question": f"What upstream services or downstream packages directly depend on '{title}'?",
                "purpose": "Avoid breaking changes during future refactoring.",
            }
        ]

    return [
        {
            "question": f"Please clarify the background, rationale, and scope for '{title}'.",
            "purpose": "Ensure complete context is captured for the handover.",
        },
        {
            "question": f"Are there any undocumented edge cases or operational gotchas related to '{title}'?",
            "purpose": "Accelerate onboarding and mitigate operational risk.",
        },
    ]


class AIAssistedVerificationService:
    """Provides local LLM-assisted nuance analysis and question suggestion for human reviewers."""

    def __init__(
        self,
        llm_client: StructuredLLMClient | None = None,
        *,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.timeout_seconds = float(timeout_seconds)
        if llm_client is None:
            settings = get_settings()
            model = getattr(settings, "ollama_llm_model", None) or getattr(
                settings, "ollama_model_reconstruction", "qwen3:8b"
            )
            self._client: StructuredLLMClient = OllamaLLMClient(
                base_url=settings.ollama_base_url,
                model=model,
                timeout_seconds=self.timeout_seconds,
            )
        else:
            self._client = llm_client

    def explain_conflict(
        self,
        *,
        claim_a: str,
        claim_b: str,
        context: str = "",
        conflict_type: str = "general",
    ) -> dict[str, Any]:
        """Explain the nuance of contradictory claims between two sources.

        Guaranteed non-blocking: if the advisory LLM fails or times out (5s),
        falls back to deterministic heuristic explanation immediately.
        """
        user_prompt = _EXPLAIN_CONFLICT_PROMPT.format(
            claim_a=claim_a[:1000],
            claim_b=claim_b[:1000],
            context=context[:1000],
        )
        request = LLMGenerationRequest(
            system_prompt=(
                "You are a strict, objective project knowledge verification auditor. "
                "Produce valid JSON only."
            ),
            user_prompt=user_prompt,
            temperature=0.1,
        )

        try:
            result = self._client.generate_json(request)
            parsed = result.parsed_json
            if isinstance(parsed, dict) and "likely_cause" in parsed:
                return parsed
            logger.warning("AI conflict response lacked expected keys, applying fallback.")
            return _deterministic_fallback_conflict_explanation(
                claim_a, claim_b, context, conflict_type
            )
        except Exception as exc:
            logger.warning(
                "AI conflict explanation failed or timed out (%s), applying deterministic fallback.",
                exc,
            )
            return _deterministic_fallback_conflict_explanation(
                claim_a, claim_b, context, conflict_type
            )

    def suggest_clarifications(
        self,
        *,
        title: str,
        domain: str,
        summary: str,
        missing_context: str,
    ) -> list[dict[str, str]]:
        """Formulate targeted clarification questions for incomplete findings.

        Guaranteed non-blocking: falls back to deterministic heuristic questions
        if the advisory LLM fails, times out, or returns malformed data.
        """
        user_prompt = _SUGGEST_CLARIFICATIONS_PROMPT.format(
            title=title[:200],
            domain=domain,
            summary=summary[:1000],
            missing_context=missing_context,
        )
        request = LLMGenerationRequest(
            system_prompt=(
                "You are a strict, objective project knowledge verification auditor. "
                "Produce valid JSON only."
            ),
            user_prompt=user_prompt,
            temperature=0.1,
        )

        try:
            result = self._client.generate_json(request)
            parsed = result.parsed_json
            questions = parsed.get("questions", [])
            if isinstance(questions, list) and len(questions) > 0:
                return questions
            return _deterministic_fallback_clarifications(
                title, domain, summary, missing_context
            )
        except Exception as exc:
            logger.warning(
                "AI clarification generation failed or timed out (%s), applying deterministic fallback.",
                exc,
            )
            return _deterministic_fallback_clarifications(
                title, domain, summary, missing_context
            )
