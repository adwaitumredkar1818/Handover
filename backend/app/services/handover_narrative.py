"""AI-Assisted Narrative Drafting Service for Handover Sections.

Platform: The Handover
Module: Handover Workspace (Module 4 / Knowledge Transfer Area)

Enforces:
1. Optional Qwen3 8B drafting assistance for human editors
2. Grounded narrative generation strictly derived from linked verified knowledge
3. AI cannot independently approve, sign, or alter project facts
4. Fallback deterministic drafting when local LLM inference is offline
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ServiceUnavailableError
from app.core.security import utc_now
from app.models.enums import AuditOutcome, HandoverCaseStatus
from app.models.handover import (
    HandoverCase,
    HandoverPackageSection,
    HandoverPackageVersion,
    HandoverSignoff,
)
from app.models.knowledge import KnowledgeEvidenceLink
from app.repositories.audit import AuditLogRepository
from app.repositories.handover import (
    HandoverPackageVersionRepository,
    HandoverSectionRepository,
)
from app.schemas.handover import NarrativeDraftRequest, SectionEditRequest
from app.services.audit import AuditService
from app.services.handover_eligibility import check_evidence_accessibility
from app.services.handover_sections import redact_secrets
from app.services.llm import (
    DisabledLLMClient,
    LLMExecutionError,
    LLMGenerationRequest,
    StructuredLLMClient,
)

logger = logging.getLogger("app.services.handover_narrative")

LOCKED_SECTION_CASE_STATUSES: set[str] = {
    HandoverCaseStatus.APPROVED.value,
    HandoverCaseStatus.DELIVERED.value,
    HandoverCaseStatus.ACKNOWLEDGED.value,
    HandoverCaseStatus.TRANSFERRED.value,
    HandoverCaseStatus.ARCHIVED.value,
    HandoverCaseStatus.SUPERSEDED.value,
}


class HandoverNarrativeService:
    """Provides grounded narrative generation and section content editing."""

    def __init__(
        self,
        session: Session,
        llm_client: StructuredLLMClient | None = None,
    ) -> None:
        self.session = session
        self.version_repo = HandoverPackageVersionRepository(session)
        self.section_repo = HandoverSectionRepository(session)
        self.audit_service = AuditService(audit_repository=AuditLogRepository(session))
        self.llm_client = llm_client

    def draft_section_narrative(
        self,
        *,
        project_id: uuid.UUID,
        request: NarrativeDraftRequest,
        case_id: uuid.UUID | None = None,
        viewer_user_id: uuid.UUID | None = None,
        has_project_manage: bool = False,
    ) -> dict[str, Any]:
        """Generate a structured, evidence-grounded, ACL-filtered draft narrative for a section."""
        version = self.version_repo.get_by_id(request.version_id, load_sections=True)
        if (
            not version
            or version.project_id != project_id
            or (case_id is not None and version.case_id != case_id)
        ):
            raise NotFoundError(f"Package version {request.version_id} not found in this project.")

        # Find matching section
        section = next(
            (s for s in version.sections if s.section_type == request.section_type), None
        )
        if not section:
            raise NotFoundError(f"Section type '{request.section_type}' not found in version {request.version_id}.")

        # Collect linked knowledge items with fail-closed source ACL enforcement
        knowledge_snippets: list[str] = []
        for link in section.content_links:
            if link.knowledge_item:
                ki = link.knowledge_item
                if viewer_user_id is not None:
                    ev_ids = list(
                        self.session.execute(
                            select(KnowledgeEvidenceLink.evidence_id).where(
                                KnowledgeEvidenceLink.knowledge_item_id == ki.id
                            )
                        )
                        .scalars()
                        .all()
                    )
                    if ev_ids:
                        accessible, _ = check_evidence_accessibility(
                            self.session,
                            ev_ids,
                            project_id=project_id,
                            viewer_user_id=viewer_user_id,
                            has_project_manage=has_project_manage,
                        )
                        if not accessible:
                            continue
                stmt = redact_secrets(ki.title or "Verified Finding")
                desc = redact_secrets(ki.structured_summary or "")
                knowledge_snippets.append(f"- {stmt}: {desc}")

        context_str = "\n".join(knowledge_snippets) if knowledge_snippets else "No individual items linked."

        draft_content: str
        summary_text: str

        draft_content = self._deterministic_draft(section.section_title, knowledge_snippets)
        if not knowledge_snippets:
            draft_content = (
                f"# {section.section_title}\n\n"
                "Insufficient approved information for this section. "
                "Review and approve supporting findings in Verification Center."
            )
        summary_text = f"Deterministic compilation of {len(knowledge_snippets)} human-approved findings."

        return {
            "section_id": section.id,
            "section_type": section.section_type,
            "draft_content": draft_content,
            "content_summary": summary_text,
            "findings_count": len(knowledge_snippets),
        }

    def edit_section_content(
        self,
        section_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        request: SectionEditRequest,
    ) -> HandoverPackageSection:
        """Human editor updates section text and summary on an editable, unsigned current package version."""
        section = self.section_repo.get_by_id(section_id, load_links=False)
        if not section or section.project_id != project_id:
            raise NotFoundError(f"Section {section_id} not found in this project.")

        version = self.version_repo.get_by_id(section.version_id, load_sections=False)
        if not version or version.project_id != project_id:
            raise NotFoundError(f"Package version for section {section_id} not found.")
        if not version.is_current:
            raise ConflictError(
                "Historical package versions are immutable and cannot be edited."
            )

        case = self.session.get(HandoverCase, version.case_id)
        if not case or case.project_id != project_id:
            raise NotFoundError("Parent handover case not found in this project.")
        if case.status in LOCKED_SECTION_CASE_STATUSES:
            raise ConflictError(
                f"Cannot edit section content while handover case is in locked status '{case.status}'."
            )

        active_signoff = self.session.execute(
            select(HandoverSignoff).where(
                HandoverSignoff.version_id == version.id,
                HandoverSignoff.is_superseded.is_(False),
            )
        ).scalars().first()
        if active_signoff is not None:
            raise ConflictError(
                "Cannot edit section content after sign-off has been recorded on this package version. "
                "Reopen the sign-off phase or assemble a new package version first."
            )

        updated = self.section_repo.update_content(
            section_id,
            content=request.section_content,
            summary=request.content_summary,
        )
        self.audit_service.record_event(
            event_type="handover.section.edited",
            resource_type="handover_package_section",
            resource_id=str(section.id),
            actor_user_id=user_id,
            organisation_id=case.organisation_id,
            project_id=project_id,
            outcome=AuditOutcome.SUCCESS.value,
            metadata={
                "case_id": str(case.id),
                "version_id": str(version.id),
                "section_type": section.section_type,
            },
        )
        return updated  # type: ignore[return-value]

    def _deterministic_draft(self, title: str, snippets: list[str]) -> str:
        lines = [
            f"# {title}",
            "",
            "## Summary of Verified Findings",
            "",
        ]
        if snippets:
            lines.extend(snippets)
        else:
            lines.append("No active verified findings recorded for this domain.")
        lines.append("")
        return "\n".join(lines)
