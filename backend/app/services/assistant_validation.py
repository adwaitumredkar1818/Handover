"""Citation Validation and Uncertainty Engine for Project Knowledge Assistant.

Platform: The Handover
Module: Project Knowledge Assistant (Module 5 / AI Assistant Area)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from app.models.enums import AssistantAnswerStatus, AssistantResponseMode
from app.schemas.assistant import (
    AssistantAnswerPayload,
    AssistantCitationResponse,
    DeepExtractPayload,
    DeepThinkPayload,
    FactualClaim,
    ResearchReportPayload,
)

logger = logging.getLogger("app.services.assistant_validation")

_CITATION_LABEL_RE = re.compile(r"\[(S\d+)\]")

# Personal workstation hardware leakage patterns (protected boundary)
_PERSONAL_HARDWARE_RE = re.compile(
    r"\b(?:RTX\s*4050|HP\s*Victus|Victus\b|6GB\s*VRAM|16GB\s*RAM|personal\s+laptop|developer(?:'s)?\s+laptop|my\s+laptop|local\s+workstation|workstation\s+specs)\b",
    re.IGNORECASE,
)
_PERSONAL_FILE_PATH_RE = re.compile(
    r"\b(?:[a-zA-Z]:\\Users\\[a-zA-Z0-9_\-.\\]+|/home/[a-zA-Z0-9_\-./]+)\b",
    re.IGNORECASE,
)

# Secret information patterns requiring mandatory redaction
_SECRET_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
        "[REDACTED_SECRET]",
    ),
    (
        re.compile(r"\beyJ[a-zA-Z0-9_\-]{10,}\.eyJ[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}\b"),
        "[REDACTED_SECRET]",
    ),
    (
        re.compile(r"\b(?:sk|pk)[-_][a-zA-Z0-9_\-]{20,}\b"),
        "[REDACTED_SECRET]",
    ),
    (
        re.compile(r"\bghp_[a-zA-Z0-9]{20,}\b"),
        "[REDACTED_SECRET]",
    ),
    (
        re.compile(r"\bxox[baprs]-[a-zA-Z0-9\-]{20,}\b"),
        "[REDACTED_SECRET]",
    ),
    (
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "[REDACTED_SECRET]",
    ),
    (
        re.compile(
            r"(?i)\b(password|passwd|secret_key|client_secret)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-!@#$%^&*()+=]{6,})['\"]?"
        ),
        r"\1: [REDACTED_SECRET]",
    ),
]


@dataclass
class ValidatedAssistantAnswer:
    """Consolidated answer payload after citation verification, grounding checks, and abstention."""

    answer: str
    answer_status: AssistantAnswerStatus
    claims: list[FactualClaim]
    validated_citations: list[AssistantCitationResponse]
    uncertainty: str | None
    conflicts: list[str]
    missing_information: list[str]
    suggested_followup_questions: list[str]
    response_mode: AssistantResponseMode = AssistantResponseMode.STANDARD
    research_report: ResearchReportPayload | None = None
    deep_think: DeepThinkPayload | None = None
    deep_extract: DeepExtractPayload | None = None



class AssistantAnswerValidator:
    """Validates citations against prompt manifest, enforces grounding, and detects hallucinations."""

    def _redact_secrets(self, text: str) -> str:
        """Scan and redact passwords, API keys, JWT tokens, and private keys."""
        cleaned = text
        for pattern, replacement in _SECRET_PATTERNS:
            cleaned = pattern.sub(replacement, cleaned)
        return cleaned

    def _sanitize_prompt_injections(self, text: str) -> str:
        """Strip internal prompt markers that may have leaked or been mirrored."""
        sanitized = re.sub(r"(?i)CRITICAL INSTRUCTIONS & SAFEGUARDS:.*", "", text, flags=re.DOTALL)
        sanitized = re.sub(r"(?i)SYSTEM PROMPT:.*", "", sanitized, flags=re.DOTALL)
        return sanitized.strip()

    def _sanitize_personal_hardware_leakage(
        self,
        text: str,
        claims: list[FactualClaim],
        citations: list[AssistantCitationResponse],
    ) -> tuple[str, list[FactualClaim], bool]:
        """Detect and scrub personal workstation hardware or file paths from output."""
        has_hw = bool(_PERSONAL_HARDWARE_RE.search(text)) or any(
            _PERSONAL_HARDWARE_RE.search(c.claim_text) for c in claims
        )
        has_paths = bool(_PERSONAL_FILE_PATH_RE.search(text)) or any(
            _PERSONAL_FILE_PATH_RE.search(c.claim_text) for c in claims
        )

        if not (has_hw or has_paths):
            return text, claims, False

        # Verify whether this was explicitly grounded in official project evidence
        is_grounded_in_evidence = any(
            _PERSONAL_HARDWARE_RE.search(cit.excerpt or "")
            or _PERSONAL_HARDWARE_RE.search(cit.source_title or "")
            for cit in citations
        )

        if not is_grounded_in_evidence:
            # If the response is largely an ungrounded workstation disclosure, trigger privacy refusal
            if re.search(r"\b(?:runs\s+on\s+(?:an\s+)?rtx|laptop\s+has|victus\b|16gb\s+ram)\b", text, re.IGNORECASE):
                refusal = (
                    "I'm here to assist with the currently selected Handover project. "
                    "I don't provide personal device or environment information through the Project Knowledge Assistant."
                )
                return refusal, [], True

            # Otherwise, redact specific workstation hardware phrases and local paths
            scrubbed_text = _PERSONAL_HARDWARE_RE.sub("[protected workstation specification]", text)
            scrubbed_text = _PERSONAL_FILE_PATH_RE.sub("[local file path]", scrubbed_text)

            scrubbed_claims = []
            for c in claims:
                c_text = _PERSONAL_HARDWARE_RE.sub("[protected workstation specification]", c.claim_text)
                c_text = _PERSONAL_FILE_PATH_RE.sub("[local file path]", c_text)
                scrubbed_claims.append(
                    FactualClaim(
                        claim_text=c_text,
                        citation_labels=c.citation_labels,
                        confidence=c.confidence,
                    )
                )
            return scrubbed_text, scrubbed_claims, False

        return text, claims, False

    def validate(
        self,
        *,
        payload: AssistantAnswerPayload,
        citations_manifest: list[AssistantCitationResponse],
        is_access_restricted: bool = False,
        active_project_id: Any | None = None,
    ) -> ValidatedAssistantAnswer:
        """Validate LLM output against candidate evidence manifest and fail-closed rules."""
        # 0. Enforce active project isolation on incoming candidate citations
        if active_project_id is not None:
            active_pid_str = str(active_project_id)
            filtered_manifest = []
            for cit in citations_manifest:
                cit_pid = getattr(cit, "project_id", None)
                if cit_pid is None or str(cit_pid) == active_pid_str:
                    filtered_manifest.append(cit)
                else:
                    logger.warning(
                        "Cross-project citation rejected by validator: cit_id=%s cit_project=%s active_project=%s",
                        cit.citation_label,
                        cit_pid,
                        active_pid_str,
                    )
            citations_manifest = filtered_manifest

        manifest_map: dict[str, AssistantCitationResponse] = {
            c.citation_label: c for c in citations_manifest
        }
        valid_labels = set(manifest_map.keys())

        # 1. Mandatory Pre-Sanitization across all exit paths: Redact secrets, injections & personal hardware
        sanitized_input_answer = self._redact_secrets(payload.answer)
        sanitized_input_answer = self._sanitize_prompt_injections(sanitized_input_answer)
        sanitized_input_answer, pre_claims, was_hw_refusal = self._sanitize_personal_hardware_leakage(
            sanitized_input_answer, payload.claims, citations_manifest
        )

        if was_hw_refusal:
            return ValidatedAssistantAnswer(
                answer=sanitized_input_answer,
                answer_status=AssistantAnswerStatus.UNSUPPORTED_QUERY,
                claims=[],
                validated_citations=[],
                uncertainty="Request is outside the active project boundary.",
                conflicts=[],
                missing_information=[],
                suggested_followup_questions=payload.suggested_followup_questions,
                response_mode=payload.response_mode,
            )

        # If user access to the requested scope was blocked/restricted
        if is_access_restricted:
            return ValidatedAssistantAnswer(
                answer=(
                    "Access restricted: You do not possess the required delegated source permissions "
                    "or project access level to retrieve information from the requested repository or source."
                ),
                answer_status=AssistantAnswerStatus.ACCESS_RESTRICTED,
                claims=[],
                validated_citations=[],
                uncertainty="Caller lacks authorized credentials for the target evidence source.",
                conflicts=[],
                missing_information=["Delegated source authorization."],
                suggested_followup_questions=[
                    "Please verify your source connection in Settings -> Connected Sources.",
                ],
            )

        # If no evidence was available
        if not citations_manifest:
            # If the response is a conversational greeting/intro or already answered without claims
            if payload.answer_status == AssistantAnswerStatus.ANSWERED and not payload.claims:
                return ValidatedAssistantAnswer(
                    answer=sanitized_input_answer,
                    answer_status=AssistantAnswerStatus.ANSWERED,
                    claims=[],
                    validated_citations=[],
                    uncertainty=None,
                    conflicts=[],
                    missing_information=[],
                    suggested_followup_questions=payload.suggested_followup_questions,
                    response_mode=payload.response_mode,
                    research_report=payload.research_report,
                    deep_think=payload.deep_think,
                    deep_extract=payload.deep_extract,
                )

            return ValidatedAssistantAnswer(
                answer=sanitized_input_answer,
                answer_status=AssistantAnswerStatus.INSUFFICIENT_EVIDENCE,
                claims=[],
                validated_citations=[],
                uncertainty=payload.uncertainty or "No matching evidence found in current project context.",
                conflicts=payload.conflicts,
                missing_information=payload.missing_information or ["Supporting documentation or source records."],
                suggested_followup_questions=payload.suggested_followup_questions,
                response_mode=payload.response_mode,
                research_report=payload.research_report,
                deep_think=payload.deep_think,
                deep_extract=payload.deep_extract,
            )

        # 1. Extract all citation labels mentioned in answer text
        mentioned_in_text = set(_CITATION_LABEL_RE.findall(payload.answer))

        # 2. Validate claims and their citation labels
        validated_claims: list[FactualClaim] = []
        cited_labels: set[str] = set(mentioned_in_text)

        for claim in payload.claims:
            clean_labels = [lbl for lbl in claim.citation_labels if lbl in valid_labels]
            cited_labels.update(clean_labels)
            # Only keep claim if it has at least one valid supporting citation or status is partial
            if clean_labels or payload.answer_status != AssistantAnswerStatus.ANSWERED:
                validated_claims.append(
                    FactualClaim(
                        claim_text=claim.claim_text,
                        citation_labels=clean_labels,
                        confidence=claim.confidence if clean_labels else 0.5,
                    )
                )

        # 3. Clean up citation tags from visible answer text so it reads as direct clean prose
        cleaned_answer = re.sub(r"\[S\d+\]", "", sanitized_input_answer)
        cleaned_answer = re.sub(r"  +", " ", cleaned_answer).strip()

        # 4. Resolve final validated citations
        # Include all citations that were directly cited, plus any top evidence if none were explicitly tagged
        final_citations: list[AssistantCitationResponse] = []
        if cited_labels.intersection(valid_labels):
            for label in sorted(cited_labels.intersection(valid_labels)):
                final_citations.append(manifest_map[label])
        else:
            # If model didn't cite in text but provided an answer, attach top 2 manifest citations
            final_citations = citations_manifest[:2]

        # 5. Determine resolved epistemic status
        resolved_status = payload.answer_status

        # If model claimed answered, but 0 citations could be validated
        if resolved_status == AssistantAnswerStatus.ANSWERED and not final_citations:
            resolved_status = AssistantAnswerStatus.INSUFFICIENT_EVIDENCE

        # If conflicts are reported
        if payload.conflicts and resolved_status == AssistantAnswerStatus.ANSWERED:
            resolved_status = AssistantAnswerStatus.CONFLICTED_EVIDENCE

        # If missing information is explicitly noted
        if payload.missing_information and resolved_status == AssistantAnswerStatus.ANSWERED:
            resolved_status = AssistantAnswerStatus.PARTIALLY_ANSWERED

        # 6. Apply Strict Disclosure & Anti-Leakage Filters
        cleaned_answer = self._redact_secrets(cleaned_answer)
        cleaned_answer = self._sanitize_prompt_injections(cleaned_answer)
        cleaned_answer, validated_claims, was_hw_refusal = self._sanitize_personal_hardware_leakage(
            cleaned_answer, validated_claims, final_citations
        )
        if was_hw_refusal:
            resolved_status = AssistantAnswerStatus.UNSUPPORTED_QUERY
            final_citations = []
            validated_claims = []

        return ValidatedAssistantAnswer(
            answer=cleaned_answer.strip(),
            answer_status=resolved_status,
            claims=validated_claims,
            validated_citations=final_citations,
            uncertainty=payload.uncertainty if not was_hw_refusal else "Request is outside the active project boundary.",
            conflicts=payload.conflicts if not was_hw_refusal else [],
            missing_information=payload.missing_information if not was_hw_refusal else [],
            suggested_followup_questions=payload.suggested_followup_questions,
            response_mode=payload.response_mode,
            research_report=payload.research_report if not was_hw_refusal else None,
            deep_think=payload.deep_think if not was_hw_refusal else None,
            deep_extract=payload.deep_extract if not was_hw_refusal else None,
        )
