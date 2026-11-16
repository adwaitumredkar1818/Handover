"""GitHub contribution attribution, domain classification, and responsibility alignment."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import (
    ContributionCategory,
    IdentityMatchMethod,
    ResponsibilityAlignment,
)
from app.models.evidence import EvidenceItem
from app.models.project import ProjectMembership
from app.models.team_roster import ContributionAttribution, TeamRosterMember

logger = logging.getLogger("app.services.contribution_attribution")

_DOMAIN_KEYWORDS: list[tuple[ContributionCategory, list[str]]] = [
    (ContributionCategory.DATABASE_ENGINEERING, ["migration", "alembic", "sql", "postgres", "schema", "database", "table", "index", "foreign key"]),
    (ContributionCategory.AUTHENTICATION, ["auth", "jwt", "login", "session", "password", "oauth", "token", "rbac", "permission", "credential"]),
    (ContributionCategory.SECURITY, ["security", "encryption", "aes-256", "secret", "ssrf", "sanitize", "vulnerability"]),
    (ContributionCategory.AI_ML, ["ollama", "qwen", "glm", "llm", "inference", "prompt", "ai/ml"]),
    (ContributionCategory.RAG_AND_RETRIEVAL, ["rag", "retrieval", "embedding", "nomic", "chroma", "vector", "chunk"]),
    (ContributionCategory.OCR_AND_DOCUMENT_PROCESSING, ["ocr", "pymupdf", "docx", "pdf", "extraction"]),
    (ContributionCategory.DEVOPS, ["ci/cd", "github actions", "pipeline", "dockerfile", "docker-compose", "deploy", "workflow"]),
    (ContributionCategory.INFRASTRUCTURE, ["infrastructure", "docker", "env", "port", "config", "server"]),
    (ContributionCategory.TESTING, ["test", "pytest", "unit test", "integration test", "mock", "assert", "coverage"]),
    (ContributionCategory.BUG_FIXING, ["fix", "bug", "patch", "hotfix", "resolve", "error", "crash"]),
    (ContributionCategory.DOCUMENTATION, ["doc", "readme", "specification", "architecture", "handover", "guide", "changelog"]),
    (ContributionCategory.FRONTEND_DEVELOPMENT, ["frontend", "react", "next.js", "nextjs", "component", "tailwind", "tsx", "jsx", "dom", "ui"]),
    (ContributionCategory.API_DEVELOPMENT, ["api", "router", "endpoint", "openapi", "swagger", "payload", "schema"]),
    (ContributionCategory.BACKEND_DEVELOPMENT, ["backend", "fastapi", "service", "handler", "repository", "worker"]),
    (ContributionCategory.INTEGRATION, ["integration", "github", "jira", "slack", "sync", "connector", "webhook"]),
]


def classify_contribution_domain(title_or_message: str, paths: list[str] | None = None) -> ContributionCategory:
    """Classify commit or contribution text into one of 17 canonical technical categories."""
    combined = (title_or_message or "").lower()
    if paths:
        combined += " " + " ".join(paths).lower()

    for category, keywords in _DOMAIN_KEYWORDS:
        if any(kw in combined for kw in keywords):
            return category

    return ContributionCategory.OTHER


def evaluate_alignment(
    category: ContributionCategory,
    roster_member: TeamRosterMember | None,
) -> tuple[ResponsibilityAlignment, str]:
    """Evaluate whether contribution aligns with member's declared responsibilities."""
    if roster_member is None:
        return (
            ResponsibilityAlignment.UNCERTAIN,
            "Contributor could not be mapped to a declared project team roster member.",
        )

    declared = [r.lower() for r in (roster_member.primary_responsibilities or [])]
    components = [c.lower() for c in (roster_member.component_ownership or [])]
    all_declared = declared + components

    if not all_declared:
        return (
            ResponsibilityAlignment.UNCERTAIN,
            f"Roster member '{roster_member.full_name}' has no declared responsibilities in the roster.",
        )

    cat_name = category.value.lower()
    cat_words = set(cat_name.replace("/", " ").replace("-", " ").split())

    # Exact or strong match
    for d in all_declared:
        if cat_name in d or d in cat_name or any(w in d for w in cat_words if len(w) > 3):
            return (
                ResponsibilityAlignment.ALIGNED,
                f"Contribution domain '{category.value}' aligns with declared responsibility '{d}'.",
            )

    # Partial / general developer match
    if any("developer" in d or "engineer" in d or "fullstack" in d or "lead" in d for d in declared):
        return (
            ResponsibilityAlignment.PARTIALLY_ALIGNED,
            f"Contribution domain '{category.value}' is broadly compatible with general role '{roster_member.role_name}'.",
        )

    return (
        ResponsibilityAlignment.OUTSIDE_DECLARED_RESPONSIBILITY,
        f"Contribution domain '{category.value}' is outside declared responsibilities: {', '.join(roster_member.primary_responsibilities[:3])}.",
    )


class ContributionAttributionService:
    """Resolves commit/PR author identity and attributes contributions to roster members."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def attribute_evidence(self, evidence: EvidenceItem) -> ContributionAttribution | None:
        if evidence.category not in ("commit", "pull_request", "issue"):
            return None

        meta = dict(evidence.metadata_json or {})
        gh_login = meta.get("github_author_login")
        git_email = meta.get("git_author_email")
        git_name = meta.get("git_author_name") or evidence.source_author_identity
        primary_id = gh_login or git_email or git_name or evidence.source_author_identity
        if not primary_id:
            return None

        # Fetch roster members for this project
        roster_stmt = select(TeamRosterMember).where(TeamRosterMember.project_id == evidence.project_id)
        roster_members = self._session.execute(roster_stmt).scalars().all()

        matched_member: TeamRosterMember | None = None
        match_method: str | None = None
        match_confidence: float = 0.0

        # Conservative matching hierarchy
        # 1. Exact GitHub username match
        if gh_login:
            for rm in roster_members:
                if rm.github_username and rm.github_username.lower() == gh_login.lower():
                    matched_member = rm
                    match_method = IdentityMatchMethod.EXACT_GITHUB_USERNAME.value
                    match_confidence = 1.0
                    break

        # 2. Exact Git commit email match
        if not matched_member and git_email:
            for rm in roster_members:
                if rm.email and rm.email.lower() == git_email.lower():
                    matched_member = rm
                    match_method = "exact_git_commit_email"
                    match_confidence = 0.95
                    break

        # 3. GitHub noreply email mapping
        if not matched_member and git_email and "users.noreply.github.com" in git_email.lower():
            local_part = git_email.lower().split("@")[0]
            noreply_username = local_part.split("+")[-1] if "+" in local_part else local_part
            for rm in roster_members:
                if rm.github_username and rm.github_username.lower() == noreply_username:
                    matched_member = rm
                    match_method = "github_noreply_email_mapping"
                    match_confidence = 0.95
                    break

        # 4. Full name match (ambiguous candidate per AGENTS.md / Part 12)
        if not matched_member and git_name:
            for rm in roster_members:
                if rm.full_name and rm.full_name.lower() == git_name.lower():
                    matched_member = rm
                    match_method = "ambiguous_name"
                    match_confidence = 0.50
                    break

        # Classify contribution category
        category = classify_contribution_domain(evidence.title + " " + (evidence.original_filename or ""))
        alignment, explanation = evaluate_alignment(category, matched_member)
        if match_method == "ambiguous_name":
            explanation = f"Ambiguous candidate matched by display name only: {explanation}"

        # Upsert attribution
        existing_attr = self._session.execute(
            select(ContributionAttribution).where(
                ContributionAttribution.evidence_item_id == evidence.id
            )
        ).scalars().first()

        if existing_attr:
            existing_attr.contributor_identifier = primary_id
            existing_attr.identifier_type = "github_login" if gh_login else "git_email" if git_email else "name"
            existing_attr.matched_roster_member_id = matched_member.id if matched_member else None
            existing_attr.matched_project_membership_id = (
                matched_member.matched_project_membership_id if matched_member else None
            )
            existing_attr.match_method = match_method
            existing_attr.match_confidence = match_confidence
            existing_attr.contribution_category = category.value
            existing_attr.responsibility_alignment = alignment.value
            existing_attr.alignment_explanation = explanation
            attr = existing_attr
        else:
            attr = ContributionAttribution(
                project_id=evidence.project_id,
                evidence_item_id=evidence.id,
                contributor_identifier=primary_id,
                identifier_type="github_login" if gh_login else "git_email" if git_email else "name",
                matched_roster_member_id=matched_member.id if matched_member else None,
                matched_project_membership_id=(
                    matched_member.matched_project_membership_id if matched_member else None
                ),
                match_method=match_method,
                match_confidence=match_confidence,
                contribution_category=category.value,
                responsibility_alignment=alignment.value,
                alignment_explanation=explanation,
                metadata_json={"title": evidence.title},
            )
            self._session.add(attr)

        self._session.commit()
        return attr
