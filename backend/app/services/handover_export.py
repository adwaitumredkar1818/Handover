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

import uuid
from datetime import UTC, datetime
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
        """Generate viewer-authorized PDF document using PyMuPDF (fitz)."""
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

        doc = fitz.open()
        watermark = data["approval_watermark"]
        is_approved = data["is_approved_release"]

        # Page 1: Title and Metadata Cover Page
        cover = doc.new_page(width=595, height=842)  # A4 size in points
        y = 60

        cover.insert_text(
            fitz.Point(54, y),
            watermark,
            fontsize=10,
            fontname="helv",
            color=(0.1, 0.55, 0.25) if is_approved else (0.75, 0.2, 0.2),
        )
        y += 18
        cover.insert_text(
            fitz.Point(54, y),
            f"THE HANDOVER PLATFORM  |  {data['handover_type_label'].upper()}",
            fontsize=10,
            fontname="helv",
            color=(0.2, 0.4, 0.8),
        )
        y += 24
        cover.insert_text(
            fitz.Point(54, y),
            data["title"][:54],
            fontsize=18,
            fontname="helv",
            color=(0.1, 0.1, 0.1),
        )
        y += 20
        cover.insert_text(
            fitz.Point(54, y),
            f"Project: {data['project_name']}",
            fontsize=12,
            fontname="helv",
            color=(0.3, 0.3, 0.3),
        )
        y += 28

        meta_lines = [
            f"Handover Case ID: {data['case_id']}",
            f"Handover Type: {data['handover_type_label']}",
            f"Lifecycle Status: {data['status'].upper()} ({watermark})",
            f"Package Version: v{data['package_version_number']} (Rev v{data['version']})",
            f"Package Hash: {data['package_hash'][:24]}...",
            f"Generated: {data['exported_at']}",
        ]
        if data.get("target_handover_date"):
            meta_lines.append(f"Target Handover Date: {data['target_handover_date']}")
        if data["viewer_acl_filtered"]:
            meta_lines.append(
                f"Source Access Notice: {data['omitted_restricted_items_count']} restricted item(s) omitted."
            )

        for line in meta_lines:
            cover.insert_text(
                fitz.Point(54, y),
                line,
                fontsize=9,
                fontname="helv",
                color=(0.25, 0.25, 0.25),
            )
            y += 14

        y += 12
        cover.draw_line(fitz.Point(54, y), fitz.Point(541, y), color=(0.8, 0.8, 0.8), width=1)
        y += 20

        if data["description"]:
            cover.insert_text(
                fitz.Point(54, y),
                "EXECUTIVE SUMMARY",
                fontsize=11,
                fontname="helv",
                color=(0.1, 0.1, 0.1),
            )
            y += 14
            desc_rect = fitz.Rect(54, y, 541, y + 64)
            cover.insert_textbox(
                desc_rect,
                data["description"][:380],
                fontsize=9,
                fontname="helv",
                color=(0.2, 0.2, 0.2),
            )
            y += 72

        summary_sections = data["mandatory_sections"] or []
        cover.insert_text(
            fitz.Point(54, y),
            "MANDATORY HANDOVER SECTIONS" if summary_sections else "COMPILED 8-DOMAIN SECTIONS",
            fontsize=11,
            fontname="helv",
            color=(0.1, 0.1, 0.1),
        )
        y += 16

        if summary_sections:
            for msec in summary_sections:
                sec_line = (
                    f"{msec['section_number']}. {msec['section_title']} "
                    f"[{msec['readiness_status']}]"
                )
                cover.insert_text(
                    fitz.Point(60, y),
                    sec_line[:68],
                    fontsize=9,
                    fontname="helv",
                    color=(0.2, 0.2, 0.2),
                )
                y += 14
        else:
            for sec in data["sections"]:
                sec_line = f"* {sec['title']} ({sec['evidence_item_count']} items)"
                cover.insert_text(
                    fitz.Point(60, y),
                    sec_line[:60],
                    fontsize=9,
                    fontname="helv",
                    color=(0.2, 0.2, 0.2),
                )
                y += 14

        cover.insert_text(
            fitz.Point(54, 800),
            f"{watermark}  |  Confidential - The Handover Platform",
            fontsize=8,
            fontname="helv",
            color=(0.5, 0.5, 0.5),
        )

        # Render the 10 mandatory sections when available, else fallback to 8-domain sections
        if summary_sections:
            for msec in summary_sections:
                page = doc.new_page(width=595, height=842)
                py = 54
                page.insert_text(
                    fitz.Point(54, py),
                    f"{msec['section_number']}. {msec['section_title'].upper()}"[:58],
                    fontsize=13,
                    fontname="helv",
                    color=(0.1, 0.2, 0.5),
                )
                py += 14
                header_sub = (
                    f"Readiness: {msec['readiness_status']}  |  "
                    f"Priority #{msec['role_priority_rank']} ({data['handover_type_label']})"
                )
                page.insert_text(
                    fitz.Point(54, py),
                    header_sub[:85],
                    fontsize=8,
                    fontname="helv",
                    color=(0.4, 0.4, 0.4),
                )
                py += 10
                page.draw_line(
                    fitz.Point(54, py),
                    fitz.Point(541, py),
                    color=(0.85, 0.85, 0.85),
                    width=0.75,
                )
                py += 16
                content_rect = fitz.Rect(54, py, 541, 780)
                body_text = (
                    msec.get("content_markdown")
                    or msec.get("insufficient_info_message")
                    or "No verified content recorded for this section."
                )
                page.insert_textbox(
                    content_rect,
                    body_text[:3400],
                    fontsize=9,
                    fontname="helv",
                    color=(0.15, 0.15, 0.15),
                )
                page_footer = f"{watermark}  |  Handover: {data['title'][:36]}  |  Page {page.number + 1}"
                page.insert_text(
                    fitz.Point(54, 810),
                    page_footer,
                    fontsize=8,
                    fontname="helv",
                    color=(0.5, 0.5, 0.5),
                )
        else:
            for sec in data["sections"]:
                page = doc.new_page(width=595, height=842)
                py = 54
                page.insert_text(
                    fitz.Point(54, py),
                    sec["title"].upper()[:50],
                    fontsize=13,
                    fontname="helv",
                    color=(0.1, 0.2, 0.5),
                )
                py += 14
                badge = "Human Verified" if sec["is_human_edited"] else "Machine Assembly"
                header_sub = f"Domain: {sec['section_type']}  |  Status: {badge}"
                page.insert_text(
                    fitz.Point(54, py),
                    header_sub[:80],
                    fontsize=8,
                    fontname="helv",
                    color=(0.4, 0.4, 0.4),
                )
                py += 10
                page.draw_line(
                    fitz.Point(54, py),
                    fitz.Point(541, py),
                    color=(0.85, 0.85, 0.85),
                    width=0.75,
                )
                py += 16
                content_rect = fitz.Rect(54, py, 541, 780)
                text_to_insert = sec["content"] or "No content recorded for this section."
                page.insert_textbox(
                    content_rect,
                    text_to_insert[:3000],
                    fontsize=9,
                    fontname="helv",
                    color=(0.15, 0.15, 0.15),
                )
                page_footer = f"{watermark}  |  Handover: {data['title'][:36]}  |  Page {page.number + 1}"
                page.insert_text(
                    fitz.Point(54, 810),
                    page_footer,
                    fontsize=8,
                    fontname="helv",
                    color=(0.5, 0.5, 0.5),
                )

        if data["signoffs"]:
            spage = doc.new_page(width=595, height=842)
            sy = 54
            spage.insert_text(
                fitz.Point(54, sy),
                "HUMAN SIGN-OFFS & APPROVAL LOG",
                fontsize=13,
                fontname="helv",
                color=(0.1, 0.2, 0.5),
            )
            sy += 24
            for s in data["signoffs"]:
                sline = f"* {s['signoff_type']} : {s['decision'].upper()} ({s['signed_at'] or 'Pending'})"
                spage.insert_text(
                    fitz.Point(54, sy),
                    sline[:85],
                    fontsize=9,
                    fontname="helv",
                    color=(0.15, 0.15, 0.15),
                )
                sy += 16
            spage.insert_text(
                fitz.Point(54, 810),
                f"{watermark}  |  Page {spage.number + 1}",
                fontsize=8,
                fontname="helv",
                color=(0.5, 0.5, 0.5),
            )

        pdf_bytes = doc.tobytes()
        doc.close()
        return pdf_bytes
