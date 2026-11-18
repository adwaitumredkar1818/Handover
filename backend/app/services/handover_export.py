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
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.enums import (
    AuditOutcome,
    HandoverLinkType,
    ProjectMembershipStatus,
    UserStatus,
)
from app.models.handover import (
    HandoverCase,
    HandoverPackageVersion,
    HandoverSignoff,
)
from app.models.project import Project, ProjectMembership
from app.models.user import User
from app.repositories.audit import AuditLogRepository
from app.services.audit import AuditService
from app.services.handover_eligibility import (
    HandoverEligibilityService,
    check_evidence_accessibility,
)
from app.services.handover_sections import HandoverSectionReadService, redact_secrets


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
        total_omitted_restricted = 0
        total_accessible_items = 0

        if target_version:
            # Always re-evaluate ACLs fresh for this requesting viewer (never trust cached content)
            hydrated = self.section_read_service.get_version_sections(
                case_id=case_id,
                version_id=target_version.id,
                project_id=project_id,
                viewer_user_id=user_id,
                has_project_manage=has_project_manage,
            )

            for sec in hydrated.sections:
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
            "status": case.status.value if hasattr(case.status, "value") else str(case.status),
            "version": case.version,
            "package_version_id": str(target_version.id) if target_version else None,
            "package_version_number": target_version.version_number if target_version else 1,
            "package_hash": canonical_hash,
            "viewer_acl_filtered": total_omitted_restricted > 0,
            "omitted_restricted_items_count": total_omitted_restricted,
            "accessible_items_count": total_accessible_items,
            "sections": sections,
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
    ) -> str:
        """Render viewer-authorized handover package to clean GitHub-flavored Markdown."""
        data = self._get_case_data(
            project_id=project_id,
            case_id=case_id,
            user_id=user_id,
            version_id=version_id,
            has_project_manage=has_project_manage,
            export_format="markdown",
        )
        lines: list[str] = [
            f"# {data['title']}",
            "",
            f"**Project**: {data['project_name']}  ",
            f"**Handover Case Status**: `{data['status'].upper()}`  ",
            f"**Package Version**: v{data['package_version_number']} (Case v{data['version']})  ",
            f"**Integrity Hash**: `{data['package_hash'][:16]}...`  ",
            f"**Exported At**: {data['exported_at']}  ",
        ]
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
    ) -> dict[str, Any]:
        """Export viewer-authorized structured JSON representation of the handover package."""
        return self._get_case_data(
            project_id=project_id,
            case_id=case_id,
            user_id=user_id,
            version_id=version_id,
            has_project_manage=has_project_manage,
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
    ) -> bytes:
        """Generate viewer-authorized PDF document using PyMuPDF (fitz)."""
        data = self._get_case_data(
            project_id=project_id,
            case_id=case_id,
            user_id=user_id,
            version_id=version_id,
            has_project_manage=has_project_manage,
            export_format="pdf",
        )

        doc = fitz.open()

        # Page 1: Title and Metadata Cover Page
        cover = doc.new_page(width=595, height=842)  # A4 size in points
        y = 72

        # Header Title
        cover.insert_text(
            fitz.Point(54, y),
            "THE HANDOVER PLATFORM",
            fontsize=10,
            fontname="helv",
            color=(0.2, 0.4, 0.8),
        )
        y += 24
        cover.insert_text(
            fitz.Point(54, y),
            data["title"][:50],
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
        y += 30

        # Metadata block
        meta_lines = [
            f"Handover Case ID: {data['case_id']}",
            f"Status: {data['status'].upper()}",
            f"Package Version: v{data['package_version_number']} (Rev v{data['version']})",
            f"Package Hash: {data['package_hash'][:24]}...",
            f"Generated: {data['exported_at']}",
        ]
        for line in meta_lines:
            cover.insert_text(
                fitz.Point(54, y),
                line,
                fontsize=9,
                fontname="helv",
                color=(0.25, 0.25, 0.25),
            )
            y += 14

        y += 16
        cover.draw_line(fitz.Point(54, y), fitz.Point(541, y), color=(0.8, 0.8, 0.8), width=1)
        y += 24

        # Description if available
        if data["description"]:
            cover.insert_text(
                fitz.Point(54, y),
                "EXECUTIVE SUMMARY",
                fontsize=11,
                fontname="helv",
                color=(0.1, 0.1, 0.1),
            )
            y += 16
            desc_rect = fitz.Rect(54, y, 541, y + 80)
            cover.insert_textbox(
                desc_rect,
                data["description"][:400],
                fontsize=9,
                fontname="helv",
                color=(0.2, 0.2, 0.2),
            )
            y += 90

        # Section overview summary table
        cover.insert_text(
            fitz.Point(54, y),
            "COMPILED 8-DOMAIN SECTIONS",
            fontsize=11,
            fontname="helv",
            color=(0.1, 0.1, 0.1),
        )
        y += 16

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

        # Footer on Cover
        cover.insert_text(
            fitz.Point(54, 800),
            "Confidential - The Handover Knowledge Platform",
            fontsize=8,
            fontname="helv",
            color=(0.5, 0.5, 0.5),
        )

        # Content Pages for each Section
        for sec in data["sections"]:
            page = doc.new_page(width=595, height=842)
            py = 54

            # Section Header
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

            # Section Content
            content_rect = fitz.Rect(54, py, 541, 780)
            text_to_insert = sec["content"] or "No content recorded for this section."
            page.insert_textbox(
                content_rect,
                text_to_insert[:3000],
                fontsize=9,
                fontname="helv",
                color=(0.15, 0.15, 0.15),
            )

            # Page Footer
            page_footer = f"Handover: {data['title'][:40]}  |  Page {page.number + 1}"
            page.insert_text(
                fitz.Point(54, 810),
                page_footer,
                fontsize=8,
                fontname="helv",
                color=(0.5, 0.5, 0.5),
            )

        pdf_bytes = doc.tobytes()
        doc.close()
        return pdf_bytes
