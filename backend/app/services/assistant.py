"""Project Knowledge Assistant Orchestration Service.

Platform: The Handover
Module: Project Knowledge Assistant (Module 5 / AI Assistant Area)
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import (
    ForbiddenError,
    NotFoundError,
)
from app.models.enums import (
    AssistantAnswerStatus,
    AssistantConversationStatus,
    AssistantQueryType,
    AssistantSenderType,
)
from app.repositories.assistant import (
    AssistantCitationRepository,
    AssistantConversationRepository,
    AssistantFeedbackRepository,
    AssistantMessageRepository,
    AssistantRetrievalRunRepository,
)
from app.schemas.assistant import (
    AssistantAnswerResponse,
    AssistantCitationResponse,
    AssistantFeedbackRequest,
    AssistantFeedbackResponse,
    AssistantMessageResponse,
    ConversationDetailResponse,
    ConversationResponse,
    QuestionRequest,
    RetrievalDiagnosticsResponse,
)
from app.services.assistant_llm import AssistantLLMReasoner
from app.services.assistant_query import AssistantQueryClassifier, ClassifiedQuery
from app.services.assistant_retrieval import AssistantRetrievalResult, AssistantRetrievalService
from app.services.assistant_validation import AssistantAnswerValidator, ValidatedAssistantAnswer
from app.services.handover_case import (
    HandoverCaseService,
    is_unapproved_draft_restricted_for_successor,
)
from app.services.handover_sections import HandoverSectionReadService, redact_secrets
from app.services.rbac import ProjectContext

logger = logging.getLogger("app.services.assistant")


class ProjectKnowledgeAssistantService:
    """Coordinates conversations, query classification, hybrid retrieval, LLM reasoning, and validation."""

    def __init__(
        self,
        *,
        session: Session,
        settings: Settings,
        retrieval_service: AssistantRetrievalService | None = None,
        llm_reasoner: AssistantLLMReasoner | None = None,
        validator: AssistantAnswerValidator | None = None,
        query_classifier: AssistantQueryClassifier | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.conversation_repo = AssistantConversationRepository(session)
        self.message_repo = AssistantMessageRepository(session)
        self.citation_repo = AssistantCitationRepository(session)
        self.retrieval_run_repo = AssistantRetrievalRunRepository(session)
        self.feedback_repo = AssistantFeedbackRepository(session)

        self.retrieval_service = retrieval_service or AssistantRetrievalService(
            session=session,
            settings=settings,
        )
        self.llm_reasoner = llm_reasoner or AssistantLLMReasoner(settings=settings)
        self.validator = validator or AssistantAnswerValidator()
        self.classifier = query_classifier or AssistantQueryClassifier()

    # -----------------------------------------------------------------------
    # Conversation Management
    # -----------------------------------------------------------------------

    def create_conversation(
        self,
        *,
        project_ctx: ProjectContext,
        title: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> ConversationResponse:
        """Create a new conversation session for the authenticated project member."""
        user = project_ctx.principal.user
        default_title = title or "New Project Inquiry"

        conversation = self.conversation_repo.create(
            organisation_id=project_ctx.organisation.id,
            project_id=project_ctx.project.id,
            created_by_user_id=user.id,
            title=default_title,
            metadata_json=metadata_json,
        )
        return ConversationResponse.model_validate(conversation)

    def list_conversations(
        self,
        *,
        project_ctx: ProjectContext,
        status: AssistantConversationStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ConversationResponse]:
        """List caller's conversations within the project."""
        user = project_ctx.principal.user
        convs = self.conversation_repo.list_for_user_in_project(
            project_id=project_ctx.project.id,
            user_id=user.id,
            status=status,
            limit=limit,
            offset=offset,
        )
        return [ConversationResponse.model_validate(c) for c in convs]

    def get_conversation_detail(
        self,
        *,
        project_ctx: ProjectContext,
        conversation_id: uuid.UUID,
    ) -> ConversationDetailResponse:
        """Fetch conversation metadata and ordered message turns with their citations."""
        user = project_ctx.principal.user
        conv = self.conversation_repo.get_by_id(
            conversation_id,
            project_id=project_ctx.project.id,
            load_messages=True,
        )
        if not conv:
            raise NotFoundError("Conversation not found.", code="CONVERSATION_NOT_FOUND")

        # Non-managers can only access their own conversations
        if conv.created_by_user_id != user.id and not project_ctx.has_permission("assistant.admin"):
            raise ForbiddenError("You cannot access another user's conversation.", code="FORBIDDEN_CONVERSATION")

        msg_responses: list[AssistantMessageResponse] = []
        for msg in conv.messages:
            cit_responses = [
                AssistantCitationResponse.model_validate(c)
                for c in msg.citations
            ]
            msg_responses.append(
                AssistantMessageResponse(
                    id=msg.id,
                    conversation_id=msg.conversation_id,
                    sender_type=AssistantSenderType(msg.sender_type),
                    content=msg.content,
                    answer_status=AssistantAnswerStatus(msg.answer_status) if msg.answer_status else None,
                    structured_payload_json=msg.structured_payload_json,
                    citations=cit_responses,
                    model_name=msg.model_name,
                    prompt_tokens=msg.prompt_tokens,
                    completion_tokens=msg.completion_tokens,
                    duration_ms=msg.duration_ms,
                    retrieval_run_id=msg.retrieval_run_id,
                    created_at=msg.created_at,
                )
            )

        return ConversationDetailResponse(
            conversation=ConversationResponse.model_validate(conv),
            messages=msg_responses,
        )

    def update_conversation(
        self,
        *,
        project_ctx: ProjectContext,
        conversation_id: uuid.UUID,
        title: str | None = None,
        status: AssistantConversationStatus | None = None,
    ) -> ConversationResponse:
        """Update conversation title or active/archived status."""
        user = project_ctx.principal.user
        conv = self.conversation_repo.get_by_id(
            conversation_id,
            project_id=project_ctx.project.id,
        )
        if not conv:
            raise NotFoundError("Conversation not found.", code="CONVERSATION_NOT_FOUND")

        if conv.created_by_user_id != user.id and not project_ctx.has_permission("assistant.admin"):
            raise ForbiddenError("You cannot modify another user's conversation.", code="FORBIDDEN_CONVERSATION")

        updated = self.conversation_repo.update(
            conversation_id,
            title=title,
            status=status,
        )
        return ConversationResponse.model_validate(updated)

    def delete_conversation(
        self,
        *,
        project_ctx: ProjectContext,
        conversation_id: uuid.UUID,
    ) -> bool:
        """Delete an assistant conversation and all its messages/citations."""
        user = project_ctx.principal.user
        conv = self.conversation_repo.get_by_id(
            conversation_id,
            project_id=project_ctx.project.id,
        )
        if not conv:
            raise NotFoundError("Conversation not found.", code="CONVERSATION_NOT_FOUND")

        if conv.created_by_user_id != user.id and not project_ctx.has_permission("assistant.admin"):
            raise ForbiddenError("You cannot delete another user's conversation.", code="FORBIDDEN_CONVERSATION")

        return self.conversation_repo.delete(conversation_id)

    # -----------------------------------------------------------------------
    # Question Answering & Execution Pipeline
    # -----------------------------------------------------------------------

    def ask_question(
        self,
        *,
        project_ctx: ProjectContext,
        conversation_id: uuid.UUID,
        request: QuestionRequest,
    ) -> AssistantAnswerResponse:
        """Execute end-to-end question answering turn within a conversation."""
        started_at = time.perf_counter()
        user = project_ctx.principal.user

        # 1. Verify conversation exists and user has access
        conv = self.conversation_repo.get_by_id(
            conversation_id,
            project_id=project_ctx.project.id,
        )
        if not conv:
            raise NotFoundError("Conversation not found.", code="CONVERSATION_NOT_FOUND")

        if conv.created_by_user_id != user.id and not project_ctx.has_permission("assistant.admin"):
            raise ForbiddenError("You cannot post in another user's conversation.", code="FORBIDDEN_CONVERSATION")

        # 1b. Resolve optional handover case context & enforce successor publication gate before DB/LLM work
        resolved_handover_case_id: uuid.UUID | None = request.handover_case_id
        if resolved_handover_case_id is None and isinstance(conv.metadata_json, dict):
            raw_hc = conv.metadata_json.get("handover_case_id")
            if raw_hc:
                try:
                    resolved_handover_case_id = uuid.UUID(str(raw_hc))
                except (ValueError, TypeError):
                    resolved_handover_case_id = None

        handover_case = None
        if resolved_handover_case_id is not None:
            handover_case = HandoverCaseService(self.session).get_case(
                resolved_handover_case_id,
                project_id=project_ctx.project.id,
                load_relationships=True,
            )
            can_review_or_manage = any(
                project_ctx.has_permission(p)
                for p in (
                    "handover.review",
                    "handover.approve",
                    "handover.deliver",
                    "handover.admin",
                    "project.manage",
                )
            )
            if is_unapproved_draft_restricted_for_successor(
                handover_case,
                user.id,
                can_review_or_manage,
            ):
                raise ForbiddenError(
                    "Incoming successors cannot query an unapproved handover package before publication.",
                    code="HANDOVER_DRAFT_RESTRICTED",
                )

        # 2. Persist User Message
        user_message = self.message_repo.create(
            conversation_id=conversation_id,
            organisation_id=project_ctx.organisation.id,
            project_id=project_ctx.project.id,
            sender_type=AssistantSenderType.USER,
            content=request.question,
        )

        # Update conversation title automatically on first turn if it has default title
        if conv.title == "New Conversation" or conv.title == "New Project Inquiry":
            auto_title = request.question.strip()[:60]
            if len(request.question) > 60:
                auto_title += "..."
            self.conversation_repo.update(conversation_id, title=auto_title)

        # 3. Fetch past conversation history
        past_messages = self.message_repo.list_for_conversation(conversation_id, limit=6)
        chat_history: list[dict[str, str]] = []
        for pm in past_messages:
            if pm.id == user_message.id:
                continue
            chat_history.append({"role": pm.sender_type, "content": pm.content})

        # 4. Query Classification & Entity Extraction
        classified: ClassifiedQuery = self.classifier.classify(request.question)

        # 5. Permission-Aware Retrieval
        retrieval_res: AssistantRetrievalResult = self.retrieval_service.retrieve(
            project_ctx=project_ctx,
            classified_query=classified,
            search_mode=request.mode,
            response_mode=request.response_mode,
            include_domains=request.include_domains,
            max_citations=request.max_citations,
        )

        # 5b. Augment retrieval context with ACL-filtered approved handover package evidence
        is_handover_access_restricted = False
        if handover_case is not None:
            is_handover_access_restricted = self._augment_retrieval_with_handover_context(
                project_ctx=project_ctx,
                handover_case=handover_case,
                package_version_id=request.package_version_id,
                current_section=request.current_section,
                retrieval_res=retrieval_res,
            )

        # 6. Record Retrieval Run Telemetry
        retrieval_run = self.retrieval_run_repo.create(
            organisation_id=project_ctx.organisation.id,
            project_id=project_ctx.project.id,
            user_id=user.id,
            query_text=request.question,
            query_type=classified.query_type,
            retrieval_mode=request.mode,
            candidates_found=retrieval_res.candidates_found,
            candidates_authorized=retrieval_res.candidates_authorized,
            duration_ms=retrieval_res.duration_ms,
            diagnostics_json=retrieval_res.diagnostics,
        )

        # 7. Qwen3 Structured Reasoner
        available_labels = [c.citation_label for c in retrieval_res.citations_manifest]
        payload, llm_telemetry = self.llm_reasoner.generate_answer(
            question=request.question,
            evidence_prompt=retrieval_res.evidence_prompt,
            response_mode=request.response_mode,
            conversation_history=chat_history,
            available_citation_labels=available_labels,
        )

        # 8. Citation & Epistemic Validation Engine
        validated: ValidatedAssistantAnswer = self.validator.validate(
            payload=payload,
            citations_manifest=retrieval_res.citations_manifest,
            is_access_restricted=is_handover_access_restricted,
        )

        total_duration_ms = int((time.perf_counter() - started_at) * 1000)

        # 9. Persist Assistant Message Turn
        structured_payload = {
            "query_type": classified.query_type.value,
            "response_mode": validated.response_mode.value,
            "claims": [c.model_dump() for c in validated.claims],
            "uncertainty": validated.uncertainty,
            "conflicts": validated.conflicts,
            "missing_information": validated.missing_information,
            "suggested_followup_questions": validated.suggested_followup_questions,
            "research_report": validated.research_report.model_dump() if validated.research_report else None,
            "deep_think": validated.deep_think.model_dump() if validated.deep_think else None,
            "deep_extract": validated.deep_extract.model_dump() if validated.deep_extract else None,
        }

        assistant_message = self.message_repo.create(
            conversation_id=conversation_id,
            organisation_id=project_ctx.organisation.id,
            project_id=project_ctx.project.id,
            sender_type=AssistantSenderType.ASSISTANT,
            content=validated.answer,
            answer_status=validated.answer_status,
            structured_payload_json=structured_payload,
            model_name=llm_telemetry.get("model_name"),
            prompt_tokens=llm_telemetry.get("prompt_tokens"),
            completion_tokens=llm_telemetry.get("completion_tokens"),
            duration_ms=total_duration_ms,
            retrieval_run_id=retrieval_run.id,
        )

        # 10. Persist Citations
        citations_to_persist = []
        for order, cit in enumerate(validated.validated_citations, start=1):
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

        persisted_citations = self.citation_repo.create_batch(citations_to_persist)
        self.conversation_repo.touch_last_message(conversation_id)

        response_citations = [
            AssistantCitationResponse.model_validate(c) for c in persisted_citations
        ]

        return AssistantAnswerResponse(
            message_id=assistant_message.id,
            conversation_id=conversation_id,
            answer=validated.answer,
            answer_status=validated.answer_status,
            response_mode=validated.response_mode,
            query_type=classified.query_type,
            claims=validated.claims,
            citations=response_citations,
            uncertainty=validated.uncertainty,
            conflicts=validated.conflicts,
            missing_information=validated.missing_information,
            suggested_followup_questions=validated.suggested_followup_questions,
            research_report=validated.research_report,
            deep_think=validated.deep_think,
            deep_extract=validated.deep_extract,
            model_name=llm_telemetry.get("model_name", "qwen3:8b"),
            retrieval_run_id=retrieval_run.id,
            duration_ms=total_duration_ms,
            created_at=assistant_message.created_at,
        )

    # -----------------------------------------------------------------------
    # Feedback & Diagnostics
    # -----------------------------------------------------------------------

    def submit_feedback(
        self,
        *,
        project_ctx: ProjectContext,
        message_id: uuid.UUID,
        request: AssistantFeedbackRequest,
    ) -> AssistantFeedbackResponse:
        """Record user feedback rating on an assistant message turn."""
        user = project_ctx.principal.user
        msg = self.message_repo.get_by_id(message_id, load_citations=False)
        if not msg:
            raise NotFoundError("Message not found.", code="MESSAGE_NOT_FOUND")

        if msg.project_id != project_ctx.project.id:
            raise NotFoundError("Message does not belong to this project.", code="MESSAGE_NOT_IN_PROJECT")

        feedback = self.feedback_repo.create(
            message_id=message_id,
            user_id=user.id,
            feedback_type=request.feedback_type,
            comment=request.comment,
        )
        return AssistantFeedbackResponse.model_validate(feedback)

    def get_retrieval_diagnostics(
        self,
        *,
        project_ctx: ProjectContext,
        run_id: uuid.UUID,
    ) -> RetrievalDiagnosticsResponse:
        """Fetch audit diagnostic telemetry for a specific retrieval execution."""
        run = self.retrieval_run_repo.get_by_id(run_id)
        if not run:
            raise NotFoundError("Retrieval run record not found.", code="RUN_NOT_FOUND")

        if run.project_id != project_ctx.project.id:
            raise NotFoundError("Retrieval run does not belong to this project.", code="RUN_NOT_IN_PROJECT")

        return RetrievalDiagnosticsResponse.model_validate(run)

    def _augment_retrieval_with_handover_context(
        self,
        *,
        project_ctx: ProjectContext,
        handover_case: Any,
        package_version_id: uuid.UUID | None,
        current_section: str | None,
        retrieval_res: AssistantRetrievalResult,
    ) -> bool:
        """Ground assistant context with ACL-filtered approved handover sections and evidence."""
        from app.schemas.assistant import AssistantCitationResponse

        versions = list(getattr(handover_case, "versions", None) or [])
        target_version_id = package_version_id
        if target_version_id is None:
            current_v = next((v for v in versions if v.is_current), None)
            if current_v is not None:
                target_version_id = current_v.id
            elif versions:
                target_version_id = sorted(versions, key=lambda v: v.version_number, reverse=True)[0].id

        handover_type = "developer"
        if isinstance(handover_case.metadata_json, dict):
            raw_ht = handover_case.metadata_json.get("handover_type")
            if isinstance(raw_ht, str) and raw_ht in ("developer", "project_manager", "technical_lead"):
                handover_type = raw_ht

        due_str = (
            handover_case.target_handover_date.isoformat()
            if getattr(handover_case, "target_handover_date", None)
            else "Unspecified"
        )

        if target_version_id is None:
            header_only = (
                f'<handover_context case_id="{handover_case.id}" title="{redact_secrets(handover_case.title)}" '
                f'status="{handover_case.status}" handover_type="{handover_type}" '
                f'target_handover_date="{due_str}">\n'
                "No assembled package version exists yet for this handover case.\n"
                "</handover_context>"
            )
            retrieval_res.evidence_prompt = (
                f"{header_only}\n\n{retrieval_res.evidence_prompt}"
                if retrieval_res.evidence_prompt
                else header_only
            )
            retrieval_res.diagnostics["handover_case_id"] = str(handover_case.id)
            return False

        sections_resp = HandoverSectionReadService(self.session).get_version_sections(
            handover_case.id,
            target_version_id,
            project_id=project_ctx.project.id,
            viewer_user_id=project_ctx.principal.user.id,
            has_project_manage=project_ctx.has_permission("project.manage"),
        )

        ev_to_label: dict[uuid.UUID, str] = {
            c.evidence_id: c.citation_label for c in retrieval_res.citations_manifest
        }
        added_blocks: list[str] = []
        restricted_items_skipped = 0

        def _register_provenance(
            prov: Any,
            *,
            knowledge_item_id: uuid.UUID | None,
            section_title: str,
            fallback_excerpt: str,
        ) -> str | None:
            if prov.acl_restricted:
                return None
            if prov.evidence_id in ev_to_label:
                return ev_to_label[prov.evidence_id]
            if len(retrieval_res.citations_manifest) >= 16:
                return None
            label = f"S{len(retrieval_res.citations_manifest) + 1}"
            ev_to_label[prov.evidence_id] = label
            excerpt_text = redact_secrets(prov.supporting_excerpt or fallback_excerpt or "")[:400]
            cit = AssistantCitationResponse(
                citation_label=label,
                evidence_id=prov.evidence_id,
                chunk_id=None,
                knowledge_item_id=knowledge_item_id,
                source_title=prov.source_name or "Handover Evidence",
                source_provider=prov.source_provider or prov.source_type or "handover",
                source_url=prov.source_url,
                source_external_id=prov.source_reference,
                author=prov.author,
                source_timestamp=prov.source_timestamp,
                page_number=None,
                section_title=section_title,
                excerpt=excerpt_text,
                is_verified=True,
            )
            retrieval_res.citations_manifest.append(cit)
            date_str = (
                cit.source_timestamp.strftime("%Y-%m-%d")
                if cit.source_timestamp
                else "Undated"
            )
            added_blocks.append(
                f'<project_evidence id="{label}" provider="{cit.source_provider}" title="{cit.source_title}">\n'
                f"**Metadata**: Author: {cit.author or 'Unknown'} | Date: {date_str} | Handover Section: {section_title}\n"
                f"**Content**:\n{excerpt_text}\n"
                f"</project_evidence>"
            )
            return label

        ordered_sections = list(sections_resp.mandatory_sections)
        if current_section:
            focus = current_section.strip().lower()
            ordered_sections.sort(
                key=lambda s: (
                    0 if (focus == s.section_key.lower() or focus in s.section_title.lower()) else 1,
                    s.role_priority_rank,
                )
            )

        ctx_lines: list[str] = [
            f'<handover_context case_id="{handover_case.id}" version_id="{target_version_id}" '
            f'version_number="v{sections_resp.version.version_number}" '
            f'title="{redact_secrets(handover_case.title)}" status="{handover_case.status}" '
            f'handover_type="{sections_resp.handover_type_label}" target_handover_date="{due_str}">',
            f"Role Focus: {sections_resp.role_focus_summary}",
        ]

        for ms in ordered_sections:
            sec_lines: list[str] = [
                f"\n## Section {ms.section_number}: {ms.section_title} [status={ms.readiness_status}]"
            ]
            if ms.insufficient_info_message:
                sec_lines.append(f"Gaps / Insufficient Information: {ms.insufficient_info_message}")
            for ki in ms.knowledge_items:
                allowed_prov = [p for p in ki.provenance if not p.acl_restricted]
                if ki.provenance and not allowed_prov:
                    restricted_items_skipped += 1
                    continue
                labels = [
                    lbl
                    for p in allowed_prov
                    if (
                        lbl := _register_provenance(
                            p,
                            knowledge_item_id=ki.id,
                            section_title=ms.section_title,
                            fallback_excerpt=ki.content,
                        )
                    )
                    is not None
                ]
                cit_suffix = f" [{', '.join(labels)}]" if labels else ""
                sec_lines.append(
                    f"- Verified Finding ({ki.epistemic_status}): {redact_secrets(ki.title)} — "
                    f"{redact_secrets(ki.content)[:350]}{cit_suffix}"
                )
            for rel in ms.relationships[:6]:
                allowed_rel_prov = [p for p in rel.provenance if not p.acl_restricted]
                if rel.provenance and not allowed_rel_prov:
                    restricted_items_skipped += 1
                    continue
                labels = [
                    lbl
                    for p in allowed_rel_prov
                    if (
                        lbl := _register_provenance(
                            p,
                            knowledge_item_id=None,
                            section_title=ms.section_title,
                            fallback_excerpt=f"{rel.source_entity_name} --[{rel.relationship_type}]--> {rel.target_entity_name}",
                        )
                    )
                    is not None
                ]
                cit_suffix = f" [{', '.join(labels)}]" if labels else ""
                sec_lines.append(
                    f"- Verified Relationship: {rel.source_entity_name} --[{rel.relationship_type}]--> "
                    f"{rel.target_entity_name}{cit_suffix}"
                )
            for conflict in ms.unresolved_conflicts[:5]:
                sec_lines.append(
                    f"- UNRESOLVED CONFLICT ({conflict.priority} / {conflict.conflict_type}): "
                    f"{redact_secrets(conflict.explanation)[:220]}"
                )
            for step in ms.recommended_steps[:5]:
                sec_lines.append(
                    f"- Recommended Step [{step.get('status', 'pending')}]: {redact_secrets(str(step.get('title', '')))}"
                )
            for resp in ms.responsibilities_summary[:5]:
                sec_lines.append(
                    f"- Responsibility [{resp.get('transfer_status', 'pending')}]: "
                    f"{redact_secrets(str(resp.get('responsibility_title', '')))} "
                    f"(Successor confirmed={resp.get('successor_acknowledged', False)})"
                )
            if len(sec_lines) > 1:
                ctx_lines.extend(sec_lines)

        ctx_lines.append("</handover_context>")
        handover_block = "\n".join(ctx_lines)
        new_evidence_block = "\n\n".join(added_blocks)

        parts = [p for p in [handover_block, new_evidence_block, retrieval_res.evidence_prompt] if p]
        retrieval_res.evidence_prompt = "\n\n".join(parts)
        retrieval_res.candidates_authorized = max(
            retrieval_res.candidates_authorized,
            len(retrieval_res.citations_manifest),
        )
        retrieval_res.diagnostics["handover_case_id"] = str(handover_case.id)
        retrieval_res.diagnostics["handover_version_id"] = str(target_version_id)
        retrieval_res.diagnostics["handover_restricted_items_skipped"] = restricted_items_skipped
        return restricted_items_skipped > 0 and len(retrieval_res.citations_manifest) == 0
