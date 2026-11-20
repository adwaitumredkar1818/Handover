"""Handover Document Export Service.

Supports:
- Markdown export
- Structured JSON export
- Professional PDF export via PyMuPDF (fitz)

Security & Integrity:
- Fail-closed source ACL checks (inaccessible evidence excluded)
- Secrets and tokens sanitized
- Verbatim citations and provenance preserved
- Human edits prioritized over draft narratives
"""

from __future__ import annotations

import base64
import html as html_lib
import io
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pymupdf as fitz
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.enums import (
    AuditOutcome,
    HandoverLinkType,
    HandoverPackageSectionType,
    ProjectMembershipStatus,
    UserStatus,
)
from app.models.handover import (
    HandoverCase,
    HandoverChecklist,
    HandoverPackageVersion,
    HandoverSignoff,
)
from app.models.project import Project, ProjectMembership
from app.models.user import User
from app.repositories.audit import AuditLogRepository
from app.services.audit import AuditService
from app.services.handover_case import is_unapproved_draft_restricted_for_successor
from app.services.handover_eligibility import (
    HandoverEligibilityService,
    check_evidence_accessibility,
)
from app.services.handover_sections import (
    HANDOVER_ROLE_CONFIG,
    HandoverSectionReadService,
    build_mandatory_ten_sections,
    build_start_here_briefing,
    normalize_handover_type,
    redact_secrets,
)


class HandoverExportService:
    """Exports structured handover packages to Markdown, JSON, and PDF formats.

    Strictly separates canonical stored package content (and its immutable SHA-256 hash)
    from the viewer-authorized export representation computed per request.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.eligibility_service = HandoverEligibilityService(session)
        self.section_read_service = HandoverSectionReadService(session)
        self.audit_service = AuditService(audit_repository=AuditLogRepository(session))

    def _verify_viewer_project_access(
        self,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID | None,
        has_project_manage: bool,
    ) -> User:
        """Fail closed if requesting viewer principal is missing, inactive, or not authorised on project."""
        if user_id is None:
            raise ForbiddenError("Authenticated viewer principal is required to export a handover package.")

        viewer = self.session.get(User, user_id)
        if viewer is None or viewer.status != UserStatus.ACTIVE.value:
            raise ForbiddenError("Requesting user principal is invalid or inactive.")

        if has_project_manage:
            return viewer

        membership = self.session.execute(
            select(ProjectMembership).where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.user_id == user_id,
                ProjectMembership.status == ProjectMembershipStatus.ACTIVE.value,
            )
        ).scalar_one_or_none()
        if membership is None:
            raise ForbiddenError(
                "Viewer does not have active project membership required to export this handover package."
            )
        return viewer

    def _render_authorized_section_text(
        self,
        *,
        section_title: str,
        permitted_items: list[dict[str, Any]],
        permitted_relationships: list[dict[str, Any]],
        omitted_count: int,
    ) -> str:
        """Render clean viewer-authorized section text strictly from permitted records."""
        lines: list[str] = []
        if omitted_count > 0:
            lines.append(
                f"> *Source Access Notice: {omitted_count} restricted item(s) in '{section_title}' "
                "were omitted due to source access controls.*"
            )
            lines.append("")

        for item in permitted_items:
            lines.append(f"### {item['title']}")
            if item["summary"]:
                lines.append(item["summary"])
            if item["provenance"]:
                sources = ", ".join(
                    p["source_name"] for p in item["provenance"] if p.get("source_name")
                )
                if sources:
                    lines.append(f"*Sources*: {sources}")
            lines.append("")

        if permitted_relationships:
            lines.append("### Verified Relationships")
            for rel in permitted_relationships:
                lines.append(
                    f"- **{rel['source_entity_name']}** `{rel['relationship_type']}` **{rel['target_entity_name']}**"
                )
            lines.append("")

        if not permitted_items and not permitted_relationships:
            if omitted_count > 0:
                return "\n".join(lines).strip()
            return "*(No authorized verified findings recorded for this section)*"

        return "\n".join(lines).strip()

    def _get_case_data(
        self,
        *,
        project_id: uuid.UUID,
        case_id: uuid.UUID,
        user_id: uuid.UUID | None,
        version_id: uuid.UUID | None = None,
        has_project_manage: bool = False,
        can_review_or_manage: bool | None = None,
        role_override: str | None = None,
        export_format: str = "json",
    ) -> dict[str, Any]:
        """Fetch case metadata and compute a fresh per-viewer ACL-filtered export representation.

        Never mutates the canonical package version, section rows, or SHA-256 content_hash.
        Never reuses cached section content across viewers when restricted evidence is present.
        """
        self._verify_viewer_project_access(
            project_id=project_id,
            user_id=user_id,
            has_project_manage=has_project_manage,
        )
        assert user_id is not None

        case = (
            self.session.query(HandoverCase)
            .filter(
                HandoverCase.id == case_id,
                HandoverCase.project_id == project_id,
            )
            .first()
        )
        if not case:
            raise NotFoundError(f"HandoverCase {case_id} not found in project {project_id}.")

        can_bypass_draft_gate = (
            can_review_or_manage if can_review_or_manage is not None else has_project_manage
        )
        if is_unapproved_draft_restricted_for_successor(
            case,
            viewer_user_id=user_id,
            can_review_or_manage=can_bypass_draft_gate,
        ):
            raise ForbiddenError(
                "Incoming successor cannot export unapproved handover drafts before formal publication."
            )

        project = self.session.query(Project).filter(Project.id == project_id).first()
        project_name = redact_secrets(project.name) if project else "Project"

        if version_id is not None:
            target_version = (
                self.session.query(HandoverPackageVersion)
                .filter(
                    HandoverPackageVersion.id == version_id,
                    HandoverPackageVersion.case_id == case_id,
                    HandoverPackageVersion.project_id == project_id,
                )
                .first()
            )
            if not target_version:
                raise NotFoundError(
                    f"Package version {version_id} not found for case {case_id} in project {project_id}."
                )
        else:
            target_version = (
                self.session.query(HandoverPackageVersion)
                .filter(
                    HandoverPackageVersion.case_id == case_id,
                    HandoverPackageVersion.project_id == project_id,
                )
                .order_by(HandoverPackageVersion.version_number.desc())
                .first()
            )

        sections: list[dict[str, Any]] = []
        mandatory_sections_out: list[dict[str, Any]] = []
        start_here_out: dict[str, Any] | None = None
        epistemic_summary_out: dict[str, Any] | None = None
        total_underlying_findings = 0
        composed_card_count = 0
        total_omitted_restricted = 0
        total_accessible_items = 0
        resolved_role = normalize_handover_type(
            role_override or (case.metadata_json or {}).get("handover_type")
        )
        role_cfg = HANDOVER_ROLE_CONFIG[resolved_role]

        if target_version:
            # Always re-evaluate ACLs fresh for this requesting viewer (never trust cached content)
            hydrated = self.section_read_service.get_version_sections(
                case_id=case_id,
                version_id=target_version.id,
                project_id=project_id,
                viewer_user_id=user_id,
                has_project_manage=has_project_manage,
                role_override=resolved_role,
            )

            overview_ctx: dict[str, Any] = {
                "project_name": project_name,
                "case_title": redact_secrets(case.title),
                "case_description": redact_secrets(case.description or ""),
                "case_status": case.status.value if hasattr(case.status, "value") else str(case.status),
            }
            team_members_ctx: list[dict[str, Any]] = []
            transfers_ctx: list[dict[str, Any]] = []
            unresolved_conflicts = []
            resolved_conflicts = []

            for sec in hydrated.sections:
                if sec.section_type == HandoverPackageSectionType.PROJECT_OVERVIEW_CONTEXT.value and sec.domain_context:
                    overview_ctx = sec.domain_context
                elif sec.section_type == HandoverPackageSectionType.RESPONSIBILITIES_OWNERSHIP.value and sec.domain_context:
                    team_members_ctx = list(sec.domain_context.get("team_members") or [])
                    transfers_ctx = list(sec.domain_context.get("responsibility_transfers") or [])
                elif sec.section_type == HandoverPackageSectionType.BUGS_BLOCKERS_RISKS.value:
                    unresolved_conflicts = list(sec.unresolved_conflicts)
                    resolved_conflicts = list(sec.resolved_conflicts)

                permitted_items: list[dict[str, Any]] = []
                permitted_rels: list[dict[str, Any]] = []
                sec_omitted = 0

                # Re-verify direct evidence links attached to this section, if any
                direct_ev_ids = [
                    link.evidence_id
                    for link in sec.content_links
                    if link.evidence_id is not None
                    and link.knowledge_item_id is None
                    and link.relationship_id is None
                ]
                if direct_ev_ids:
                    all_direct_ok, inaccessible_direct = check_evidence_accessibility(
                        self.session,
                        direct_ev_ids,
                        project_id=project_id,
                        viewer_user_id=user_id,
                        has_project_manage=has_project_manage,
                    )
                    if not all_direct_ok:
                        sec_omitted += len(inaccessible_direct)

                for ki in sec.knowledge_items:
                    has_restricted_source = any(p.acl_restricted for p in ki.provenance)
                    if has_restricted_source:
                        # Fail closed: omit restricted finding completely so title/summary/excerpt cannot leak
                        sec_omitted += 1
                        continue
                    permitted_prov = [
                        {
                            "evidence_id": str(p.evidence_id),
                            "source_type": p.source_type,
                            "source_provider": p.source_provider,
                            "source_name": redact_secrets(p.source_name),
                            "source_url": p.source_url,
                            "author": p.author,
                            "source_timestamp": p.source_timestamp.isoformat() if p.source_timestamp else None,
                            "supporting_excerpt": redact_secrets(p.supporting_excerpt) if p.supporting_excerpt else None,
                        }
                        for p in ki.provenance
                        if not p.acl_restricted
                    ]
                    permitted_items.append(
                        {
                            "id": str(ki.id),
                            "title": redact_secrets(ki.title),
                            "summary": redact_secrets(ki.content),
                            "category": ki.category,
                            "epistemic_status": ki.epistemic_status,
                            "provenance": permitted_prov,
                        }
                    )

                for rel in sec.relationships:
                    has_restricted_rel = any(p.acl_restricted for p in rel.provenance)
                    if has_restricted_rel:
                        sec_omitted += 1
                        continue
                    permitted_rel_prov = [
                        {
                            "evidence_id": str(p.evidence_id),
                            "source_type": p.source_type,
                            "source_name": redact_secrets(p.source_name),
                            "source_url": p.source_url,
                        }
                        for p in rel.provenance
                        if not p.acl_restricted
                    ]
                    permitted_rels.append(
                        {
                            "id": str(rel.id),
                            "relationship_type": rel.relationship_type,
                            "source_entity_name": redact_secrets(rel.source_entity_name),
                            "target_entity_name": redact_secrets(rel.target_entity_name),
                            "provenance": permitted_rel_prov,
                        }
                    )

                total_omitted_restricted += sec_omitted
                total_accessible_items += len(permitted_items) + len(permitted_rels)

                # Never expose cached canonical section_content if ANY restricted source was omitted for this viewer
                if sec_omitted > 0:
                    safe_content = self._render_authorized_section_text(
                        section_title=redact_secrets(sec.section_title),
                        permitted_items=permitted_items,
                        permitted_relationships=permitted_rels,
                        omitted_count=sec_omitted,
                    )
                else:
                    raw_content = sec.section_content or sec.content_summary or ""
                    safe_content = redact_secrets(raw_content)

                sections.append(
                    {
                        "title": redact_secrets(sec.section_title),
                        "section_type": str(sec.section_type),
                        "content": safe_content,
                        "is_human_edited": False,
                        "evidence_item_count": len(permitted_items),
                        "omitted_restricted_count": sec_omitted,
                        "items": permitted_items,
                        "relationships": permitted_rels,
                    }
                )

            case_checklists = list(
                self.session.execute(
                    select(HandoverChecklist)
                    .where(
                        HandoverChecklist.case_id == case_id,
                        HandoverChecklist.project_id == project_id,
                    )
                    .options(selectinload(HandoverChecklist.items))
                    .order_by(HandoverChecklist.created_at.asc())
                )
                .scalars()
                .all()
            )
            mandatory_objs = build_mandatory_ten_sections(
                hydrated_sections=hydrated.sections,
                handover_type=resolved_role,
                unresolved_conflicts=unresolved_conflicts,
                resolved_conflicts=resolved_conflicts,
                team_members_ctx=team_members_ctx,
                transfers_ctx=transfers_ctx,
                checklists=case_checklists,
                domain_context_overview=overview_ctx,
                omit_restricted_items=True,
            )
            mandatory_sections_out = [m.model_dump(mode="json") for m in mandatory_objs]
            has_provisional = any(
                (ki.epistemic_status != "human_verified" or ki.review_status != "approved")
                for m in mandatory_objs
                for ki in m.knowledge_items
            )
            start_here_out = build_start_here_briefing(
                mandatory_sections=mandatory_objs,
                domain_context_overview=overview_ctx,
                team_members_ctx=team_members_ctx,
                transfers_ctx=transfers_ctx,
                handover_type=resolved_role,
                is_provisional_draft=has_provisional,
            ).model_dump(mode="json")
            epistemic_summary_out = hydrated.epistemic_summary.model_dump(mode="json")
            total_underlying_findings = hydrated.total_underlying_findings
            composed_card_count = len(mandatory_objs) and sum(
                len(m.knowledge_items) for m in mandatory_objs
            )

        signoffs = (
            self.session.query(HandoverSignoff)
            .filter(
                HandoverSignoff.case_id == case_id,
                HandoverSignoff.project_id == project_id,
            )
            .all()
        )
        signoff_list = [
            {
                "signoff_type": (
                    s.signoff_type.value
                    if hasattr(s.signoff_type, "value")
                    else str(s.signoff_type)
                ),
                "decision": (
                    s.decision.value
                    if hasattr(s.decision, "value")
                    else str(s.decision)
                ),
                "signed_at": s.signed_at.isoformat() if s.signed_at else None,
                "notes": redact_secrets(s.comments or ""),
            }
            for s in signoffs
        ]

        canonical_hash = (
            (
                getattr(target_version, "content_hash", None)
                or getattr(target_version, "package_hash", None)
                or "N/A"
            )
            if target_version
            else "N/A"
        )

        status_str = case.status.value if hasattr(case.status, "value") else str(case.status)
        is_approved_release = status_str in {"approved", "delivered", "acknowledged", "transferred"}
        approval_watermark = (
            "APPROVED RELEASE" if is_approved_release else "DRAFT — NOT APPROVED"
        )

        # Immutable audit event — strictly no restricted excerpts or secrets logged
        self.audit_service.record_event(
            event_type="handover.package.exported",
            resource_type="handover_package_version" if target_version else "handover_case",
            resource_id=str(target_version.id if target_version else case.id),
            actor_user_id=user_id,
            organisation_id=case.organisation_id,
            project_id=project_id,
            outcome=AuditOutcome.SUCCESS.value,
            metadata={
                "case_id": str(case.id),
                "version_id": str(target_version.id) if target_version else None,
                "version_number": target_version.version_number if target_version else None,
                "package_hash": canonical_hash,
                "format": export_format,
                "handover_type": resolved_role,
                "is_approved_release": is_approved_release,
                "viewer_acl_filtered": total_omitted_restricted > 0,
                "omitted_restricted_items_count": total_omitted_restricted,
                "accessible_items_count": total_accessible_items,
            },
        )

        return {
            "case_id": str(case.id),
            "project_name": project_name,
            "title": redact_secrets(case.title),
            "description": redact_secrets(case.description or ""),
            "status": status_str,
            "is_approved_release": is_approved_release,
            "approval_watermark": approval_watermark,
            "handover_type": resolved_role,
            "handover_type_label": role_cfg["label"],
            "role_focus_summary": role_cfg["focus_summary"],
            "departing_member_id": str(case.departing_member_id),
            "successor_id": str(case.successor_id) if case.successor_id else None,
            "target_handover_date": (
                case.target_handover_date.isoformat() if case.target_handover_date else None
            ),
            "version": case.version,
            "package_version_id": str(target_version.id) if target_version else None,
            "package_version_number": target_version.version_number if target_version else 1,
            "package_hash": canonical_hash,
            "viewer_acl_filtered": total_omitted_restricted > 0,
            "omitted_restricted_items_count": total_omitted_restricted,
            "accessible_items_count": total_accessible_items,
            "sections": sections,
            "mandatory_sections": mandatory_sections_out,
            "start_here_briefing": start_here_out,
            "epistemic_summary": epistemic_summary_out,
            "total_underlying_findings": total_underlying_findings,
            "composed_card_count": composed_card_count,
            "signoffs": signoff_list,
            "exported_at": datetime.now(UTC).isoformat(),
        }

    def export_markdown(
        self,
        *,
        project_id: uuid.UUID,
        case_id: uuid.UUID,
        user_id: uuid.UUID | None,
        version_id: uuid.UUID | None = None,
        has_project_manage: bool = False,
        can_review_or_manage: bool | None = None,
        role_override: str | None = None,
    ) -> str:
        """Render viewer-authorized handover package to clean GitHub-flavored Markdown."""
        data = self._get_case_data(
            project_id=project_id,
            case_id=case_id,
            user_id=user_id,
            version_id=version_id,
            has_project_manage=has_project_manage,
            can_review_or_manage=can_review_or_manage,
            role_override=role_override,
            export_format="markdown",
        )
        lines: list[str] = []
        if not data["is_approved_release"]:
            lines.extend([
                f"> **{data['approval_watermark']}** — This handover draft has not yet received final human approval.",
                "",
            ])
        lines.extend([
            f"# {data['title']}",
            "",
            f"**Project**: {data['project_name']}  ",
            f"**Handover Type**: {data['handover_type_label']}  ",
            f"**Handover Case Status**: `{data['status'].upper()}` (`{data['approval_watermark']}`)  ",
            f"**Package Version**: v{data['package_version_number']} (Case v{data['version']})  ",
            f"**Integrity Hash**: `{data['package_hash'][:16]}...`  ",
            f"**Exported At**: {data['exported_at']}  ",
        ])
        if data["viewer_acl_filtered"]:
            lines.append(
                f"**Source Access Filtering**: {data['omitted_restricted_items_count']} restricted item(s) omitted for this viewer  "
            )
        lines.extend(["", "---", ""])

        if data["description"]:
            lines.extend([
                "## Overview",
                data["description"],
                "",
                "---",
                "",
            ])

        briefing = data.get("start_here_briefing")
        if isinstance(briefing, dict):
            lines.extend([
                "## Start Here — Executive Project Briefing",
                "",
            ])
            if briefing.get("is_provisional_draft"):
                lines.append(
                    "> *Provisional Draft Notice*: Includes pending-review findings clearly separated from human-verified facts."
                )
                lines.append("")
            lines.extend([
                f"- **What is this project?**: {briefing.get('what_is_this_project', '')}",
                f"- **What has been built?**: {briefing.get('what_has_been_built', '')}",
                f"- **How does it work?**: {briefing.get('how_does_it_work', '')}",
                f"- **What is the current state?**: {briefing.get('what_is_the_current_state', '')}",
                f"- **What should you understand first?**: {briefing.get('what_to_understand_first', '')}",
                f"- **Where should you start?**: {briefing.get('where_to_start', '')}",
                "",
                "---",
                "",
            ])

        if data["mandatory_sections"]:
            for msec in data["mandatory_sections"]:
                priority_tag = " *(Role Priority)*" if msec.get("is_role_priority") else ""
                lines.extend([
                    f"## {msec['section_number']}. {msec['section_title']}{priority_tag}",
                    "",
                    f"*Readiness*: `{msec['readiness_status']}` | *Priority Rank*: #{msec['role_priority_rank']}  ",
                    "",
                ])
                if msec.get("content_markdown"):
                    lines.append(msec["content_markdown"])
                elif msec.get("insufficient_info_message"):
                    lines.append(f"> *{msec['insufficient_info_message']}*")
                else:
                    lines.append("*(No verified content recorded for this section)*")
                lines.extend(["", "---", ""])
        else:
            for sec in data["sections"]:
                audit_label = (
                    "[Human Edited & Verified]"
                    if sec["is_human_edited"]
                    else "[Deterministic Machine Assembly]"
                )
                meta_sub = f"*Type*: `{sec['section_type']}` | *Items*: {sec['evidence_item_count']}"
                lines.extend([
                    f"## {sec['title']}",
                    "",
                    f"{meta_sub}  ",
                    f"*Status*: {audit_label}  ",
                    "",
                    sec["content"] or "*(No content recorded for this section)*",
                    "",
                    "---",
                    "",
                ])

        if data["signoffs"]:
            lines.extend([
                "## Role Sign-Offs & Acknowledgements",
                "",
                "| Phase / Role | Decision | Signed At | Notes |",
                "| :--- | :--- | :--- | :--- |",
            ])
            for s in data["signoffs"]:
                row = (
                    f"| {s['signoff_type']} | `{s['decision'].upper()}` | "
                    f"{s['signed_at'] or 'Pending'} | {s['notes']} |"
                )
                lines.append(row)
            lines.extend(["", "---", ""])

        lines.extend([
            "> **Handover Notice**: This document was generated by **The Handover** platform.",
            "> All claims are grounded in verified source evidence and authenticated records.",
        ])

        return "\n".join(lines)

    def export_json(
        self,
        *,
        project_id: uuid.UUID,
        case_id: uuid.UUID,
        user_id: uuid.UUID | None,
        version_id: uuid.UUID | None = None,
        has_project_manage: bool = False,
        can_review_or_manage: bool | None = None,
        role_override: str | None = None,
    ) -> dict[str, Any]:
        """Export viewer-authorized structured JSON representation of the handover package."""
        return self._get_case_data(
            project_id=project_id,
            case_id=case_id,
            user_id=user_id,
            version_id=version_id,
            has_project_manage=has_project_manage,
            can_review_or_manage=can_review_or_manage,
            role_override=role_override,
            export_format="json",
        )

    @staticmethod
    def _load_logo_data_uri() -> str:
        """Load the canonical frontend Handover logo PNG as a data URI for offline Chromium/PyMuPDF rendering."""
        logo_path = Path(__file__).resolve().parents[3] / "frontend" / "public" / "handover-logo.png"
        if logo_path.is_file():
            encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
            return f"data:image/png;base64,{encoded}"
        return ""

    @staticmethod
    def _render_html_to_pdf_bytes(html_doc: str, *, footer_label: str) -> bytes:
        """Render print-ready HTML/CSS to A4 PDF using headless Chromium (Playwright), falling back to PyMuPDF Story."""
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    context = browser.new_context(viewport={"width": 1024, "height": 1448})
                    page = context.new_page()
                    page.set_content(html_doc, wait_until="load", timeout=15000)
                    footer_html = (
                        '<div style="width:100%;font-family:Inter,system-ui,sans-serif;font-size:8px;'
                        'color:#718096;padding:0 14mm;display:flex;justify-content:space-between;align-items:center;">'
                        f"<span>{html_lib.escape(footer_label)}</span>"
                        '<span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span>'
                        "</div>"
                    )
                    pdf_bytes = page.pdf(
                        format="A4",
                        print_background=True,
                        prefer_css_page_size=True,
                        display_header_footer=True,
                        header_template="<span></span>",
                        footer_template=footer_html,
                        margin={"top": "14mm", "right": "14mm", "bottom": "16mm", "left": "14mm"},
                    )
                    return pdf_bytes
                finally:
                    browser.close()
        except Exception:
            buf = io.BytesIO()
            writer = fitz.DocumentWriter(buf)
            story = fitz.Story(html=html_doc)
            story.write(
                writer,
                lambda _rect_num, _filled: (
                    fitz.Rect(0, 0, 595, 842),
                    fitz.Rect(36, 36, 559, 806),
                    None,
                ),
            )
            writer.close()
            return buf.getvalue()

    def export_pdf(
        self,
        *,
        project_id: uuid.UUID,
        case_id: uuid.UUID,
        user_id: uuid.UUID | None,
        version_id: uuid.UUID | None = None,
        has_project_manage: bool = False,
        can_review_or_manage: bool | None = None,
        role_override: str | None = None,
    ) -> bytes:
        """Generate viewer-authorized PDF matching the exact Handover Report UI."""
        data = self._get_case_data(
            project_id=project_id,
            case_id=case_id,
            user_id=user_id,
            version_id=version_id,
            has_project_manage=has_project_manage,
            can_review_or_manage=can_review_or_manage,
            role_override=role_override,
            export_format="pdf",
        )

        esc = html_lib.escape
        watermark = data["approval_watermark"]
        is_approved = data["is_approved_release"]
        summary_sections = data["mandatory_sections"] or []

        logo_uri = self._load_logo_data_uri()
        logo_html = (
            f'<img src="{logo_uri}" alt="Handover" style="height:24px;width:auto;display:block;" />'
            if logo_uri
            else '<span style="font-size:15px;font-weight:700;color:#203653;">Handover</span>'
        )

        shield_svg = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:inline;vertical-align:-2px;"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/></svg>'
        lock_svg = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:inline;vertical-align:-1px;"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>'
        sparkles_svg = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:inline;vertical-align:-1px;"><path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"/></svg>'
        alert_svg = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#d39b43" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:inline;vertical-align:-2px;margin-right:5px;"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>'

        status_cls = "badge-green" if is_approved else "badge-amber"
        status_icon = shield_svg if is_approved else lock_svg

        ep_sum = data.get("epistemic_summary") or {}
        if ep_sum:
            total_verified = int(ep_sum.get("human_verified_included") or 0)
            total_pending = int(ep_sum.get("pending_verification") or 0)
        else:
            total_verified = (
                sum(len(m.get("knowledge_items") or []) for m in summary_sections)
                if summary_sections
                else sum(int(s.get("evidence_item_count") or 0) for s in data["sections"])
            )
            total_pending = 0
        verified_summary_cell = (
            f"{total_verified} verified ({total_pending} pending)"
            if total_pending > 0
            else f"{total_verified} verified"
        )
        outgoing_name = esc(str(data.get("departing_member_name") or data.get("departing_member_id") or "Assigned Member"))
        incoming_name = esc(str(data.get("successor_name") or data.get("successor_id") or "Unassigned"))
        target_date = esc(str(data.get("target_handover_date") or "Not set"))

        acl_banner_html = ""
        if data["viewer_acl_filtered"]:
            acl_banner_html = (
                f'<div class="epistemic-banner" style="background:#fbf5ea;border:1px solid #ebd5ac;color:#775420;margin-top:8px;">'
                f'<strong>Source Access Notice:</strong> {int(data["omitted_restricted_items_count"])} restricted item(s) omitted based on viewer permissions.'
                f"</div>"
            )

        start_here_html = ""
        briefing = data.get("start_here_briefing")
        if isinstance(briefing, dict):
            briefing_rows = [
                ("What is this project?", briefing.get("what_is_this_project") or ""),
                ("What has been built?", briefing.get("what_has_been_built") or ""),
                ("How does it work?", briefing.get("how_does_it_work") or ""),
                ("What is the current state?", briefing.get("what_is_the_current_state") or ""),
                ("What should the successor understand first?", briefing.get("what_to_understand_first") or ""),
                ("Where should they start?", briefing.get("where_to_start") or ""),
            ]
            briefing_cards = "".join(
                f'<div class="handover-finding-card">'
                f'<p class="finding-title">{esc(label)}</p>'
                f'<p class="finding-body">{esc(str(val))}</p>'
                f"</div>"
                for label, val in briefing_rows
                if str(val).strip()
            )
            prov_tag = (
                ' <span class="badge badge-amber">Includes Provisional Draft Findings</span>'
                if briefing.get("is_provisional_draft")
                else ""
            )
            start_here_html = (
                f'<section class="sec" style="border-top:none;padding-top:0;margin-top:0;margin-bottom:20px;">'
                f'<div class="handover-section-heading">'
                f'<div class="sec-left"><span class="sec-num">00</span> <h2 class="sec-title">Start Here &mdash; Executive Project Briefing</h2> {prov_tag}</div>'
                f"</div>"
                f'<div class="sec-cards">{briefing_cards}</div>'
                f"</section>"
            )

        sections_html_parts: list[str] = []
        if summary_sections:
            for msec in summary_sections:
                num = f"{int(msec['section_number']):02d}"
                title = esc(str(msec["section_title"]))
                is_prio = bool(msec.get("is_role_priority") or msec.get("is_priority_for_role"))
                readiness = str(msec.get("readiness_status") or "insufficient_information")
                readiness_label = esc(readiness.replace("_", " "))
                r_cls = "badge-green" if readiness == "ready" else ("badge-red" if readiness == "has_conflicts" else "badge-amber")

                kis = msec.get("knowledge_items") or msec.get("items") or []
                ev_refs = msec.get("evidence_references") or []
                v_cnt = sum(
                    1
                    for it in kis
                    if isinstance(it, dict)
                    and it.get("epistemic_status", "human_verified") == "human_verified"
                    and it.get("review_status", "approved") == "approved"
                )
                p_cnt = len(kis) - v_cnt
                s_cnt = len(ev_refs) if ev_refs else int(msec.get("citation_count") or 0)

                guidance = str(msec.get("role_emphasis_note") or msec.get("role_guidance") or "").strip()
                insuff = str(msec.get("insufficient_info_message") or "").strip()
                prio_html = f'<span class="badge badge-blue">{sparkles_svg} Priority</span>' if is_prio else ""

                cards_html: list[str] = []
                for ki in kis:
                    if not isinstance(ki, dict):
                        continue
                    ki_title = esc(str(ki.get("title") or "Verified Finding"))
                    ki_content = esc(str(ki.get("content") or ki.get("structured_summary") or ki.get("summary") or ""))
                    is_item_verified = (
                        ki.get("epistemic_status", "human_verified") == "human_verified"
                        and ki.get("review_status", "approved") == "approved"
                    )
                    ep_icon = (
                        f'<span style="color:#299b80;margin-left:4px;">{shield_svg}</span>'
                        if is_item_verified
                        else '<span class="badge badge-amber" style="margin-left:6px;">Provisional &middot; Pending review</span>'
                    )
                    cons_cnt = int(((ki.get("structured_payload") or {}).get("consolidated_finding_count")) or 1)
                    cons_badge = (
                        f'<span class="badge badge-blue" style="margin-left:6px;">Consolidated ({cons_cnt} findings)</span>'
                        if cons_cnt > 1
                        else ""
                    )
                    prov = ki.get("provenance") or ki.get("citations") or []
                    prov_avail = ki.get("provenance_available", bool(prov))
                    if prov_avail and prov:
                        src_names = ", ".join(
                            esc(str(ev.get("source_name") or ev.get("evidence_title") or ev.get("source_title") or "Restricted"))
                            for ev in prov[:8]
                            if isinstance(ev, dict)
                        )
                        extra_src = f" (+{len(prov) - 8} more)" if len(prov) > 8 else ""
                        src_line = f"Sources: {src_names}{extra_src}"
                    else:
                        src_line = "Provenance: No linked source recorded"
                    cards_html.append(
                        f'<div class="handover-finding-card">'
                        f'<p class="finding-title">{ki_title} {ep_icon}{cons_badge}</p>'
                        f'<p class="finding-body">{ki_content}</p>'
                        f'<p class="finding-src">{src_line}</p>'
                        f"</div>"
                    )

                rels = msec.get("relationships") or []
                if rels:
                    rel_lis = "".join(
                        f'<li><span class="navy-med">{esc(str(r.get("source_entity_name") or r.get("source_entity_id") or ""))}</span> '
                        f'<span style="color:#315fba;">[{esc(str(r.get("relationship_type") or ""))}]</span> '
                        f'<span class="navy-med">{esc(str(r.get("target_entity_name") or r.get("target_entity_id") or ""))}</span></li>'
                        for r in rels if isinstance(r, dict)
                    )
                    cards_html.append(f'<ul class="rel-list">{rel_lis}</ul>')

                resps = msec.get("responsibilities_summary") or []
                if resps:
                    resp_lis = "".join(
                        f'<li><span class="navy-med">{esc(str(r.get("responsibility_description") or r.get("responsibility_title") or r.get("title") or "Responsibility"))}</span> '
                        f'&mdash; Status: {esc(str(r.get("transfer_status") or "pending"))}</li>'
                        for r in resps if isinstance(r, dict)
                    )
                    cards_html.append(f'<ul class="rel-list">{resp_lis}</ul>')

                steps = msec.get("recommended_steps") or []
                if steps:
                    step_lis = "".join(
                        f'<li>[{esc(str(st.get("priority") or st.get("status") or "pending").upper())}] <span class="navy-med">{esc(str(st.get("title") or ""))}</span></li>'
                        for st in steps if isinstance(st, dict)
                    )
                    cards_html.append(f'<ul class="rel-list">{step_lis}</ul>')

                conflicts = msec.get("unresolved_conflicts") or []
                if conflicts:
                    cf_lis = "".join(f"<li>{esc(str(cf.get('explanation') or ''))}</li>" for cf in conflicts if isinstance(cf, dict))
                    cards_html.append(
                        f'<div class="conflict-box"><p class="conflict-title">Unresolved Verification Conflicts ({len(conflicts)} &mdash; Excluded from Verified Facts)</p>'
                        f'<ul class="conflict-list">{cf_lis}</ul></div>'
                    )

                if not cards_html and not insuff:
                    raw_md = str(msec.get("content_markdown") or "").strip()
                    if raw_md:
                        cards_html.append(f'<div class="handover-finding-card"><p class="finding-body">{esc(raw_md)}</p></div>')

                insuff_html = f'<div class="insuff-box">{alert_svg}{esc(insuff)}</div>' if insuff else ""
                guidance_html = f'<p class="sec-guide">{esc(guidance)}</p>' if guidance else ""
                counts_label = (
                    f"{v_cnt} verified &middot; {p_cnt} provisional &middot; {s_cnt} sources"
                    if p_cnt > 0
                    else f"{v_cnt} verified &middot; {s_cnt} sources"
                )

                sections_html_parts.append(
                    f'<section class="sec">'
                    f'<div class="handover-section-heading">'
                    f'<div class="sec-left"><span class="sec-num">{num}</span> <h2 class="sec-title">{title}</h2> {prio_html}</div>'
                    f'<div class="sec-right"><span class="badge {r_cls}">{readiness_label}</span> '
                    f'<span class="sec-counts">{counts_label}</span></div>'
                    f"</div>"
                    f"{guidance_html}"
                    f"{insuff_html}"
                    f'<div class="sec-cards">{"".join(cards_html)}</div>'
                    f"</section>"
                )
        else:
            for idx, sec in enumerate(data["sections"], start=1):
                paragraphs = "".join(
                    f"<p>{esc(line)}</p>"
                    for line in str(sec.get("content") or "No content recorded.").splitlines()
                    if line.strip()
                )
                sections_html_parts.append(
                    f'<section class="sec">'
                    f'<div class="handover-section-heading">'
                    f'<div class="sec-left"><span class="sec-num">{idx:02d}</span> <h2 class="sec-title">{esc(str(sec["title"]))}</h2></div>'
                    f"</div>"
                    f'<div class="handover-finding-card"><div class="finding-body">{paragraphs}</div></div>'
                    f"</section>"
                )

        signoffs_html = ""
        if data["signoffs"]:
            rows = "".join(
                f'<li><span class="navy-med">{esc(str(s["signoff_type"]))}</span>: '
                f'{esc(str(s["decision"]).upper())} ({esc(str(s.get("signed_at") or "Pending"))})</li>'
                for s in data["signoffs"]
            )
            signoffs_html = (
                f'<section class="sec">'
                f'<div class="handover-section-heading"><div class="sec-left"><h2 class="sec-title">Human Sign-Offs &amp; Approval Log</h2></div></div>'
                f'<ul class="rel-list">{rows}</ul>'
                f"</section>"
            )

        html_doc = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>
  @page {{ size: A4; margin: 14mm 14mm 16mm 14mm; }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: 'Manrope', 'Inter', ui-sans-serif, system-ui, -apple-system, sans-serif;
    color: #203653;
    background: #ffffff;
    font-size: 13px;
    line-height: 1.5;
    margin: 0;
    padding: 0;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }}
  .handover-report {{
    max-width: 100%;
    background: #ffffff;
  }}
  .report-header {{
    border-bottom: 2px solid #203653;
    padding-bottom: 20px;
    margin-bottom: 24px;
  }}
  .topbar {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 16px;
  }}
  .topbar-badges {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
  }}
  .badge {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 9px;
    border-radius: 9999px;
    font-size: 11px;
    font-weight: 600;
    border: 1px solid #d9e1f0;
  }}
  .badge-amber {{ background: #fbf5ea; color: #8f6522; border-color: #ebd5ac; }}
  .badge-green {{ background: #eef6f3; color: #1d6e5b; border-color: #bfdcd3; }}
  .badge-indigo {{ background: #f4f2fa; color: #5f4f9a; border-color: #d3ccec; }}
  .badge-blue {{ background: #eef2fa; color: #284f9c; border-color: #c3d2ec; }}
  .badge-red {{ background: #fbf0f0; color: #a04549; border-color: #edc5c7; }}
  .case-ver {{ font-size: 11.5px; font-weight: 500; color: #718096; }}
  .eyebrow {{
    margin: 18px 0 0 0;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.2em;
    color: #315fba;
  }}
  h1 {{
    margin: 6px 0 0 0;
    font-size: 28px;
    font-weight: 600;
    letter-spacing: -0.02em;
    color: #203653;
    line-height: 1.15;
  }}
  .case-title {{ margin: 4px 0 0 0; font-size: 13.5px; color: #718096; }}
  .meta-grid {{
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 14px;
    margin: 20px 0 0 0;
    font-size: 12.5px;
  }}
  .meta-dt {{ font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.05em; color: #94a3b8; }}
  .meta-dd {{ margin: 2px 0 0 0; font-weight: 500; color: #203653; }}
  .epistemic-banner {{
    margin-top: 16px;
    border-radius: 8px;
    background: #f8fafc;
    padding: 8px 12px;
    font-size: 11.5px;
    color: #718096;
  }}
  .sec {{
    border-top: 1px solid #d9e1f0;
    padding-top: 20px;
    margin-top: 24px;
  }}
  .sec:first-of-type {{ border-top: none; padding-top: 0; margin-top: 0; }}
  .handover-section-heading {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 10px;
    break-after: avoid;
    page-break-after: avoid;
  }}
  .sec-left {{ display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }}
  .sec-right {{ display: flex; align-items: center; gap: 8px; }}
  .sec-num {{ font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11.5px; font-weight: 600; color: #315fba; }}
  .sec-title {{ margin: 0; font-size: 15.5px; font-weight: 600; color: #203653; }}
  .sec-counts {{ font-size: 11.5px; color: #718096; }}
  .sec-guide {{ margin: 0 0 10px 0; font-size: 11.5px; color: #718096; break-after: avoid; page-break-after: avoid; }}
  .insuff-box {{
    margin-bottom: 10px;
    border-radius: 8px;
    border: 1px solid #ebd5ac;
    background: rgba(251, 245, 234, 0.7);
    padding: 10px 12px;
    font-size: 11.5px;
    color: #5f4219;
  }}
  .sec-cards {{ display: flex; flex-direction: column; gap: 10px; }}
  .handover-finding-card {{
    border-radius: 8px;
    border: 1px solid #d9e1f0;
    background: rgba(248, 250, 252, 0.45);
    padding: 12px 14px;
    break-inside: avoid;
    page-break-inside: avoid;
  }}
  .finding-title {{ margin: 0; font-size: 13px; font-weight: 600; color: #203653; }}
  .finding-body {{ margin: 4px 0 0 0; font-size: 12.5px; color: #334155; white-space: pre-wrap; line-height: 1.5; }}
  .finding-src {{ margin: 6px 0 0 0; font-size: 11px; color: #718096; }}
  .rel-list {{ margin: 4px 0 0 0; padding-left: 18px; font-size: 12.5px; color: #334155; }}
  .rel-list li {{ margin-bottom: 3px; }}
  .navy-med {{ font-weight: 500; color: #203653; }}
  .conflict-box {{
    border-radius: 8px;
    border: 1px solid #edc5c7;
    background: rgba(251, 240, 240, 0.45);
    padding: 10px 12px;
    break-inside: avoid;
    page-break-inside: avoid;
  }}
  .conflict-title {{ margin: 0; font-size: 11.5px; font-weight: 600; color: #a04549; }}
  .conflict-list {{ margin: 6px 0 0 0; padding-left: 16px; font-size: 11.5px; color: #334155; }}
</style>
</head>
<body>
  <article class="handover-report">
    <header class="report-header">
      <div class="topbar">
        <div>{logo_html}</div>
        <div class="topbar-badges">
          <span class="badge {status_cls}">{status_icon} {esc(watermark)}</span>
          <span class="badge badge-indigo">{esc(data["handover_type_label"])}</span>
          <span class="case-ver">Version v{int(data["package_version_number"])}</span>
        </div>
      </div>
      <p class="eyebrow">Handover Report</p>
      <h1>{esc(str(data["project_name"]))}</h1>
      <p class="case-title">{esc(str(data["title"]))}</p>
      <dl class="meta-grid">
        <div><dt class="meta-dt">Outgoing</dt><dd class="meta-dd">{outgoing_name}</dd></div>
        <div><dt class="meta-dt">Incoming</dt><dd class="meta-dd">{incoming_name}</dd></div>
        <div><dt class="meta-dt">Target Date</dt><dd class="meta-dd">{target_date}</dd></div>
        <div><dt class="meta-dt">Verified</dt><dd class="meta-dd">{esc(verified_summary_cell)}</dd></div>
      </dl>
      <div class="epistemic-banner">
        <span style="color:#299b80;margin-right:4px;">{shield_svg}</span>
        Only human-verified knowledge compiled into this immutable package version appears as confirmed handover content. Unresolved conflicts and unverified items are explicitly separated.
      </div>
      {acl_banner_html}
    </header>
    {start_here_html}
    {''.join(sections_html_parts)}
    {signoffs_html}
  </article>
</body>
</html>"""

        return self._render_html_to_pdf_bytes(
            html_doc,
            footer_label=f"{watermark} · {data['project_name']} · v{data['package_version_number']} · Hash {str(data['package_hash'])[:16]}",
        )
