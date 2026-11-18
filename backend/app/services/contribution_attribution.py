"""GitHub contribution attribution, configurable work classification, identity review, and responsibility alignment."""

from __future__ import annotations

import logging
import re
import uuid
from collections import defaultdict
from datetime import UTC
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.security import utc_now
from app.models.audit import AuditLog
from app.models.enums import (
    ContributionCategory,
    ContributorReviewStatus,
    ContributorType,
    IdentityMatchMethod,
    ResponsibilityAlignment,
)
from app.models.evidence import EvidenceItem
from app.models.integration import UserSourceAuthorisation
from app.models.organisation import OrganisationInvitation, OrganisationMembership
from app.models.project import Project, ProjectMembership
from app.models.rbac import Role
from app.models.team_roster import ContributionAttribution, TeamRosterMember
from app.services.integrations.github_sync import is_bot_identity
from app.services.llm import LLMGenerationRequest, StructuredLLMClient

logger = logging.getLogger("app.services.contribution_attribution")

_RAG_EXPLICIT_RE = re.compile(
    r"(?:^|[/\\._\-\s])rag(?:$|[/\\._\-\s])|retrieval[-_ ]augmented|rag[-_ ]pipeline|rag[-_ ]chain|hybrid[-_ ]rag",
    re.IGNORECASE,
)


def is_explicit_rag_evidence(text: str) -> bool:
    """Return True only when text explicitly evidences Retrieval-Augmented Generation (RAG),
    never matching 'rag' as a substring of unrelated words like 'storage' or 'coverage'.
    """
    return bool(text and _RAG_EXPLICIT_RE.search(text))


_PATH_DOMAIN_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Database", ("migrations/", "alembic/", "/models/", ".sql", "schema", "database", "vector_store", "chroma")),
    ("Authentication", ("/auth", "jwt", "oauth", "rbac", "supabase_verifier", "password", "session")),
    ("Security", ("security", "token_encryption", "access_policy", "rls", "crypto")),
    ("OCR", ("/ocr", "document_extraction", "pymupdf", "docx")),
    ("AI/ML", ("/llm", "extraction_prompts", "knowledge_validator", "reconstruction_worker", "ollama", "qwen", "embedding")),
    ("Integration", ("integrations/", "github_", "jira_", "slack_", "webhook")),
    ("API", ("/api/", "routes/", "endpoints", "schemas/", "openapi")),
    ("Frontend", ("frontend/", "src/app/", "src/components/", ".tsx", ".jsx", ".css", "tailwind")),
    ("Testing", ("tests/", "test_", ".test.", ".spec.", "vitest", "pytest")),
    ("Documentation", ("docs/", "documentation/", "readme", ".md", ".mdx", "specification")),
    ("DevOps", ("dockerfile", "docker-compose", "compose.yaml", ".github/workflows", "render.yaml")),
    ("Infrastructure", ("infrastructure/", "docker/", ".env", "k8s/", "terraform/", "deploy/")),
    ("Backend", ("backend/", "services/", "repositories/", "worker.py", ".py")),
]

_DOMAIN_KEYWORDS: list[tuple[ContributionCategory, list[str]]] = [
    (ContributionCategory.DATABASE_ENGINEERING, ["migration", "alembic", "sql", "postgres", "schema", "database", "table", "index", "foreign key", "chroma", "vector_store"]),
    (ContributionCategory.AUTHENTICATION, ["auth", "jwt", "login", "session", "password", "oauth", "token", "rbac", "permission", "credential"]),
    (ContributionCategory.SECURITY, ["security", "encryption", "aes-256", "secret", "ssrf", "sanitize", "vulnerability"]),
    (ContributionCategory.AI_ML, ["ollama", "qwen", "glm", "llm", "inference", "prompt", "ai/ml", "embedding"]),
    (ContributionCategory.OCR_AND_DOCUMENT_PROCESSING, ["ocr", "pymupdf", "docx", "pdf", "extraction"]),
    (ContributionCategory.DEVOPS, ["ci/cd", "github actions", "pipeline", "dockerfile", "docker-compose", "deploy", "workflow"]),
    (ContributionCategory.INFRASTRUCTURE, ["infrastructure", "docker", "env", "port", "config"]),
    (ContributionCategory.TESTING, ["test", "pytest", "vitest", "unit test", "integration test", "mock", "assert", "coverage"]),
    (ContributionCategory.BUG_FIXING, ["fix", "bug", "patch", "hotfix", "resolve", "error", "crash"]),
    (ContributionCategory.DOCUMENTATION, ["doc", "readme", "specification", "architecture", "handover", "guide", "changelog"]),
    (ContributionCategory.FRONTEND_DEVELOPMENT, ["frontend", "react", "next.js", "nextjs", "component", "tailwind", "tsx", "jsx", "dom", "ui"]),
    (ContributionCategory.API_DEVELOPMENT, ["api", "router", "endpoint", "openapi", "swagger", "payload", "schema"]),
    (ContributionCategory.BACKEND_DEVELOPMENT, ["backend", "fastapi", "service", "handler", "repository", "worker"]),
    (ContributionCategory.INTEGRATION, ["integration", "github", "jira", "slack", "sync", "connector", "webhook"]),
]

_CANONICAL_CATEGORY_MAP: dict[str, str] = {
    "Frontend": ContributionCategory.FRONTEND_DEVELOPMENT.value,
    "Backend": ContributionCategory.BACKEND_DEVELOPMENT.value,
    "Database": ContributionCategory.DATABASE_ENGINEERING.value,
    "API": ContributionCategory.API_DEVELOPMENT.value,
    "Authentication": ContributionCategory.AUTHENTICATION.value,
    "AI/ML": ContributionCategory.AI_ML.value,
    "RAG": ContributionCategory.RAG_AND_RETRIEVAL.value,
    "OCR": ContributionCategory.OCR_AND_DOCUMENT_PROCESSING.value,
    "Infrastructure": ContributionCategory.INFRASTRUCTURE.value,
    "DevOps": ContributionCategory.DEVOPS.value,
    "Testing": ContributionCategory.TESTING.value,
    "Documentation": ContributionCategory.DOCUMENTATION.value,
    "Bug Fixing": ContributionCategory.BUG_FIXING.value,
    "Security": ContributionCategory.SECURITY.value,
    "Integration": ContributionCategory.INTEGRATION.value,
    "Other": ContributionCategory.OTHER.value,
}


def mask_email(email: str | None) -> str | None:
    """Mask email local-part for users without identity-management permissions."""
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if len(local) <= 1:
        return f"*@{domain}"
    return f"{local[0]}***@{domain}"


def classify_contribution_domains(
    title_or_message: str,
    *,
    paths: list[str] | None = None,
    labels: list[str] | None = None,
    custom_path_rules: dict[str, str] | None = None,
    llm_client: StructuredLLMClient | None = None,
) -> tuple[list[str], str, list[str]]:
    """Classify a contribution into one or more canonical technical work areas.

    Returns `(work_areas, classification_method, evidence_signals)`.
    Never invents contributor identities or ownership.
    """
    matched_areas: list[str] = []
    evidence_signals: list[str] = []

    def _add(area: str, signal: str) -> None:
        if area not in matched_areas:
            matched_areas.append(area)
        if signal not in evidence_signals and len(evidence_signals) < 20:
            evidence_signals.append(signal)

    norm_paths = [p.replace("\\", "/").lower() for p in (paths or []) if isinstance(p, str) and p.strip()]
    if norm_paths:
        # Check optional repo-specific path prefix overrides first
        if custom_path_rules:
            for path in norm_paths:
                for prefix, area in custom_path_rules.items():
                    if prefix.lower() in path:
                        _add(area, f"custom_path:{prefix}->{path}")

        for path in norm_paths:
            if is_explicit_rag_evidence(path):
                _add("RAG", f"path:{path}")
            for area, tokens in _PATH_DOMAIN_RULES:
                if any(tok in path for tok in tokens):
                    _add(area, f"path:{path}")

        if matched_areas:
            return matched_areas, "deterministic_path", evidence_signals

    # Stage 2: Labels, title, commit message, PR description keywords
    combined = " ".join(
        [title_or_message or "", *(labels or []), *norm_paths]
    ).lower()

    if is_explicit_rag_evidence(combined):
        _add("RAG", "keyword:rag_explicit")

    short_by_enum = {v: k for k, v in _CANONICAL_CATEGORY_MAP.items()}
    for category, keywords in _DOMAIN_KEYWORDS:
        for kw in keywords:
            if re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", combined):
                area = short_by_enum.get(category.value, category.value)
                _add(area, f"keyword:{kw}")
                break

    if matched_areas:
        return matched_areas, "deterministic_keyword", evidence_signals

    # Stage 3: Bounded Qwen3 fallback only when explicitly supplied in background jobs
    if llm_client is not None and (title_or_message.strip() or norm_paths):
        try:
            prompt_text = (
                f"Title/Message: {title_or_message[:400]}\n"
                f"Changed Paths: {', '.join(norm_paths[:20]) or 'none'}\n"
                f"Labels: {', '.join(labels or []) or 'none'}"
            )
            res = llm_client.generate_json(
                LLMGenerationRequest(
                    system_prompt=(
                        "Classify this engineering contribution into 1 to 3 work areas from: "
                        "Frontend, Backend, Database, Authentication, API, AI/ML, RAG, OCR, "
                        "DevOps, Infrastructure, Security, Testing, Documentation, Integration, "
                        "Bug Fixing, Other. Return JSON: {\"areas\": [\"...\"], \"reason\": \"...\"}."
                    ),
                    user_prompt=prompt_text,
                    json_schema={
                        "type": "object",
                        "properties": {
                            "areas": {"type": "array", "items": {"type": "string"}},
                            "reason": {"type": "string"},
                        },
                        "required": ["areas"],
                    },
                )
            )
            raw_areas = res.parsed_json.get("areas") if isinstance(res.parsed_json, dict) else None
            if isinstance(raw_areas, list):
                valid = [str(a).strip() for a in raw_areas if str(a).strip() in _CANONICAL_CATEGORY_MAP]
                if valid:
                    return valid[:3], "llm_assisted", [f"llm:{res.parsed_json.get('reason', 'classified')[:160]}"]
        except Exception as exc:
            logger.debug("LLM fallback classification skipped: %s", exc)

    return ["Other"], "unclassified", []


def classify_contribution_domain(
    title_or_message: str,
    paths: list[str] | None = None,
) -> ContributionCategory:
    """Backward-compatible single-category helper mapping to ContributionCategory."""
    areas, _method, _signals = classify_contribution_domains(title_or_message, paths=paths)
    first_area = areas[0] if areas else "Other"
    mapped = _CANONICAL_CATEGORY_MAP.get(first_area, ContributionCategory.OTHER.value)
    try:
        return ContributionCategory(mapped)
    except ValueError:
        return ContributionCategory.OTHER


def evaluate_alignment(
    category: ContributionCategory | str,
    roster_member: TeamRosterMember | None,
    *,
    membership: ProjectMembership | None = None,
    contributor_type: str = ContributorType.UNIDENTIFIED.value,
) -> tuple[ResponsibilityAlignment, str]:
    """Evaluate whether contribution aligns with declared project responsibilities."""
    if contributor_type in {ContributorType.BOT.value, ContributorType.EXTERNAL_CONTRIBUTOR.value}:
        return (
            ResponsibilityAlignment.NOT_APPLICABLE,
            f"Responsibility alignment is not applicable for '{contributor_type}' accounts.",
        )

    declared: list[str] = []
    role_label = ""
    if roster_member is not None:
        declared.extend(r.lower() for r in (roster_member.primary_responsibilities or []))
        declared.extend(c.lower() for c in (roster_member.component_ownership or []))
        role_label = roster_member.role_name or roster_member.full_name
    if membership is not None and membership.responsibility_description:
        declared.append(membership.responsibility_description.lower())

    if roster_member is None and membership is None:
        return (
            ResponsibilityAlignment.UNCERTAIN,
            "Contributor could not be mapped to a confirmed project member or team roster record.",
        )

    if not declared:
        return (
            ResponsibilityAlignment.UNCERTAIN,
            "Confirmed member has no declared responsibilities recorded.",
        )

    cat_val = category.value if isinstance(category, ContributionCategory) else str(category)
    cat_name = cat_val.lower()
    _generic_stop = {"development", "engineering", "processing", "management", "system", "and", "other"}
    cat_words = {
        w for w in re.split(r"[\s/\-_]+", cat_name) if len(w) > 3 and w not in _generic_stop
    }

    for d in declared:
        if cat_name in d or d in cat_name or any(w in d for w in cat_words):
            return (
                ResponsibilityAlignment.ALIGNED,
                f"Observed contribution area '{cat_val}' aligns with declared responsibility '{d[:120]}'.",
            )

    if any(
        re.search(r"\b(fullstack|general|software\s+developer|software\s+engineer|tech\s+lead)\b", d)
        for d in declared
    ):
        return (
            ResponsibilityAlignment.PARTIALLY_ALIGNED,
            f"Observed contribution area '{cat_val}' is broadly compatible with role '{role_label}'.",
        )

    return (
        ResponsibilityAlignment.OUTSIDE_DECLARED_RESPONSIBILITY,
        f"Observed contribution area '{cat_val}' differs from declared responsibilities ({', '.join(declared[:2])}).",
    )


def build_contributor_key(meta: dict[str, Any], primary_id: str) -> str:
    """Compute a deterministic canonical contributor identity key per project."""
    gh_id = meta.get("github_author_id")
    if gh_id is not None and str(gh_id).strip():
        return f"ghid:{str(gh_id).strip()}"
    gh_login = meta.get("github_author_login")
    if isinstance(gh_login, str) and gh_login.strip():
        return f"gh:{gh_login.strip().lower()}"
    git_email = meta.get("git_author_email")
    if isinstance(git_email, str) and git_email.strip():
        return f"email:{git_email.strip().lower()}"
    return f"id:{primary_id.strip().lower()}"


class ContributionAttributionService:
    """Resolves commit/PR author identity, classifies work, and supports human identity review."""

    def __init__(
        self,
        session: Session,
        *,
        llm_client: StructuredLLMClient | None = None,
    ) -> None:
        self._session = session
        self._llm = llm_client
        self._project_cache: dict[uuid.UUID, dict[str, Any]] = {}

    def _get_project_cache(self, project_id: uuid.UUID) -> dict[str, Any]:
        cached = self._project_cache.get(project_id)
        if cached is not None:
            return cached

        roster_members = list(
            self._session.execute(
                select(TeamRosterMember).where(TeamRosterMember.project_id == project_id)
            )
            .scalars()
            .all()
        )
        memberships = list(
            self._session.execute(
                select(ProjectMembership)
                .options(selectinload(ProjectMembership.user))
                .where(
                    ProjectMembership.project_id == project_id,
                    ProjectMembership.status == "active",
                )
            )
            .scalars()
            .all()
        )
        existing_attrs = list(
            self._session.execute(
                select(ContributionAttribution).where(
                    ContributionAttribution.project_id == project_id
                )
            )
            .scalars()
            .all()
        )

        reviewed_statuses = {
            ContributorReviewStatus.CONFIRMED.value,
            ContributorReviewStatus.MARKED_EXTERNAL.value,
            ContributorReviewStatus.MARKED_BOT.value,
        }
        by_ev: dict[uuid.UUID, ContributionAttribution] = {}
        prior_by_key: dict[str, ContributionAttribution] = {}
        prior_by_ident: dict[str, ContributionAttribution] = {}
        for row in existing_attrs:
            by_ev[row.evidence_item_id] = row
            if row.review_status in reviewed_statuses:
                r_key = (row.metadata_json or {}).get("contributor_key")
                if isinstance(r_key, str) and r_key and r_key not in prior_by_key:
                    prior_by_key[r_key] = row
                r_ident = row.contributor_identifier.lower()
                if r_ident not in prior_by_ident:
                    prior_by_ident[r_ident] = row

        user_ids = [m.user_id for m in memberships if m.user_id]
        auth_rows = []
        if user_ids:
            auth_rows = list(
                self._session.execute(
                    select(UserSourceAuthorisation).where(
                        UserSourceAuthorisation.user_id.in_(user_ids),
                        UserSourceAuthorisation.provider == "github",
                        UserSourceAuthorisation.status == "active",
                    )
                )
                .scalars()
                .all()
            )
        gh_login_to_pm: dict[str, ProjectMembership] = {}
        for a in auth_rows:
            if a.external_username:
                matching_pm = next((m for m in memberships if m.user_id == a.user_id), None)
                if matching_pm:
                    gh_login_to_pm[a.external_username.strip().lower()] = matching_pm

        cached = {
            "roster_members": roster_members,
            "memberships": memberships,
            "gh_login_to_pm": gh_login_to_pm,
            "by_ev": by_ev,
            "prior_by_key": prior_by_key,
            "prior_by_ident": prior_by_ident,
        }
        self._project_cache[project_id] = cached
        return cached

    def attribute_evidence(
        self,
        evidence: EvidenceItem,
        *,
        custom_path_rules: dict[str, str] | None = None,
        flush: bool = True,
    ) -> ContributionAttribution | None:
        if evidence.category not in ("commit", "pull_request", "issue"):
            return None

        meta = dict(evidence.metadata_json or {})
        gh_login = str(meta.get("github_author_login") or "").strip() or None
        gh_id = str(meta.get("github_author_id") or "").strip() or None
        gh_type = str(meta.get("github_author_type") or "").strip() or None
        git_email = str(meta.get("git_author_email") or "").strip() or None
        git_name = str(meta.get("git_author_name") or evidence.source_author_identity or "").strip() or None
        primary_id = gh_login or git_email or git_name or evidence.source_author_identity
        if not primary_id:
            return None

        contributor_key = build_contributor_key(meta, primary_id)
        is_bot, bot_basis = is_bot_identity(
            login=gh_login,
            name=git_name,
            email=git_email,
            provider_type=gh_type,
        )

        # Load cached roster members, active memberships, and existing attributions once per project
        proj_cache = self._get_project_cache(evidence.project_id)
        roster_members: list[TeamRosterMember] = proj_cache["roster_members"]
        memberships: list[ProjectMembership] = proj_cache["memberships"]

        prior_for_key: ContributionAttribution | None = (
            proj_cache["prior_by_key"].get(contributor_key)
            or proj_cache["prior_by_ident"].get(primary_id.lower())
        )

        matched_member: TeamRosterMember | None = None
        matched_membership: ProjectMembership | None = None
        suggested_member_id: str | None = None
        suggested_membership_id: str | None = None
        match_method: str = IdentityMatchMethod.UNMATCHED.value
        match_confidence: float = 0.0
        contributor_type: str = ContributorType.UNIDENTIFIED.value
        review_status: str = ContributorReviewStatus.PENDING.value

        if is_bot:
            contributor_type = ContributorType.BOT.value
            review_status = ContributorReviewStatus.MARKED_BOT.value
            match_method = bot_basis or "bot_naming_pattern"
            match_confidence = 0.98
        elif prior_for_key is not None:
            contributor_type = prior_for_key.contributor_type
            review_status = prior_for_key.review_status
            matched_membership_id = prior_for_key.matched_project_membership_id
            matched_roster_id = prior_for_key.matched_roster_member_id
            if matched_membership_id:
                matched_membership = next((m for m in memberships if m.id == matched_membership_id), None)
            if matched_roster_id:
                matched_member = next((r for r in roster_members if r.id == matched_roster_id), None)
            match_method = prior_for_key.match_method or "human_reviewed"
            match_confidence = float(prior_for_key.match_confidence or 1.0)
        else:
            # 1. Exact verified GitHub numeric ID
            if gh_id:
                for rm in roster_members:
                    rm_gh_id = str((rm.metadata_json or {}).get("github_user_id") or "").strip()
                    if rm_gh_id and rm_gh_id == gh_id:
                        matched_member = rm
                        match_method = IdentityMatchMethod.EXACT_GITHUB_ID.value
                        match_confidence = 1.0
                        break

            # 2. Exact confirmed GitHub username match
            if not matched_member and gh_login:
                for rm in roster_members:
                    if rm.github_username and rm.github_username.lower() == gh_login.lower():
                        matched_member = rm
                        match_method = IdentityMatchMethod.EXACT_GITHUB_USERNAME.value
                        match_confidence = 1.0
                        break
                if not matched_member and not matched_membership:
                    gh_login_to_pm = proj_cache.get("gh_login_to_pm") or {}
                    if gh_login.lower() in gh_login_to_pm:
                        matched_membership = gh_login_to_pm[gh_login.lower()]
                        match_method = "github_authorisation_mapping"
                        match_confidence = 1.0

            # 3. Exact verified Git commit email match (roster or active ProjectMembership user)
            if not matched_member and git_email:
                for rm in roster_members:
                    rm_emails = {
                        e.lower() for e in (rm.email, rm.git_commit_email) if isinstance(e, str) and e.strip()
                    }
                    if git_email.lower() in rm_emails:
                        matched_member = rm
                        match_method = "exact_git_commit_email"
                        match_confidence = 0.95
                        break
                if not matched_member:
                    for pm in memberships:
                        if pm.user and pm.user.email and pm.user.email.lower() == git_email.lower():
                            matched_membership = pm
                            match_method = "exact_git_commit_email"
                            match_confidence = 0.95
                            break

            # 4. GitHub noreply email mapping (against reconciled roster member)
            if not matched_member and not matched_membership and git_email and "users.noreply.github.com" in git_email.lower():
                local_part = git_email.lower().split("@")[0]
                noreply_username = local_part.split("+")[-1] if "+" in local_part else local_part
                for rm in roster_members:
                    if rm.github_username and rm.github_username.lower() == noreply_username:
                        matched_member = rm
                        match_method = "github_noreply_email_mapping"
                        match_confidence = 0.95
                        break

            if matched_member is not None and matched_membership is None and matched_member.matched_project_membership_id:
                matched_membership = next(
                    (m for m in memberships if m.id == matched_member.matched_project_membership_id),
                    None,
                )

            if matched_member is not None or matched_membership is not None:
                contributor_type = ContributorType.CONFIRMED_MEMBER.value
                review_status = ContributorReviewStatus.CONFIRMED.value
            elif git_name:
                # 5. Display-name similarity MUST remain an unverified candidate requiring human review
                for rm in roster_members:
                    if rm.full_name and rm.full_name.strip().lower() == git_name.lower():
                        suggested_member_id = str(rm.id)
                        suggested_membership_id = str(rm.matched_project_membership_id) if rm.matched_project_membership_id else None
                        match_method = "ambiguous_name"
                        match_confidence = 0.50
                        break
                for pm in memberships:
                    if pm.user and pm.user.full_name and pm.user.full_name.strip().lower() == git_name.lower():
                        suggested_membership_id = str(pm.id)
                        match_method = "ambiguous_name"
                        match_confidence = 0.50
                        break

        # Extract changed file paths & labels for path-based classification
        raw_files = meta.get("changed_files") or []
        changed_paths = [
            str(f["filename"])
            for f in raw_files
            if isinstance(f, dict) and f.get("filename")
        ]
        labels = [str(lbl) for lbl in (meta.get("labels") or []) if isinstance(lbl, str)]
        work_areas, class_method, class_signals = classify_contribution_domains(
            f"{evidence.title or ''} {evidence.original_filename or ''}",
            paths=changed_paths,
            labels=labels,
            custom_path_rules=custom_path_rules,
            llm_client=self._llm,
        )
        primary_area = work_areas[0] if work_areas else "Other"
        primary_cat_enum = ContributionCategory(
            _CANONICAL_CATEGORY_MAP.get(primary_area, ContributionCategory.OTHER.value)
        )

        alignment, explanation = evaluate_alignment(
            primary_cat_enum,
            matched_member,
            membership=matched_membership,
            contributor_type=contributor_type,
        )
        if match_method == "ambiguous_name":
            explanation = (
                "Ambiguous name match (unverified candidate requiring human review): "
                + explanation
            )

        gh_login_to_pm = proj_cache.get("gh_login_to_pm") or {}
        repo_name = str(meta.get("repository") or "")
        repo_owner = repo_name.split("/")[0].strip().lower() if "/" in repo_name else None
        directed_by_pm: ProjectMembership | None = gh_login_to_pm.get(repo_owner) if repo_owner else None

        attr_meta = {
            "title": evidence.title,
            "contributor_key": contributor_key,
            "repository": meta.get("repository"),
            "github_author_login": gh_login,
            "github_author_id": gh_id,
            "github_author_type": gh_type,
            "git_author_name": git_name,
            "git_author_email": git_email,
            "co_authors": meta.get("co_authors") or [],
            "work_areas": work_areas,
            "classification_method": class_method,
            "classification_evidence": class_signals,
            "changed_files_count": len(changed_paths),
            "changed_files": changed_paths[:30],
            "suggested_roster_member_id": suggested_member_id,
            "suggested_project_membership_id": suggested_membership_id,
        }
        if is_bot:
            attr_meta["attribution_classification"] = "tool_associated"
            if directed_by_pm:
                attr_meta["directed_by_pm_id"] = str(directed_by_pm.id)
                attr_meta["directed_by_name"] = directed_by_pm.user.full_name if directed_by_pm.user else repo_owner
                attr_meta["directed_by_login"] = repo_owner
                attr_meta["human_director"] = attr_meta["directed_by_name"]

        by_ev: dict[uuid.UUID, ContributionAttribution] = proj_cache["by_ev"]
        existing_attr: ContributionAttribution | None = by_ev.get(evidence.id)

        matched_membership_id = matched_membership.id if matched_membership else (
            matched_member.matched_project_membership_id if matched_member else None
        )
        candidate_roster_id = (
            uuid.UUID(suggested_member_id)
            if matched_member is None and suggested_member_id and match_method == "ambiguous_name"
            else None
        )
        persisted_roster_member_id = matched_member.id if matched_member else candidate_roster_id

        if existing_attr is not None:
            if existing_attr.contributor_identifier != primary_id:
                existing_attr.contributor_identifier = primary_id
            new_ident_type = "github_login" if gh_login else "git_email" if git_email else "name"
            if existing_attr.identifier_type != new_ident_type:
                existing_attr.identifier_type = new_ident_type
            # Preserve manual human review decisions unless re-run explicitly confirms
            if existing_attr.review_status == ContributorReviewStatus.PENDING.value or is_bot:
                if existing_attr.contributor_type != contributor_type:
                    existing_attr.contributor_type = contributor_type
                if existing_attr.review_status != review_status:
                    existing_attr.review_status = review_status
                if existing_attr.matched_roster_member_id != persisted_roster_member_id:
                    existing_attr.matched_roster_member_id = persisted_roster_member_id
                if existing_attr.matched_project_membership_id != matched_membership_id:
                    existing_attr.matched_project_membership_id = matched_membership_id
                if existing_attr.match_method != match_method:
                    existing_attr.match_method = match_method
                if float(existing_attr.match_confidence or 0.0) != float(match_confidence):
                    existing_attr.match_confidence = match_confidence
            if existing_attr.contribution_category != primary_cat_enum.value:
                existing_attr.contribution_category = primary_cat_enum.value
            if existing_attr.responsibility_alignment != alignment.value:
                existing_attr.responsibility_alignment = alignment.value
            if existing_attr.alignment_explanation != explanation:
                existing_attr.alignment_explanation = explanation
            prev_history = (existing_attr.metadata_json or {}).get("review_history")
            if prev_history:
                attr_meta["review_history"] = prev_history
            if existing_attr.metadata_json != attr_meta:
                existing_attr.metadata_json = attr_meta
            attr = existing_attr
        else:
            attr = ContributionAttribution(
                id=uuid.uuid4(),
                project_id=evidence.project_id,
                evidence_item_id=evidence.id,
                contributor_identifier=primary_id,
                identifier_type="github_login" if gh_login else "git_email" if git_email else "name",
                matched_roster_member_id=persisted_roster_member_id,
                matched_project_membership_id=matched_membership_id,
                match_method=match_method,
                match_confidence=match_confidence,
                contribution_category=primary_cat_enum.value,
                responsibility_alignment=alignment.value,
                alignment_explanation=explanation,
                contributor_type=contributor_type,
                review_status=review_status,
                metadata_json=attr_meta,
            )
            self._session.add(attr)
            proj_cache["by_ev"][evidence.id] = attr

        if attr.review_status in {
            ContributorReviewStatus.CONFIRMED.value,
            ContributorReviewStatus.MARKED_EXTERNAL.value,
            ContributorReviewStatus.MARKED_BOT.value,
        }:
            proj_cache["prior_by_key"].setdefault(contributor_key, attr)
            proj_cache["prior_by_ident"].setdefault(primary_id.lower(), attr)

        if flush:
            self._session.flush()
        return attr

    def list_contributor_identities(
        self,
        *,
        project_id: uuid.UUID,
        accessible_evidence_ids: set[uuid.UUID],
        has_project_manage: bool,
        contributor_type_filter: str | None = None,
        review_status_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Aggregate contributor identities across accessible ContributionAttribution records."""
        rows = list(
            self._session.execute(
                select(ContributionAttribution)
                .options(
                    selectinload(ContributionAttribution.evidence_item).defer(
                        EvidenceItem.metadata_json
                    )
                )
                .where(ContributionAttribution.project_id == project_id)
            )
            .scalars()
            .all()
        )
        memberships = list(
            self._session.execute(
                select(ProjectMembership)
                .options(selectinload(ProjectMembership.user), selectinload(ProjectMembership.role))
                .where(ProjectMembership.project_id == project_id, ProjectMembership.status == "active")
            )
            .scalars()
            .all()
        )
        pm_by_id = {pm.id: pm for pm in memberships}
        roster_rows = list(
            self._session.execute(
                select(TeamRosterMember).where(TeamRosterMember.project_id == project_id)
            )
            .scalars()
            .all()
        )
        roster_by_id = {r.id: r for r in roster_rows}

        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            if row.evidence_item_id not in accessible_evidence_ids:
                continue
            meta = row.metadata_json or {}
            ckey = str(meta.get("contributor_key") or f"id:{row.contributor_identifier.lower()}")
            entry = grouped.get(ckey)
            if entry is None:
                raw_email = meta.get("git_author_email")
                matched_pm = pm_by_id.get(row.matched_project_membership_id) if row.matched_project_membership_id else None
                matched_roster_id = getattr(row, "matched_roster_member_id", None)
                matched_roster = roster_by_id.get(matched_roster_id) if matched_roster_id else None
                has_match = matched_pm is not None or matched_roster is not None
                effective_pm_id = str(matched_pm.id) if matched_pm is not None else None
                effective_ctype = (
                    row.contributor_type
                    if (row.contributor_type != ContributorType.CONFIRMED_MEMBER.value or has_match)
                    else ContributorType.UNIDENTIFIED.value
                )
                effective_rstatus = (
                    row.review_status
                    if (row.contributor_type != ContributorType.CONFIRMED_MEMBER.value or has_match)
                    else ContributorReviewStatus.PENDING.value
                )
                suggested_pm_id = meta.get("suggested_project_membership_id")
                suggested_pm = pm_by_id.get(uuid.UUID(suggested_pm_id)) if suggested_pm_id else None
                entry = {
                    "contributor_key": ckey,
                    "display_name": (
                        matched_pm.user.full_name
                        if matched_pm and matched_pm.user
                        else (
                            matched_roster.display_name
                            if matched_roster
                            else (meta.get("git_author_name") or row.contributor_identifier)
                        )
                    ),
                    "github_login": meta.get("github_author_login"),
                    "github_numeric_id": meta.get("github_author_id"),
                    "git_author_name": meta.get("git_author_name"),
                    "git_author_email": raw_email if has_project_manage else mask_email(raw_email),
                    "_raw_git_email": raw_email,
                    "contributor_type": effective_ctype,
                    "review_status": effective_rstatus,
                    "match_method": row.match_method if has_match or row.contributor_type != ContributorType.CONFIRMED_MEMBER.value else "member_removed",
                    "match_confidence": row.match_confidence,
                    "matched_project_membership_id": effective_pm_id,
                    "matched_member_name": (
                        matched_pm.user.full_name
                        if matched_pm and matched_pm.user
                        else (f"{matched_roster.display_name} (Invited)" if matched_roster else None)
                    ),
                    "suggested_project_membership_id": str(suggested_pm.id) if suggested_pm else None,
                    "suggested_member_name": suggested_pm.user.full_name if suggested_pm and suggested_pm.user else None,
                    "declared_responsibility": matched_pm.responsibility_description if matched_pm else None,
                    "contribution_count": 0,
                    "commits_count": 0,
                    "prs_count": 0,
                    "issues_count": 0,
                    "repositories": set(),
                    "work_areas": set(),
                    "evidence_ids": [],
                    "review_history": list(meta.get("review_history") or []),
                }
                grouped[ckey] = entry

            entry["contribution_count"] += 1
            ev_cat = (row.evidence_item.category if row.evidence_item else "").lower()
            if ev_cat == "commit":
                entry["commits_count"] += 1
            elif ev_cat == "pull_request":
                entry["prs_count"] += 1
            else:
                entry["issues_count"] += 1
            if meta.get("repository"):
                entry["repositories"].add(str(meta["repository"]))
            for wa in meta.get("work_areas") or ([row.contribution_category] if row.contribution_category else []):
                if wa:
                    wa_str = str(wa)
                    # Filter out historical substring false-positive RAG labels unless explicit RAG evidence exists
                    if wa_str in ("RAG", ContributionCategory.RAG_AND_RETRIEVAL.value):
                        ev_title = row.evidence_item.title if row.evidence_item else ""
                        if not is_explicit_rag_evidence(ev_title) and meta.get("classification_method") in ("deterministic_path", "deterministic_keyword", None):
                            continue
                    entry["work_areas"].add(wa_str)
            entry["evidence_ids"].append(str(row.evidence_item_id))

            if row.contributor_type == ContributorType.BOT.value or is_bot_identity(
                login=meta.get("github_author_login"),
                name=meta.get("git_author_name"),
                email=meta.get("git_author_email"),
            )[0]:
                raw_name = (meta.get("git_author_name") or row.contributor_identifier).lower()
                if "lovable" in raw_name or "gpt-engineer" in raw_name or "lovable" in ckey.lower():
                    clean_display = "Lovable (AI Tool)"
                elif "[bot]" in raw_name:
                    clean_display = f"{meta.get('git_author_name') or row.contributor_identifier} (AI Tool)"
                else:
                    clean_display = f"{meta.get('git_author_name') or row.contributor_identifier} (Bot)"
                entry["display_name"] = clean_display
                entry["contributor_type"] = ContributorType.BOT.value
                entry["review_status"] = ContributorReviewStatus.MARKED_BOT.value
                entry["identity_note"] = "Tool-Associated Code Generation (AI Assistant)"

        # Tier A — Confirmed project members must always be represented even with 0 direct commits
        matched_pm_ids: set[uuid.UUID] = set()
        for entry in grouped.values():
            mid = entry.get("matched_project_membership_id")
            if mid:
                try:
                    matched_pm_ids.add(uuid.UUID(str(mid)))
                except (ValueError, TypeError):
                    pass

        user_ids = [m.user_id for m in memberships if m.user_id]
        auth_rows = list(
            self._session.execute(
                select(UserSourceAuthorisation).where(
                    UserSourceAuthorisation.user_id.in_(user_ids),
                    UserSourceAuthorisation.provider == "github",
                    UserSourceAuthorisation.status == "active",
                )
            )
            .scalars()
            .all()
        ) if user_ids else []
        user_to_gh = {a.user_id: a.external_username.strip() for a in auth_rows if a.external_username}

        # Offer genuine candidate suggestions for unmatched contributors using exact GitHub login or verified email
        for entry in grouped.values():
            if entry.get("matched_project_membership_id") or entry.get("suggested_project_membership_id"):
                continue
            if entry.get("contributor_type") == ContributorType.BOT.value:
                continue
            c_login = (entry.get("github_login") or "").strip().lower()
            c_email = (entry.get("_raw_git_email") or "").strip().lower()
            for pm in memberships:
                pm_gh = (user_to_gh.get(pm.user_id) or "").strip().lower()
                pm_email = (pm.user.email or "").strip().lower() if pm.user and pm.user.email else ""
                if (c_login and pm_gh and c_login == pm_gh) or (
                    c_email and pm_email and "noreply.github.com" not in c_email and c_email == pm_email
                ):
                    entry["suggested_project_membership_id"] = str(pm.id)
                    entry["suggested_member_name"] = pm.user.full_name if pm.user else None
                    break

        # Collect assisted / directed work for confirmed members ONLY from tool-associated / bot commits
        directed_stats_by_pm: dict[uuid.UUID, dict[str, Any]] = defaultdict(lambda: {
            "assisted_commits": 0,
            "work_areas": set(),
            "repositories": set(),
            "evidence_ids": [],
        })
        for row in rows:
            if row.evidence_item_id not in accessible_evidence_ids:
                continue
            meta = row.metadata_json or {}
            # Only count directed work if the row is from a bot / AI tool
            is_bot = (
                row.contributor_type == ContributorType.BOT.value
                or meta.get("attribution_classification") == "tool_associated"
            )
            if not is_bot:
                continue
            d_pm_id = meta.get("directed_by_pm_id")
            if d_pm_id:
                try:
                    pm_uuid = uuid.UUID(str(d_pm_id))
                    stats = directed_stats_by_pm[pm_uuid]
                    stats["assisted_commits"] += 1
                    if meta.get("repository"):
                        stats["repositories"].add(str(meta["repository"]))
                    for wa in meta.get("work_areas") or []:
                        stats["work_areas"].add(str(wa))
                    stats["evidence_ids"].append(str(row.evidence_item_id))
                except (ValueError, TypeError):
                    pass

        for pm in memberships:
            ckey = f"member:{pm.id}"
            gh_handle = user_to_gh.get(pm.user_id)
            if pm.id not in matched_pm_ids:
                raw_email = pm.user.email if pm.user else None
                role_name = pm.role.name if getattr(pm, "role", None) else "project_member"
                role_label = role_name.replace("_", " ").title()
                entry = grouped.get(ckey)
                if entry is None:
                    entry = {
                        "contributor_key": ckey,
                        "display_name": pm.user.full_name if pm.user else f"Member {pm.id}",
                        "github_login": gh_handle,
                        "github_numeric_id": None,
                        "git_author_name": None,
                        "git_author_email": raw_email if has_project_manage else mask_email(raw_email),
                        "contributor_type": ContributorType.CONFIRMED_MEMBER.value,
                        "review_status": ContributorReviewStatus.CONFIRMED.value if gh_handle else ContributorReviewStatus.PENDING.value,
                        "match_method": "direct_membership" if gh_handle else "pending_identity",
                        "match_confidence": 1.0 if gh_handle else 0.0,
                        "matched_project_membership_id": str(pm.id),
                        "matched_member_name": pm.user.full_name if pm.user else None,
                        "suggested_project_membership_id": None,
                        "suggested_member_name": None,
                        "declared_responsibility": pm.responsibility_description or (f"{role_label} · GitHub @{gh_handle}" if gh_handle else f"{role_label} · GitHub identity not linked"),
                        "contribution_count": 0,
                        "commits_count": 0,
                        "prs_count": 0,
                        "issues_count": 0,
                        "repositories": set(),
                        "work_areas": {pm.responsibility_description} if pm.responsibility_description else {"Unassigned"},
                        "evidence_ids": [],
                        "review_history": [],
                        "identity_note": f"Confirmed Member · GitHub @{gh_handle}" if gh_handle else "Project member · GitHub identity not linked",
                    }
                    grouped[ckey] = entry

            entry = grouped.get(ckey) or next(
                (e for e in grouped.values() if e.get("matched_project_membership_id") == str(pm.id)),
                None,
            )
            if entry is not None and pm.id in directed_stats_by_pm:
                d_stats = directed_stats_by_pm[pm.id]
                entry["assisted_commits_count"] = d_stats["assisted_commits"]
                entry["contribution_count"] = entry.get("contribution_count", 0) + d_stats["assisted_commits"]
                entry["repositories"] = entry["repositories"] | d_stats["repositories"]
                entry["work_areas"] = (entry["work_areas"] - {"Unassigned"}) | d_stats["work_areas"]
                entry["evidence_ids"] = list(set(entry["evidence_ids"] + d_stats["evidence_ids"]))
                if gh_handle:
                    entry["github_login"] = gh_handle
                entry["declared_responsibility"] = "Repository Owner & Technical Lead (Human-Directed / AI-Assisted)"
                entry["identity_note"] = f"Confirmed Member · Directed {d_stats['assisted_commits']} AI-assisted contributions"
                entry["attribution_category"] = "human_directed"

        results: list[dict[str, Any]] = []
        for entry in grouped.values():
            entry.pop("_raw_git_email", None)
            if contributor_type_filter and entry["contributor_type"] != contributor_type_filter:
                continue
            if review_status_filter and entry["review_status"] != review_status_filter:
                continue
            entry["repositories"] = sorted(entry["repositories"])
            entry["work_areas"] = sorted(entry["work_areas"])
            results.append(entry)

        results.sort(key=lambda x: (-x["contribution_count"], x["display_name"].lower()))
        return results

    def list_selectable_members(
        self,
        *,
        project_id: uuid.UUID,
        has_project_manage: bool,
    ) -> list[dict[str, Any]]:
        """Return canonical selectable members for Identity Review across:
        1. Active project memberships
        2. Active organisation memberships in the project's organisation
        3. Pending project/organisation invitations (clearly labelled, not auto-accepted)
        4. Unreconciled team roster entries (clearly labelled)
        """
        project = self._session.get(Project, project_id)
        if project is None:
            return []

        memberships = list(
            self._session.execute(
                select(ProjectMembership)
                .options(selectinload(ProjectMembership.user), selectinload(ProjectMembership.role))
                .where(ProjectMembership.project_id == project_id, ProjectMembership.status == "active")
            )
            .scalars()
            .all()
        )
        org_memberships = list(
            self._session.execute(
                select(OrganisationMembership)
                .options(selectinload(OrganisationMembership.user), selectinload(OrganisationMembership.role))
                .where(
                    OrganisationMembership.organisation_id == project.organisation_id,
                    OrganisationMembership.status == "active",
                )
            )
            .scalars()
            .all()
        )
        invitations = list(
            self._session.execute(
                select(OrganisationInvitation)
                .options(selectinload(OrganisationInvitation.role))
                .where(
                    OrganisationInvitation.organisation_id == project.organisation_id,
                    OrganisationInvitation.status == "pending",
                    (OrganisationInvitation.project_id == project_id) | (OrganisationInvitation.project_id.is_(None)),
                )
            )
            .scalars()
            .all()
        )
        roster_rows = list(
            self._session.execute(
                select(TeamRosterMember).where(TeamRosterMember.project_id == project_id)
            )
            .scalars()
            .all()
        )

        all_user_ids = list({
            *(pm.user_id for pm in memberships if pm.user_id),
            *(om.user_id for om in org_memberships if om.user_id),
        })
        auth_rows = list(
            self._session.execute(
                select(UserSourceAuthorisation).where(
                    UserSourceAuthorisation.user_id.in_(all_user_ids),
                    UserSourceAuthorisation.provider == "github",
                    UserSourceAuthorisation.status == "active",
                )
            )
            .scalars()
            .all()
        ) if all_user_ids else []
        user_to_gh = {a.user_id: a.external_username.strip() for a in auth_rows if a.external_username}

        results: list[dict[str, Any]] = []
        seen_user_ids: set[uuid.UUID] = set()
        seen_emails: set[str] = set()

        for pm in memberships:
            if pm.user_id:
                seen_user_ids.add(pm.user_id)
            raw_email = pm.user.email if pm.user else None
            if raw_email:
                seen_emails.add(raw_email.strip().lower())
            gh = user_to_gh.get(pm.user_id)
            results.append({
                "selection_key": f"pm:{pm.id}",
                "member_source": "project_membership",
                "membership_state": "active",
                "selectable_for_match": True,
                "project_membership_id": pm.id,
                "user_id": pm.user_id,
                "invitation_id": None,
                "roster_member_id": None,
                "display_name": pm.user.full_name if pm.user and pm.user.full_name else (raw_email or "Project Member"),
                "email": raw_email if has_project_manage else mask_email(raw_email),
                "role_name": pm.role.name if getattr(pm, "role", None) else "project_member",
                "github_login": gh,
                "review_status": "linked" if gh else "pending_identity",
                "note": f"Active project member · GitHub @{gh}" if gh else "Active project member · Not linked to GitHub",
            })

        for om in org_memberships:
            if om.user_id in seen_user_ids:
                continue
            seen_user_ids.add(om.user_id)
            raw_email = om.user.email if om.user else None
            if raw_email:
                seen_emails.add(raw_email.strip().lower())
            gh = user_to_gh.get(om.user_id)
            results.append({
                "selection_key": f"org_user:{om.user_id}",
                "member_source": "organisation_membership",
                "membership_state": "org_member_unassigned",
                "selectable_for_match": False,
                "project_membership_id": None,
                "user_id": om.user_id,
                "invitation_id": None,
                "roster_member_id": None,
                "display_name": om.user.full_name if om.user and om.user.full_name else (raw_email or "Organisation Member"),
                "email": raw_email if has_project_manage else mask_email(raw_email),
                "role_name": om.role.name if getattr(om, "role", None) else "org_member",
                "github_login": gh,
                "review_status": "org_member_unassigned",
                "note": "Organisation member · Not yet a project member (add via Project Team first)",
            })

        for inv in invitations:
            inv_email = (inv.email or "").strip().lower()
            if inv_email and inv_email in seen_emails:
                continue
            if inv_email:
                seen_emails.add(inv_email)
            local_name = inv.email.split("@", 1)[0] if inv.email and "@" in inv.email else (inv.email or "Invited User")
            results.append({
                "selection_key": f"inv:{inv.id}",
                "member_source": "invitation",
                "membership_state": "invited",
                "selectable_for_match": True,
                "project_membership_id": None,
                "user_id": None,
                "invitation_id": inv.id,
                "roster_member_id": None,
                "display_name": local_name,
                "email": inv.email if has_project_manage else mask_email(inv.email),
                "role_name": inv.role.name if getattr(inv, "role", None) else "invited_member",
                "github_login": None,
                "review_status": "invited",
                "note": "Pending invitation · Match records attribution only (does not grant project access)",
            })

        for tr in roster_rows:
            if tr.matched_user_id and tr.matched_user_id in seen_user_ids:
                continue
            tr_email = (tr.email or "").strip().lower()
            if tr_email and tr_email in seen_emails:
                continue
            if tr_email:
                seen_emails.add(tr_email)
            results.append({
                "selection_key": f"roster:{tr.id}",
                "member_source": "team_roster",
                "membership_state": "roster_only",
                "selectable_for_match": False,
                "project_membership_id": None,
                "user_id": tr.matched_user_id,
                "invitation_id": None,
                "roster_member_id": tr.id,
                "display_name": tr.display_name,
                "email": tr.email if has_project_manage else mask_email(tr.email),
                "role_name": tr.role_title or "roster_member",
                "github_login": tr.github_handle,
                "review_status": "roster_only",
                "note": "Roster record · Add as active project member before identity matching",
            })

        return results

    def review_contributor_identity(
        self,
        *,
        organisation_id: uuid.UUID,
        project_id: uuid.UUID,
        contributor_key: str,
        action: str,
        reviewer_user_id: uuid.UUID,
        project_membership_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        invitation_id: uuid.UUID | None = None,
        roster_member_id: uuid.UUID | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Apply human identity review decision across matching ContributionAttribution records."""
        rows = list(
            self._session.execute(
                select(ContributionAttribution)
                .options(
                    selectinload(ContributionAttribution.evidence_item).defer(
                        EvidenceItem.metadata_json
                    )
                )
                .where(ContributionAttribution.project_id == project_id)
            )
            .scalars()
            .all()
        )
        ckey_lower = contributor_key.lower()
        matching = [
            r
            for r in rows
            if (r.metadata_json or {}).get("contributor_key") == contributor_key
            or r.contributor_identifier.lower() == ckey_lower
            or f"id:{r.contributor_identifier.lower()}" == ckey_lower
            or (
                (r.metadata_json or {}).get("github_author_id")
                and f"ghid:{(r.metadata_json or {}).get('github_author_id')}" == ckey_lower
            )
            or (
                (r.metadata_json or {}).get("github_author_login")
                and (r.metadata_json or {}).get("github_author_login").lower() == ckey_lower
            )
        ]
        if not matching:
            from app.core.exceptions import NotFoundError

            raise NotFoundError(
                f"Contributor identity '{contributor_key}' not found.",
                code="CONTRIBUTOR_IDENTITY_NOT_FOUND",
            )

        now = utc_now()
        membership: ProjectMembership | None = None
        if action == "match_member":
            if project_membership_id is not None:
                membership = self._session.get(ProjectMembership, project_membership_id)
                if membership is None or membership.project_id != project_id or membership.status != "active":
                    from app.core.exceptions import NotFoundError

                    raise NotFoundError("Active project membership not found.", code="MEMBERSHIP_NOT_FOUND")
            elif invitation_id is not None:
                inv = self._session.execute(
                    select(OrganisationInvitation)
                    .options(selectinload(OrganisationInvitation.role))
                    .where(
                        OrganisationInvitation.id == invitation_id,
                        OrganisationInvitation.organisation_id == organisation_id,
                        OrganisationInvitation.status == "pending",
                        (OrganisationInvitation.project_id == project_id) | (OrganisationInvitation.project_id.is_(None)),
                    )
                ).scalar_one_or_none()
                if inv is None:
                    from app.core.exceptions import NotFoundError

                    raise NotFoundError("Pending invitation not found.", code="INVITATION_NOT_FOUND")
                # Record identity attribution via a project TeamRosterMember without accepting the invitation
                # or creating a ProjectMembership (preserves project access boundary).
                inv_email = (inv.email or "").strip().lower()
                existing_roster = (
                    self._session.execute(
                        select(TeamRosterMember).where(
                            TeamRosterMember.project_id == project_id,
                            func.lower(TeamRosterMember.email) == inv_email,
                        )
                    ).scalar_one_or_none()
                    if inv_email
                    else None
                )
                if existing_roster is None:
                    local_name = inv.email.split("@", 1)[0] if inv.email and "@" in inv.email else (inv.email or "Invited Member")
                    existing_roster = TeamRosterMember(
                        id=uuid.uuid4(),
                        project_id=project_id,
                        display_name=local_name,
                        email=inv.email,
                        role_title=inv.role.name if getattr(inv, "role", None) else "invited_member",
                        notes="Linked from pending organisation invitation via Identity Review",
                        created_by_id=reviewer_user_id,
                    )
                    self._session.add(existing_roster)
                    self._session.flush()
                roster_member_id = existing_roster.id
                project_membership_id = None
            else:
                from app.core.exceptions import BadRequestError

                raise BadRequestError(
                    "Active project_membership_id or pending invitation_id is required. Identity matching cannot implicitly grant project membership."
                )
            new_type = ContributorType.CONFIRMED_MEMBER.value
            new_status = ContributorReviewStatus.CONFIRMED.value
            new_method = "human_confirmed"
            new_conf = 1.0
        elif action == "mark_external":
            new_type = ContributorType.EXTERNAL_CONTRIBUTOR.value
            new_status = ContributorReviewStatus.MARKED_EXTERNAL.value
            new_method = "human_marked_external"
            new_conf = 1.0
            project_membership_id = None
            roster_member_id = None
        elif action == "mark_bot":
            new_type = ContributorType.BOT.value
            new_status = ContributorReviewStatus.MARKED_BOT.value
            new_method = "human_marked_bot"
            new_conf = 1.0
            project_membership_id = None
            roster_member_id = None
        elif action == "leave_unidentified":
            new_type = ContributorType.UNIDENTIFIED.value
            new_status = ContributorReviewStatus.PENDING.value
            new_method = IdentityMatchMethod.UNMATCHED.value
            new_conf = 0.0
            project_membership_id = None
            roster_member_id = None
        elif action == "reject_match":
            new_type = ContributorType.UNIDENTIFIED.value
            new_status = ContributorReviewStatus.REJECTED.value
            new_method = IdentityMatchMethod.UNMATCHED.value
            new_conf = 0.0
            project_membership_id = None
            roster_member_id = None
        elif action == "revert":
            new_type = ContributorType.UNIDENTIFIED.value
            new_status = ContributorReviewStatus.REVERTED.value
            new_method = IdentityMatchMethod.UNMATCHED.value
            new_conf = 0.0
            project_membership_id = None
            roster_member_id = None
        else:
            from app.core.exceptions import BadRequestError

            raise BadRequestError(f"Unsupported contributor review action '{action}'.")

        roster_member = self._session.get(TeamRosterMember, roster_member_id) if roster_member_id else None
        for row in matching:
            meta = dict(row.metadata_json or {})
            meta["contributor_key"] = contributor_key
            history = list(meta.get("review_history") or [])
            history.append(
                {
                    "action": action,
                    "previous_contributor_type": row.contributor_type,
                    "previous_review_status": row.review_status,
                    "previous_membership_id": str(row.matched_project_membership_id) if row.matched_project_membership_id else None,
                    "reviewed_by_user_id": str(reviewer_user_id),
                    "reviewed_at": now.astimezone(UTC).isoformat(),
                    "notes": notes,
                }
            )
            meta["review_history"] = history[-25:]
            row.contributor_type = new_type
            row.review_status = new_status
            row.matched_project_membership_id = project_membership_id
            row.matched_roster_member_id = roster_member_id
            row.match_method = new_method
            row.match_confidence = new_conf
            row.reviewed_by_user_id = reviewer_user_id
            row.reviewed_at = now
            row.review_notes = notes
            row.metadata_json = meta

            alignment, explanation = evaluate_alignment(
                row.contribution_category or ContributionCategory.OTHER.value,
                roster_member,
                membership=membership,
                contributor_type=new_type,
            )
            row.responsibility_alignment = alignment.value
            row.alignment_explanation = explanation

        # Record immutable audit log
        self._session.add(
            AuditLog(
                organisation_id=organisation_id,
                project_id=project_id,
                actor_user_id=reviewer_user_id,
                event_type=f"contributor.identity_{action}",
                resource_type="contribution_attribution",
                resource_id=str(matching[0].id),
                outcome="success",
                event_metadata={
                    "contributor_key": contributor_key,
                    "action": action,
                    "affected_records": len(matching),
                    "matched_project_membership_id": str(project_membership_id) if project_membership_id else None,
                    "notes": notes,
                },
            )
        )
        self._project_cache.pop(project_id, None)
        self._session.flush()
        return {
            "contributor_key": contributor_key,
            "contributor_type": new_type,
            "review_status": new_status,
            "updated_records": len(matching),
        }
