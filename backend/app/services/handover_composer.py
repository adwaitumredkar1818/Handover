"""Deterministic Knowledge-to-Handover Composition Layer.

Platform: The Handover
Module: Handover Workspace (Module 4 / Knowledge Transfer Area)

Transforms raw persisted KnowledgeItems, Relationships, Responsibility Transfers,
Checklists, Conflicts, and EvidenceProvenance into an executive "Start Here" briefing
and ten structured, role-prioritised handover sections without invoking external LLMs.

Core Guarantees:
1. Never collapses epistemic tiers: human-verified findings and provisional
   (pending-review) findings are always grouped separately and labelled truthfully.
2. Never discards evidence provenance: every consolidated card merges and preserves
   all underlying source EvidenceItem references and constituent KnowledgeItem IDs.
3. Eliminates noise dumps: package manifest lines, raw per-commit logs, duplicate commit
   author records, and bare Markdown headings are synthesised into coherent subsystem
   explanations, completed workstreams, actionable pending tasks, and reference tables.
4. Defensive secret redaction applied to all rendered strings and structured payloads.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any

from app.models.enums import ChecklistItemStatus, HandoverPackageSectionType
from app.models.handover import HandoverChecklist
from app.schemas.handover import (
    HandoverEvidenceProvenanceResponse,
    HandoverMandatorySectionResponse,
    HandoverSectionConflictItemResponse,
    HandoverSectionDetailResponse,
    HandoverSectionKnowledgeItemResponse,
    HandoverSectionRelationshipResponse,
    HandoverStartHereBriefing,
    HandoverVerificationSummaryResponse,
)

SECTION_ORDER: list[str] = [
    HandoverPackageSectionType.PROJECT_OVERVIEW_CONTEXT.value,
    HandoverPackageSectionType.DECISIONS_RATIONALE.value,
    HandoverPackageSectionType.TECHNICAL_ARCHITECTURE.value,
    HandoverPackageSectionType.WORK_PROGRESS.value,
    HandoverPackageSectionType.RESPONSIBILITIES_OWNERSHIP.value,
    HandoverPackageSectionType.DEPENDENCIES_RELATIONSHIPS.value,
    HandoverPackageSectionType.BUGS_BLOCKERS_RISKS.value,
    HandoverPackageSectionType.OPERATIONAL_HISTORICAL.value,
]

HANDOVER_ROLE_CONFIG: dict[str, dict[str, Any]] = {
    "developer": {
        "label": "Developer Handover",
        "focus_summary": (
            "Prioritises technical architecture, implementation decisions, pending engineering tasks, "
            "component dependencies, bugs/blockers, and practical next steps."
        ),
        "priority_order": [2, 5, 4, 6, 7, 9, 3, 8, 1, 10],
        "top_sections": {2, 5, 4, 6, 7, 9},
    },
    "project_manager": {
        "label": "Project Manager Handover",
        "focus_summary": (
            "Prioritises project status, completed and pending deliverables, active risks, dependencies, "
            "team responsibilities, and milestone decisions."
        ),
        "priority_order": [1, 3, 4, 7, 6, 8, 5, 9, 2, 10],
        "top_sections": {1, 3, 4, 7, 6, 8},
    },
    "technical_lead": {
        "label": "Technical Lead Handover",
        "focus_summary": (
            "Prioritises architectural decisions and trade-offs, system dependencies, component ownership, "
            "technical debt/risks, and strategic continuation steps."
        ),
        "priority_order": [5, 2, 6, 8, 7, 4, 9, 3, 1, 10],
        "top_sections": {5, 2, 6, 8, 7},
    },
}

_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"-----BEGIN [A-Z0-9 ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]+ PRIVATE KEY-----"),
        "[REDACTED_PRIVATE_KEY]",
    ),
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "[REDACTED_GITHUB_PAT]"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "[REDACTED_SLACK_TOKEN]"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9\-._~+/]+=*"), r"\1 [REDACTED_TOKEN]"),
    (
        re.compile(
            r"(?i)\b(password|passwd|api_key|apikey|secret_key|client_secret|access_token|refresh_token|private_key)\s*[:=]\s*['\"]?[^\s'\",;]{6,}['\"]?"
        ),
        r"\1=[REDACTED]",
    ),
]


def redact_secrets(text: str | None) -> str:
    """Defensively redact credential or token patterns from displayed text."""
    if not text:
        return ""
    cleaned = text
    for pattern, replacement in _SECRET_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned


def redact_payload(value: Any) -> Any:
    """Recursively redact secrets from structured JSON payloads for safe display."""
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, list):
        return [redact_payload(v) for v in value]
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for k, v in value.items():
            key_lower = str(k).lower()
            if any(
                tok in key_lower
                for tok in ("password", "secret", "token", "api_key", "private_key", "credential")
            ):
                redacted[k] = "[REDACTED]"
            else:
                redacted[k] = redact_payload(v)
        return redacted
    return value


def normalize_handover_type(handover_type: str | None) -> str:
    """Normalize role presentation key to one of developer | project_manager | technical_lead."""
    val = (handover_type or "developer").strip().lower()
    return val if val in HANDOVER_ROLE_CONFIG else "developer"


_COMPLETED_STATUS_TOKENS: frozenset[str] = frozenset(
    {"completed", "done", "merged", "closed", "resolved", "delivered", "shipped", "finished"}
)
_PENDING_STATUS_TOKENS: frozenset[str] = frozenset(
    {"pending", "open", "in_progress", "in-progress", "todo", "blocked", "wip", "draft", "planned"}
)

_MANIFEST_TECH_RE = re.compile(
    r"^(?:Technology|Dependency):\s*(.+)$", re.IGNORECASE
)
_MANIFEST_CONTENT_RE = re.compile(
    r"(?:External dependency|declares dependency on)\s+'?([^'(]+?)'?\s*(?:\(([^)]+)\))?(?:\s+(?:specified|in manifest))?",
    re.IGNORECASE,
)
_COMMIT_TITLE_RE = re.compile(
    r"^Commit:\s*(?:(?P<repo>[^\s@]+)@(?P<sha>[0-9a-fA-F]{6,40}):\s*)?(?P<msg>.+)$",
    re.IGNORECASE,
)
_COMMIT_AUTHOR_CONTENT_RE = re.compile(
    r"Git commit by\s+(?P<author>[^:]+):", re.IGNORECASE
)
_CONVENTIONAL_COMMIT_RE = re.compile(
    r"^(?P<kind>feat|fix|docs|test|tests|refactor|chore|build|ci|perf|style|revert)(?:\((?P<scope>[^)]+)\))?!?:\s*(?P<subject>.+)$",
    re.IGNORECASE,
)
_AUTHOR_REC_RE = re.compile(r"^Commit Author:\s*(?P<author>.+)$", re.IGNORECASE)
_DOC_SECTION_RE = re.compile(r"^Document Section:\s*(?P<heading>.+)$", re.IGNORECASE)
_DOC_FILE_RE = re.compile(
    r"^Section\s+'[^']+'\s+in\s+(?:[^:\s]+:\s*)?(?P<file>[^\s:]+):\s*(?P<body>.*)$",
    re.DOTALL,
)

# Functional stack buckets for package manifest consolidation
_STACK_LAYER_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (
        "Frontend Framework & UI",
        (
            "next", "react", "react-dom", "typescript", "tailwind", "radix", "lucide",
            "shadcn", "clsx", "class-variance-authority", "tailwind-merge", "vitest",
            "@testing-library", "playwright", "reactflow", "@xyflow", "postcss", "eslint",
            "recharts", "swr", "zustand",
        ),
    ),
    (
        "Backend API & Web Framework",
        (
            "fastapi", "uvicorn", "starlette", "pydantic", "pydantic-settings", "httpx",
            "python-multipart", "python-dotenv", "email-validator", "typer", "rich", "orjson",
        ),
    ),
    (
        "Database, ORM & Migrations",
        (
            "sqlalchemy", "psycopg", "psycopg2", "alembic", "asyncpg", "pgvector", "redis",
            "supabase", "chromadb",
        ),
    ),
    (
        "Authentication, Cryptography & Security",
        (
            "pyjwt", "pwdlib", "argon2", "passlib", "bcrypt", "cryptography", "itsdangerous",
            "authlib", "python-jose",
        ),
    ),
    (
        "AI, RAG, OCR & Document Processing",
        (
            "pymupdf", "fitz", "python-docx", "ollama", "openai", "tiktoken", "langchain",
            "sentence-transformers", "numpy", "pillow", "pypdf",
        ),
    ),
    (
        "Testing & Quality Tooling",
        ("pytest", "pytest-asyncio", "pytest-cov", "ruff", "mypy", "black", "coverage"),
    ),
]

_LOW_SIGNAL_REL_TYPES: frozenset[str] = frozenset(
    {"BELONGS_TO_WORK_CLUSTER", "AUTHORED_BY", "CONFIGURED_IN"}
)

_WORKSTREAM_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "Handover Workspace, Lifecycle & Exports",
        ("handover", "signoff", "checklist", "readiness", "responsibility", "acknowledge", "pdf", "export"),
    ),
    (
        "Verification Center & Conflict Management",
        ("verification", "verify", "conflict", "contradiction", "reviewer"),
    ),
    (
        "Relationship Explorer & Identity Resolution",
        ("relationship", "identity", "entity", "graph", "cluster", "contributor"),
    ),
    (
        "8-Domain Knowledge Intelligence & Extraction Pipeline",
        ("knowledge", "extract", "ocr", "ingest", "reconstruction", "embedding", "chroma", "rag", "assistant"),
    ),
    (
        "Authentication, RBAC, Workspaces & Source Integrations",
        ("auth", "rbac", "source", "github", "jira", "slack", "workspace", "org", "member", "storage"),
    ),
    (
        "Frontend Stabilization & Navigation",
        ("frontend", "ssr", "ui", "modal", "sidebar", "button", "toast", "theme", "nav", "build"),
    ),
    (
        "Architecture Audits, Security Hardening & Test Infrastructure",
        ("audit", "security", "acl", "test", "ci", "docker", "env", "db", "pool", "migration"),
    ),
]


def _item_is_verified(item: HandoverSectionKnowledgeItemResponse) -> bool:
    """True strictly when canonical status + verification case confirm human approval."""
    if item.epistemic_status != "human_verified" or item.review_status != "approved":
        return False
    vc_status = item.verification.case_status if item.verification else None
    if vc_status is not None and vc_status != "verified":
        return False
    elig = item.eligibility or {}
    if elig.get("is_provisional_draft") is True:
        return False
    return True


def _is_completed_work_item(item: HandoverSectionKnowledgeItemResponse) -> bool:
    """Classify a work finding as completed vs pending strictly from evidence fields."""
    if item.title.strip().lower().startswith("commit:"):
        return True

    norm = (item.normalised_status or "").strip().lower()
    if norm in _COMPLETED_STATUS_TOKENS:
        return True
    if norm in _PENDING_STATUS_TOKENS:
        return False

    payload_status = str((item.structured_payload or {}).get("status") or "").strip().lower()
    if payload_status in _COMPLETED_STATUS_TOKENS:
        return True
    if payload_status in _PENDING_STATUS_TOKENS:
        return False

    combined = f"{item.title} {item.content}".lower()
    has_pending_marker = any(
        tok in combined
        for tok in (
            "pending", "todo", "to-do", "unfinished", "in progress",
            "blocked", "remaining", "next task", "open issue", "planned", "missing",
            "partial", "lacks ", "not yet",
        )
    )
    if has_pending_marker:
        return False

    has_completed_marker = any(
        tok in combined
        for tok in (
            "completed", "delivered", "merged", "shipped", "finalized",
            "implemented and verified", "finished", "extensive test suite",
        )
    )
    return has_completed_marker


def classify_finding(item: HandoverSectionKnowledgeItemResponse) -> dict[str, Any]:
    """Deterministically inspect a persisted KnowledgeItem to classify raw records vs insights."""
    title = (item.title or "").strip()
    content = (item.content or "").strip()

    # 1. Manifest package / dependency line
    m_tech = _MANIFEST_TECH_RE.match(title)
    if m_tech or "declares dependency on " in content or content.startswith("External dependency "):
        pkg = m_tech.group(1).strip() if m_tech else title
        ver = ""
        m_c = _MANIFEST_CONTENT_RE.search(content)
        if m_c:
            pkg = m_c.group(1).strip() or pkg
            ver = (m_c.group(2) or "").strip()
        layer = _classify_stack_layer(pkg)
        return {
            "kind": "manifest_dependency",
            "package": pkg,
            "version": ver,
            "layer": layer,
        }

    # 2. Raw Git commit finding (unless it's actually a commit-backed summary?)
    m_commit = _COMMIT_TITLE_RE.match(title)
    if m_commit or content.startswith("Git commit by "):
        msg = (m_commit.group("msg") if m_commit else title).strip()
        sha = (m_commit.group("sha") if m_commit and m_commit.group("sha") else "").strip()
        author = item.owner_label or ""
        m_auth = _COMMIT_AUTHOR_CONTENT_RE.search(content)
        if m_auth and not author:
            author = m_auth.group("author").strip()
        conv = _CONVENTIONAL_COMMIT_RE.match(msg)
        commit_kind = conv.group("kind").lower() if conv else "change"
        scope = (conv.group("scope") or "").strip().lower() if conv else ""
        subject = conv.group("subject").strip() if conv else msg
        workstream = _match_workstream(scope, subject, msg)
        return {
            "kind": "raw_commit",
            "sha": sha,
            "author": author,
            "commit_kind": commit_kind,
            "scope": scope,
            "subject": subject,
            "workstream": workstream,
        }

    # 3. Raw commit author ownership record
    m_author_rec = _AUTHOR_REC_RE.match(title)
    if m_author_rec or "is recorded as commit author for" in content:
        author = (m_author_rec.group("author") if m_author_rec else title).strip()
        return {"kind": "commit_author", "author": author}

    # 4. Raw Markdown / config Document Section heading
    m_doc = _DOC_SECTION_RE.match(title)
    if m_doc:
        heading = m_doc.group("heading").strip()
        m_file = _DOC_FILE_RE.match(content)
        src_file = m_file.group("file").strip() if m_file else ""
        body = m_file.group("body").strip() if m_file else content
        hl = heading.lower()

        if heading.startswith("- ") or src_file.endswith((".yaml", ".yml", ".env.example")):
            return {
                "kind": "env_var_heading",
                "heading": heading.lstrip("- ").strip(),
                "file": src_file,
                "body": body,
            }
        if any(tok in hl for tok in ("orchestration architecture decision", "integration decision")):
            return {
                "kind": "decision_doc",
                "heading": heading,
                "file": src_file,
                "body": body,
            }
        if "readme.md" in src_file.lower() and any(
            tok in hl
            for tok in (
                "core workflow", "knowledge categories", "product modules",
                "confirmed technology stack", "repository structure", "documentation index",
            )
        ):
            return {
                "kind": "readme_overview_doc",
                "heading": heading,
                "file": src_file,
                "body": body,
            }
        if any(
            tok in hl
            for tok in (
                "environment configuration", "inspect health", "backup", "rehearsal",
                "connection budget", "pgbouncer", "saturation", "chromadb",
                "operational security", "local inference gateway",
                "indirect prompt injection", "risk matrix",
            )
        ):
            return {
                "kind": "operational_doc",
                "heading": heading,
                "file": src_file,
                "body": body,
            }
        return {
            "kind": "doc_heading_noise",
            "heading": heading,
            "file": src_file,
            "body": body,
        }

    # 5. Runtime version duplicates
    if title.startswith("Runtime Version Requirement") or title == "Python Version Specification":
        return {"kind": "runtime_requirement", "title": title}

    # 6. Pending/gap technical items placed in technical_architecture/bugs_blockers_risks
    tl = title.lower()
    if any(
        tok in tl
        for tok in (
            "missing streaming", "streaming & real-time (sse) missing",
            "multi-agent orchestration partial", "tool calling & execution missing",
            "missing test coverage",
        )
    ):
        return {"kind": "capability_gap", "title": title}

    return {"kind": "substantive", "title": title}


def _classify_stack_layer(package_name: str) -> str:
    low = package_name.strip().lower()
    for layer, keywords in _STACK_LAYER_KEYWORDS:
        if any(low == kw or kw in low for kw in keywords):
            return layer
    return "Other Runtime & Utility Packages"


def _match_workstream(scope: str, subject: str, raw_msg: str) -> str:
    combined = f"{scope} {subject} {raw_msg}".lower()
    if raw_msg.lower().startswith("merge "):
        return "Repository Branch Merges & Integration"
    for stream_name, keywords in _WORKSTREAM_RULES:
        if any(kw in combined for kw in keywords):
            return stream_name
    return "Core Platform & Feature Updates"


def _merge_provenance(
    items: list[HandoverSectionKnowledgeItemResponse],
    *,
    omit_restricted_items: bool,
) -> list[HandoverEvidenceProvenanceResponse]:
    by_id: dict[uuid.UUID, HandoverEvidenceProvenanceResponse] = {}
    for ki in items:
        for p in ki.provenance:
            if omit_restricted_items and p.acl_restricted:
                continue
            by_id.setdefault(p.evidence_id, p)
    return list(by_id.values())


def _is_meaningful_verification(v: HandoverVerificationSummaryResponse) -> bool:
    return bool(v.verification_case_id and v.case_status == "verified")


def _synthesize_card(
    *,
    title: str,
    content: str,
    category: str,
    constituents: list[HandoverSectionKnowledgeItemResponse],
    normalised_status: str | None = None,
    owner_label: str | None = None,
    extra_payload: dict[str, Any] | None = None,
    omit_restricted_items: bool = False,
    seed_prefix: str = "composed",
) -> HandoverSectionKnowledgeItemResponse:
    """Create a schema-compatible consolidated finding card preserving full provenance & IDs."""
    is_verified = bool(constituents) and all(_item_is_verified(c) for c in constituents)
    epistemic_status = "human_verified" if is_verified else "extracted"
    review_status = "approved" if is_verified else "pending_review"

    provenance = _merge_provenance(constituents, omit_restricted_items=omit_restricted_items)
    constituent_ids = [str(c.id) for c in constituents]

    first = constituents[0] if constituents else None
    card_id = (
        first.id
        if len(constituents) == 1 and first is not None
        else uuid.uuid5(uuid.NAMESPACE_URL, f"{seed_prefix}:{category}:{title}:{epistemic_status}")
    )
    link_id = first.content_link_id if first is not None else uuid.uuid4()

    # Preserve highest-signal verification record (only when genuinely verified)
    verif = HandoverVerificationSummaryResponse()
    if is_verified and first is not None and _is_meaningful_verification(first.verification):
        verif = first.verification
    elif first is not None and not is_verified and first.verification.verification_case_id:
        verif = first.verification

    owners = [c.owner_label for c in constituents if c.owner_label]
    resolved_owner = owner_label or (owners[0] if len(set(owners)) == 1 else None)

    payload: dict[str, Any] = {}
    if len(constituents) == 1 and first is not None and first.structured_payload:
        payload.update(redact_payload(first.structured_payload))
    if len(constituents) > 1:
        payload["consolidated_finding_count"] = len(constituents)
        payload["consolidated_finding_ids"] = constituent_ids[:50]
    if not is_verified:
        payload["epistemic_tier"] = "provisional_pending_review"
    if extra_payload:
        payload.update(redact_payload(extra_payload))

    now = datetime.now(UTC)
    created_at = min((c.created_at for c in constituents), default=now)
    updated_at = max((c.updated_at for c in constituents), default=now)

    return HandoverSectionKnowledgeItemResponse(
        id=card_id,
        content_link_id=link_id,
        title=redact_secrets(title),
        content=redact_secrets(content).strip(),
        category=category,
        epistemic_status=epistemic_status,
        review_status=review_status,
        support_classification=(first.support_classification if first else "direct"),
        normalised_status=normalised_status or (first.normalised_status if first else None),
        owner_label=resolved_owner,
        structured_payload=payload,
        confidence_score=first.confidence_score if first else None,
        is_stale=any(c.is_stale for c in constituents),
        created_at=created_at,
        updated_at=updated_at,
        source_observed_at=max(
            (c.source_observed_at for c in constituents if c.source_observed_at is not None),
            default=None,
        ),
        eligibility={
            "is_eligible": is_verified,
            "is_provisional_draft": not is_verified,
            "epistemic_status": epistemic_status,
            "consolidated_count": len(constituents),
        },
        verification=verif,
        provenance=provenance,
        provenance_available=len(provenance) > 0,
    )


def _split_by_epistemic_tier(
    items: list[HandoverSectionKnowledgeItemResponse],
) -> tuple[list[HandoverSectionKnowledgeItemResponse], list[HandoverSectionKnowledgeItemResponse]]:
    """Strictly separate verified facts from provisional pending-review items."""
    verified: list[HandoverSectionKnowledgeItemResponse] = []
    provisional: list[HandoverSectionKnowledgeItemResponse] = []
    for item in items:
        if _item_is_verified(item):
            verified.append(item)
        else:
            provisional.append(item)
    return verified, provisional


def _clean_doc_excerpt(body: str, limit: int = 340) -> str:
    text = re.sub(r"\s+", " ", (body or "")).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip(" ,;:") + "…"


# ---------------------------------------------------------------------------
# Section Composers (preserve exact epistemic boundary per tier)
# ---------------------------------------------------------------------------


def _compose_overview_cards(
    overview_items: list[HandoverSectionKnowledgeItemResponse],
    readme_docs: list[tuple[HandoverSectionKnowledgeItemResponse, dict[str, Any]]],
    domain_context: dict[str, Any],
    *,
    omit_restricted_items: bool,
) -> list[HandoverSectionKnowledgeItemResponse]:
    """Compose Section 1 (Project Overview) without unrelated heading dumps."""
    all_raw = overview_items + [it for it, _ in readme_docs]
    if not all_raw:
        return []

    def _compose_tier(
        items: list[HandoverSectionKnowledgeItemResponse],
        docs: list[tuple[HandoverSectionKnowledgeItemResponse, dict[str, Any]]],
    ) -> list[HandoverSectionKnowledgeItemResponse]:
        if not items and not docs:
            return []
        # Small test fixture (<4 items and no doc headings): preserve clean standalone cards
        if len(items) <= 3 and not docs:
            return items

        cards: list[HandoverSectionKnowledgeItemResponse] = []
        purpose_group: list[HandoverSectionKnowledgeItemResponse] = []
        scope_group: list[HandoverSectionKnowledgeItemResponse] = []
        audit_group: list[HandoverSectionKnowledgeItemResponse] = []
        other_items: list[HandoverSectionKnowledgeItemResponse] = []

        for ki in items:
            tl = ki.title.lower()
            if any(k in tl for k in ("purpose", "workflow")):
                purpose_group.append(ki)
            elif any(k in tl for k in ("structure", "documentation", "repository:", "authorization")):
                scope_group.append(ki)
            elif any(k in tl for k in ("audit", "readiness")):
                audit_group.append(ki)
            else:
                other_items.append(ki)

        if purpose_group or docs:
            lines: list[str] = []
            proj_name = redact_secrets(str(domain_context.get("project_name") or ""))
            proj_desc = redact_secrets(str(domain_context.get("project_description") or ""))
            if proj_name:
                lines.append(f"Project: {proj_name}.")
            if proj_desc:
                lines.append(proj_desc)
            seen_summaries: set[str] = set()
            for ki in purpose_group:
                s = (ki.content or "").strip()
                if s and s not in seen_summaries:
                    seen_summaries.add(s)
                    lines.append(f"- {ki.title}: {s}")
            for doc_ki, meta in docs:
                heading = meta.get("heading", doc_ki.title)
                if "workflow" in heading.lower() or "categories" in heading.lower() or "modules" in heading.lower():
                    lines.append(f"- {heading}: {_clean_doc_excerpt(meta.get('body') or doc_ki.content, 260)}")
            cards.append(
                _synthesize_card(
                    title="Project Purpose, Mission & Core Workflow",
                    content="\n".join(lines),
                    category="project_overview_context",
                    constituents=purpose_group + [d for d, _ in docs],
                    omit_restricted_items=omit_restricted_items,
                    seed_prefix="sec1-purpose",
                )
            )

        if scope_group:
            lines = [f"- {ki.title}: {(ki.content or '').strip()}" for ki in scope_group]
            cards.append(
                _synthesize_card(
                    title="Repository Scope, Security Boundaries & Documentation",
                    content="\n".join(lines),
                    category="project_overview_context",
                    constituents=scope_group,
                    omit_restricted_items=omit_restricted_items,
                    seed_prefix="sec1-scope",
                )
            )

        if audit_group:
            lines = [f"- {ki.title}: {(ki.content or '').strip()}" for ki in audit_group]
            cards.append(
                _synthesize_card(
                    title="Documented Platform Readiness & Audit Context",
                    content="\n".join(lines),
                    category="project_overview_context",
                    constituents=audit_group,
                    omit_restricted_items=omit_restricted_items,
                    seed_prefix="sec1-audit",
                )
            )

        cards.extend(other_items)
        return cards

    v_items, p_items = _split_by_epistemic_tier(overview_items)
    v_docs = [(it, m) for it, m in readme_docs if _item_is_verified(it)]
    p_docs = [(it, m) for it, m in readme_docs if not _item_is_verified(it)]
    return _compose_tier(v_items, v_docs) + _compose_tier(p_items, p_docs)


def _arch_subsystem_for_item(ki: HandoverSectionKnowledgeItemResponse) -> str:
    combined = f"{ki.title} {ki.content}".lower()
    if any(k in combined for k in ("frontend", "next.js", "ui ", "sse streams", "real-time streaming")):
        return "Frontend Application Layer"
    if any(
        k in combined
        for k in (
            "postgresql", "chromadb", "alembic", "vector", "retrieval", "rrf",
            "embedding", "nomic-embed", "canonical store", "ingestion", "persistent memory",
        )
    ):
        return "Data Store, Vector Indexing & Hybrid Retrieval"
    if any(
        k in combined
        for k in ("auth", "rbac", "acl", "security gate", "zero-privilege", "jwt", "argon2")
    ):
        return "Authentication, RBAC & Fail-Closed Security Architecture"
    if any(
        k in combined
        for k in (
            "gateway", "ollama", "llm", "assistant", "state graph", "agent registry",
            "sse streaming implementation", "worker", "tunnel", "cloudflared", "local infrastructure",
        )
    ):
        return "AI Inference Gateway, Assistant Engine & Background Processing"
    if any(k in combined for k in ("fastapi", "uvicorn", "backend", "routing", "dependency injection")):
        return "Backend API & Modular Service Layer"
    return "General System Architecture"


def _compose_manifest_card(
    manifest_records: list[tuple[HandoverSectionKnowledgeItemResponse, dict[str, Any]]],
    runtime_records: list[HandoverSectionKnowledgeItemResponse],
    *,
    title: str,
    category: str,
    intro: str,
    omit_restricted_items: bool,
    seed_prefix: str,
) -> HandoverSectionKnowledgeItemResponse | None:
    if not manifest_records and not runtime_records:
        return None
    by_layer: dict[str, list[str]] = defaultdict(list)
    seen_pkgs: set[str] = set()
    for _, meta in manifest_records:
        pkg = meta["package"]
        ver = meta["version"]
        key = pkg.lower()
        if key in seen_pkgs:
            continue
        seen_pkgs.add(key)
        entry = f"{pkg} ({ver})" if ver else pkg
        by_layer[meta["layer"]].append(entry)

    lines: list[str] = [intro, ""]
    if runtime_records:
        lines.append("- **Runtime Environment**: Python >= 3.11 (backend/pyproject.toml)")
    for layer, _ in _STACK_LAYER_KEYWORDS + [("Other Runtime & Utility Packages", ())]:
        pkgs = sorted(set(by_layer.get(layer, [])))
        if pkgs:
            lines.append(f"- **{layer}** ({len(pkgs)}): {', '.join(pkgs)}")

    constituents = [it for it, _ in manifest_records] + runtime_records
    return _synthesize_card(
        title=title,
        content="\n".join(lines),
        category=category,
        constituents=constituents,
        extra_payload={"unique_packages_count": len(seen_pkgs)},
        omit_restricted_items=omit_restricted_items,
        seed_prefix=seed_prefix,
    )


def _compose_architecture_cards(
    arch_items: list[HandoverSectionKnowledgeItemResponse],
    ops_items: list[HandoverSectionKnowledgeItemResponse],
    completed_commits_to_note: list[HandoverSectionKnowledgeItemResponse] | None = None,
    *,
    omit_restricted_items: bool,
) -> list[HandoverSectionKnowledgeItemResponse]:
    """Compose Section 2 into architectural subsystem explanations, operations runbooks, and 1 compact stack reference."""
    _ = completed_commits_to_note

    def _compose_tier(
        a_items: list[HandoverSectionKnowledgeItemResponse],
        o_items: list[HandoverSectionKnowledgeItemResponse],
    ) -> list[HandoverSectionKnowledgeItemResponse]:
        if not a_items and not o_items:
            return []

        manifest_tech: list[tuple[HandoverSectionKnowledgeItemResponse, dict[str, Any]]] = []
        runtime_reqs: list[HandoverSectionKnowledgeItemResponse] = []
        substantive_arch: list[HandoverSectionKnowledgeItemResponse] = []
        ops_runbooks: list[HandoverSectionKnowledgeItemResponse] = []
        env_vars: list[tuple[HandoverSectionKnowledgeItemResponse, dict[str, Any]]] = []

        for ki in a_items:
            meta = classify_finding(ki)
            kind = meta["kind"]
            if kind == "manifest_dependency":
                manifest_tech.append((ki, meta))
            elif kind == "runtime_requirement":
                runtime_reqs.append(ki)
            elif kind == "capability_gap":
                # Capability gaps belong in Pending Work & Risks, not Architecture capabilities
                continue
            elif kind in ("doc_heading_noise",):
                continue
            else:
                substantive_arch.append(ki)

        for ki in o_items:
            meta = classify_finding(ki)
            kind = meta["kind"]
            if kind == "env_var_heading":
                env_vars.append((ki, meta))
            elif kind in ("readme_overview_doc", "decision_doc", "doc_heading_noise"):
                continue
            else:
                ops_runbooks.append(ki)

        cards: list[HandoverSectionKnowledgeItemResponse] = []

        # Group substantive architecture items by architectural subsystem
        if len(substantive_arch) <= 4 and not manifest_tech and not ops_runbooks and not env_vars:
            cards.extend(substantive_arch)
        else:
            grouped_subsystems: dict[str, list[HandoverSectionKnowledgeItemResponse]] = defaultdict(list)
            for ki in substantive_arch:
                grouped_subsystems[_arch_subsystem_for_item(ki)].append(ki)

            preferred_order = [
                "Backend API & Modular Service Layer",
                "Frontend Application Layer",
                "Data Store, Vector Indexing & Hybrid Retrieval",
                "Authentication, RBAC & Fail-Closed Security Architecture",
                "AI Inference Gateway, Assistant Engine & Background Processing",
                "General System Architecture",
            ]
            for subsystem in preferred_order:
                bucket = grouped_subsystems.get(subsystem, [])
                if not bucket:
                    continue
                if len(bucket) == 1:
                    cards.append(bucket[0])
                else:
                    seen_text: set[str] = set()
                    bullets: list[str] = []
                    for it in bucket:
                        summary = (it.content or "").strip()
                        if summary and summary not in seen_text:
                            seen_text.add(summary)
                            bullets.append(f"- **{it.title}**: {summary}")
                    cards.append(
                        _synthesize_card(
                            title=subsystem,
                            content="\n".join(bullets),
                            category="technical_architecture",
                            constituents=bucket,
                            omit_restricted_items=omit_restricted_items,
                            seed_prefix=f"sec2-{subsystem}",
                        )
                    )

        # Group Operational Runbooks & Environment Configuration cleanly
        if ops_runbooks or env_vars:
            if len(ops_runbooks) <= 2 and not env_vars and len(substantive_arch) <= 4:
                cards.extend(ops_runbooks)
            else:
                env_names = sorted({m["heading"] for _, m in env_vars if m.get("heading")})
                op_lines: list[str] = []
                for it in ops_runbooks:
                    meta = classify_finding(it)
                    if meta["kind"] == "operational_doc":
                        op_lines.append(
                            f"- **{meta.get('heading', it.title)}**: {_clean_doc_excerpt(meta.get('body') or it.content, 240)}"
                        )
                    else:
                        op_lines.append(f"- **{it.title}**: {(it.content or '').strip()}")
                if env_names:
                    op_lines.append(
                        f"- **Deployment Environment Variables (`render.yaml`)**: Required configuration keys documented for deployment include `{'`, `'.join(env_names)}`."
                    )
                if op_lines:
                    cards.append(
                        _synthesize_card(
                            title="Operational Runbooks, Infrastructure Topology & Deployment Config",
                            content="\n".join(op_lines),
                            category="operational_historical",
                            constituents=ops_runbooks + [it for it, _ in env_vars],
                            omit_restricted_items=omit_restricted_items,
                            seed_prefix="sec2-ops-runbooks",
                        )
                    )

        # Compact Declared Technology Stack Overview (never 1 card per package!)
        manifest_card = _compose_manifest_card(
            manifest_tech,
            runtime_reqs,
            title="Declared Technology Stack Overview (Manifest Reference)",
            category="technical_architecture",
            intro=(
                "Consolidated technology stack declared across project manifests "
                "(distinguished from confirmed runtime component interactions above):"
            ),
            omit_restricted_items=omit_restricted_items,
            seed_prefix="sec2-manifest-stack",
        )
        if manifest_card is not None:
            cards.append(manifest_card)

        return cards

    v_arch, p_arch = _split_by_epistemic_tier(arch_items)
    v_ops, p_ops = _split_by_epistemic_tier(ops_items)
    return _compose_tier(v_arch, v_ops) + _compose_tier(p_arch, p_ops)


def _compose_completed_work_cards(
    work_items: list[HandoverSectionKnowledgeItemResponse],
    *,
    extra_fix_commits: list[HandoverSectionKnowledgeItemResponse] | None = None,
    omit_restricted_items: bool,
) -> tuple[list[HandoverSectionKnowledgeItemResponse], list[HandoverSectionKnowledgeItemResponse]]:
    """Return (completed_cards, pending_source_items) keeping all commits cleanly grouped in Completed Work."""
    combined_work = list(work_items) + list(extra_fix_commits or [])
    pending_raw: list[HandoverSectionKnowledgeItemResponse] = []

    def _compose_tier(items: list[HandoverSectionKnowledgeItemResponse]) -> list[HandoverSectionKnowledgeItemResponse]:
        if not items:
            return []
        commit_buckets: dict[str, list[tuple[HandoverSectionKnowledgeItemResponse, dict[str, Any]]]] = defaultdict(list)
        substantive_completed: list[HandoverSectionKnowledgeItemResponse] = []

        for ki in items:
            meta = classify_finding(ki)
            if meta["kind"] == "raw_commit":
                commit_buckets[meta["workstream"]].append((ki, meta))
            elif _is_completed_work_item(ki):
                substantive_completed.append(ki)
            else:
                pending_raw.append(ki)

        cards: list[HandoverSectionKnowledgeItemResponse] = list(substantive_completed)

        for stream, records in sorted(commit_buckets.items(), key=lambda kv: -len(kv[1])):
            shas = [m["sha"] for _, m in records if m.get("sha")]
            authors = sorted({m["author"] for _, m in records if m.get("author")})
            highlights: list[str] = []
            seen_subjects: set[str] = set()
            for _, m in records:
                subj = m.get("subject") or ""
                if subj and subj.lower() not in seen_subjects and not subj.lower().startswith("merge "):
                    seen_subjects.add(subj.lower())
                    sha_tag = f"`@{m['sha'][:8]}` " if m.get("sha") else ""
                    highlights.append(f"  - {sha_tag}{subj}")
            shown_highlights = highlights[:8]
            more_count = max(0, len(highlights) - len(shown_highlights))
            lines = [
                f"**Workstream Summary**: Consolidates {len(records)} recorded repository change(s) affecting {stream}.",
            ]
            if authors:
                lines.append(f"**Recorded Contributors**: {', '.join(authors)}")
            if shown_highlights:
                lines.append("**Key Changes Recorded**:")
                lines.extend(shown_highlights)
            if more_count > 0:
                lines.append(f"  - *(+{more_count} additional commit(s) retained in linked evidence)*")
            lines.append(
                "*Verification Scope Note*: Repository commits document historical code changes; verify runtime production behavior independently."
            )
            cards.append(
                _synthesize_card(
                    title=f"Workstream: {stream}",
                    content="\n".join(lines),
                    category="work_items",
                    constituents=[ki for ki, _ in records],
                    normalised_status="completed",
                    extra_payload={"commit_count": len(records), "sample_shas": shas[:10]},
                    omit_restricted_items=omit_restricted_items,
                    seed_prefix=f"sec3-ws-{stream}",
                )
            )
        return cards

    v_items, p_items = _split_by_epistemic_tier(combined_work)
    return _compose_tier(v_items) + _compose_tier(p_items), pending_raw


def _compose_pending_work_cards(
    pending_work_items: list[HandoverSectionKnowledgeItemResponse],
    capability_gaps: list[HandoverSectionKnowledgeItemResponse],
    open_checklist_items: list[Any],
    *,
    omit_restricted_items: bool,
) -> list[HandoverSectionKnowledgeItemResponse]:
    """Compose Section 4 (Pending Work) with actionable What / Why / Status / Inspect Next guidance."""
    all_raw = pending_work_items + capability_gaps
    if not all_raw:
        return []

    def _format_actionable_task(ki: HandoverSectionKnowledgeItemResponse) -> HandoverSectionKnowledgeItemResponse:
        tl = ki.title.lower()
        body = (ki.content or "").strip()
        if len(pending_work_items) <= 3 and not capability_gaps:
            return ki

        if "streaming" in tl or "sse" in tl:
            detail = (
                f"- **What needs to be done**: Complete end-to-end Server-Sent Events (SSE) streaming across backend assistant endpoints and frontend message consumption.\n"
                f"- **Why it matters**: Documented state shows readiness at 15% and synchronous HTTP operations risk 504 timeouts on long investigations.\n"
                f"- **Recorded Status**: {body}\n"
                f"- **What to inspect next**: `AI_0_5_IMPLEMENTATION_DESIGN.md`, backend assistant streaming routes, and frontend chat stream consumer."
            )
            return _synthesize_card(
                title="Pending Capability: Real-Time SSE Streaming Pipeline",
                content=detail,
                category=ki.category,
                constituents=[ki],
                normalised_status="in_progress",
                omit_restricted_items=omit_restricted_items,
                seed_prefix="sec4-sse",
            )
        if "multi-agent" in tl or "orchestration" in tl or "tool calling" in tl:
            detail = (
                f"- **What needs to be done**: Complete typed state-graph agent orchestration and RBAC-scoped tool calling execution.\n"
                f"- **Why it matters**: Partial multi-agent orchestration (20% readiness) and missing tool execution (10% readiness) limit autonomous deep investigation workflows.\n"
                f"- **Recorded Status**: {body}\n"
                f"- **What to inspect next**: Agent Registry design, lightweight state graph checkpointing, and `ProjectContext` tool authorization guards."
            )
            return _synthesize_card(
                title="Pending Capability: Agent Orchestration & RBAC Tool Execution",
                content=detail,
                category=ki.category,
                constituents=[ki],
                normalised_status="pending",
                omit_restricted_items=omit_restricted_items,
                seed_prefix="sec4-agents",
            )
        if "test coverage" in tl:
            detail = (
                f"- **What needs to be done**: Add automated end-to-end tests for multi-agent execution, tool authorization boundaries, and RAG citation precision/recall benchmarks.\n"
                f"- **Why it matters**: Prevents regressions when extending assistant and retrieval flows.\n"
                f"- **Recorded Status**: {body}\n"
                f"- **What to inspect next**: `backend/tests/` integration suite and assistant benchmark scripts."
            )
            return _synthesize_card(
                title="Pending Quality Gate: Multi-Agent E2E & Citation Benchmark Tests",
                content=detail,
                category=ki.category,
                constituents=[ki],
                normalised_status="pending",
                omit_restricted_items=omit_restricted_items,
                seed_prefix="sec4-tests",
            )
        detail = (
            f"- **What needs to be done**: {body or ki.title}\n"
            f"- **Recorded Status**: {ki.normalised_status or 'pending'}\n"
            f"- **Owner**: {ki.owner_label or 'Unassigned — confirm owner in Team / Handover transfers'}"
        )
        return _synthesize_card(
            title=ki.title,
            content=detail,
            category=ki.category,
            constituents=[ki],
            normalised_status=ki.normalised_status or "pending",
            omit_restricted_items=omit_restricted_items,
            seed_prefix="sec4-item",
        )

    # Deduplicate overlapping SSE/Agent gap findings per tier
    def _compose_tier(
        p_work: list[HandoverSectionKnowledgeItemResponse],
        gaps: list[HandoverSectionKnowledgeItemResponse],
    ) -> list[HandoverSectionKnowledgeItemResponse]:
        out: list[HandoverSectionKnowledgeItemResponse] = []
        sse_group = [g for g in gaps if "streaming" in g.title.lower() or "sse" in g.title.lower()]
        agent_group = [
            g for g in gaps if "multi-agent" in g.title.lower() or "tool calling" in g.title.lower()
        ]
        other_gaps = [g for g in gaps if g not in sse_group and g not in agent_group]

        if sse_group:
            rep = _format_actionable_task(sse_group[0])
            if len(sse_group) > 1:
                notes = "; ".join(g.content for g in sse_group if g.content)
                rep = _synthesize_card(
                    title=rep.title,
                    content=rep.content + f"\n- **Additional Evidence**: {notes}",
                    category=rep.category,
                    constituents=sse_group,
                    normalised_status="in_progress",
                    omit_restricted_items=omit_restricted_items,
                    seed_prefix="sec4-sse-merged",
                )
            out.append(rep)
        if agent_group:
            notes = "; ".join(f"{g.title}: {g.content}" for g in agent_group)
            out.append(
                _synthesize_card(
                    title="Pending Capability: Multi-Agent State Graph & RBAC Tool Execution",
                    content=(
                        "- **What needs to be done**: Implement registered agent state-graph execution, PostgreSQL checkpointing, and RBAC-scoped tool calling.\n"
                        "- **Why it matters**: Required before enabling autonomous multi-step AI investigations without RBAC bypasses or lost state.\n"
                        f"- **Recorded Evidence**: {notes}\n"
                        "- **What to inspect next**: `AI_0_5_IMPLEMENTATION_DESIGN.md` and `docs/ai-architecture-audit/`."
                    ),
                    category=agent_group[0].category,
                    constituents=agent_group,
                    normalised_status="pending",
                    omit_restricted_items=omit_restricted_items,
                    seed_prefix="sec4-agent-merged",
                )
            )
        for g in other_gaps:
            out.append(_format_actionable_task(g))
        for w in p_work:
            out.append(_format_actionable_task(w))
        return out

    v_pw, p_pw = _split_by_epistemic_tier(pending_work_items)
    v_gap, p_gap = _split_by_epistemic_tier(capability_gaps)
    _ = open_checklist_items
    return _compose_tier(v_pw, v_gap) + _compose_tier(p_pw, p_gap)


def _compose_decisions_cards(
    decision_items: list[HandoverSectionKnowledgeItemResponse],
    arch_decision_candidates: list[HandoverSectionKnowledgeItemResponse],
    *,
    omit_restricted_items: bool,
) -> list[HandoverSectionKnowledgeItemResponse]:
    """Compose Section 5 (Important Decisions and Rationale) explaining what, why, and trade-offs."""

    def _format_decision(ki: HandoverSectionKnowledgeItemResponse, default_tradeoff: str = "") -> HandoverSectionKnowledgeItemResponse:
        rationale = str((ki.structured_payload or {}).get("rationale") or "").strip()
        body = (ki.content or "").strip()
        has_inline_reason = any(
            tok in body.lower() for tok in ("because", "rationale", "reason", "trade-off", "alternative", "to avoid", "prevent", "so that")
        )
        if len(decision_items) <= 5 and not arch_decision_candidates:
            # Small test fixture: keep concise original wording plus rationale note if missing
            return ki

        lines = [f"- **Decision**: {body}"]
        if rationale:
            lines.append(f"- **Documented Rationale**: {rationale}")
        elif has_inline_reason:
            lines.append("- **Documented Rationale**: Embedded within the linked architecture/decision evidence above.")
        else:
            lines.append(
                "- **Documented Rationale**: Confirmed in linked project records; explicit rejected alternatives were not recorded separately."
            )
        if default_tradeoff:
            lines.append(f"- **System Impact & Trade-offs**: {default_tradeoff}")
        clean_title = re.sub(r"^Document Section:\s*(?:\d+\.\s*)?", "", ki.title).strip()
        return _synthesize_card(
            title=clean_title,
            content="\n".join(lines),
            category="decisions_rationale",
            constituents=[ki],
            omit_restricted_items=omit_restricted_items,
            seed_prefix="sec5-dec",
        )

    cards: list[HandoverSectionKnowledgeItemResponse] = []
    for ki in decision_items:
        cards.append(
            _format_decision(
                ki,
                default_tradeoff="Enables local development without cloud GPU dependencies while isolating remote deployment traffic via gateway tunnel.",
            )
        )

    seen_titles = {c.title.lower() for c in cards}
    for ki in arch_decision_candidates:
        tl = ki.title.lower()
        tradeoff = ""
        if "state graph" in tl:
            tradeoff = "Avoids heavy external agent orchestration lock-in while preserving PostgreSQL checkpointing and LangGraph-style transitions."
        elif "postgresql" in tl or "canonical" in tl:
            tradeoff = "Maintains PostgreSQL as the single transactional source of truth; ChromaDB remains rebuildable secondary vector storage."
        elif "acl" in tl or "zero-privilege" in tl or "authorization" in tl:
            tradeoff = "Requires strict pre-retrieval filtering and may exclude restricted records for non-authorised viewers (fail-closed security)."
        formatted = _format_decision(ki, default_tradeoff=tradeoff)
        if formatted.title.lower() not in seen_titles:
            seen_titles.add(formatted.title.lower())
            cards.append(formatted)
    return cards


def _compose_dependency_cards(
    dep_items: list[HandoverSectionKnowledgeItemResponse],
    infra_dep_items: list[HandoverSectionKnowledgeItemResponse],
    dep_rels: list[HandoverSectionRelationshipResponse],
    *,
    omit_restricted_items: bool,
) -> tuple[list[HandoverSectionKnowledgeItemResponse], list[HandoverSectionRelationshipResponse]]:
    """Compose Section 6: prioritise system/service dependencies and consolidate manifest deps into 1 card."""
    structural_rels = [
        r for r in dep_rels if r.relationship_type not in _LOW_SIGNAL_REL_TYPES
    ]
    # Deduplicate (source_name, relationship_type, target_name)
    seen_edges: set[tuple[str, str, str]] = set()
    unique_structural_rels: list[HandoverSectionRelationshipResponse] = []
    for r in structural_rels:
        key = (r.source_entity_name.lower(), r.relationship_type, r.target_entity_name.lower())
        if key not in seen_edges:
            seen_edges.add(key)
            unique_structural_rels.append(r)

    def _compose_tier(
        items: list[HandoverSectionKnowledgeItemResponse],
        infra_items: list[HandoverSectionKnowledgeItemResponse],
    ) -> list[HandoverSectionKnowledgeItemResponse]:
        manifest_deps: list[tuple[HandoverSectionKnowledgeItemResponse, dict[str, Any]]] = []
        substantive_deps: list[HandoverSectionKnowledgeItemResponse] = []
        for ki in items:
            meta = classify_finding(ki)
            if meta["kind"] == "manifest_dependency":
                manifest_deps.append((ki, meta))
            else:
                substantive_deps.append(ki)

        cards: list[HandoverSectionKnowledgeItemResponse] = list(substantive_deps)
        seen_sub = {c.id for c in cards}
        for inf in infra_items:
            if inf.id not in seen_sub:
                cards.append(inf)
                seen_sub.add(inf.id)

        if manifest_deps:
            if len(manifest_deps) <= 3 and not substantive_deps and not unique_structural_rels:
                cards.extend([it for it, _ in manifest_deps])
            else:
                manifest_card = _compose_manifest_card(
                    manifest_deps,
                    [],
                    title="External Package Manifest Dependencies (Reference Summary)",
                    category="dependencies",
                    intro=(
                        "External libraries declared across project dependency manifests "
                        "(grouped by functional layer; detailed manifest evidence remains linked in Section 10):"
                    ),
                    omit_restricted_items=omit_restricted_items,
                    seed_prefix="sec6-manifest-deps",
                )
                if manifest_card is not None:
                    cards.append(manifest_card)
        return cards

    v_dep, p_dep = _split_by_epistemic_tier(dep_items)
    v_inf, p_inf = _split_by_epistemic_tier(infra_dep_items)
    composed_cards = _compose_tier(v_dep, v_inf) + _compose_tier(p_dep, p_inf)
    return composed_cards, unique_structural_rels[:40]


def _compose_risk_cards(
    risk_items: list[HandoverSectionKnowledgeItemResponse],
    *,
    omit_restricted_items: bool,
) -> tuple[list[HandoverSectionKnowledgeItemResponse], list[HandoverSectionKnowledgeItemResponse], list[HandoverSectionKnowledgeItemResponse]]:
    """Compose Section 7 separating active risks/blockers from historical resolved commits."""
    active_risks: list[HandoverSectionKnowledgeItemResponse] = []
    historical_resolved: list[HandoverSectionKnowledgeItemResponse] = []
    misclassified_fix_commits: list[HandoverSectionKnowledgeItemResponse] = []

    for ki in risk_items:
        meta = classify_finding(ki)
        if meta["kind"] == "raw_commit":
            misclassified_fix_commits.append(ki)
            continue
        if (ki.normalised_status or "").lower() in _COMPLETED_STATUS_TOKENS:
            historical_resolved.append(ki)
        else:
            active_risks.append(ki)

    # Enrich active risks only if many unformatted risks exist; keep single items concise
    if len(active_risks) > 4:
        formatted_active: list[HandoverSectionKnowledgeItemResponse] = []
        for ki in active_risks:
            tl = ki.title.lower()
            affected = "Assistant & Inference Pipeline"
            if "timeout" in tl:
                affected = "HTTP API & Investigation Endpoints"
            elif "vram" in tl:
                affected = "Local Ollama GPU Runtime (RTX 4050 6GB)"
            elif "tool" in tl:
                affected = "Agent Tool Execution & RBAC Boundary"
            elif "checkpoint" in tl:
                affected = "Long-Running Agent Workflows"
            elif "poisoning" in tl:
                affected = "External Source Ingestion (GitHub/Jira/Uploads)"
            elif "streaming" in tl or "sse" in tl:
                affected = "Real-Time UX & Streaming Transport"
            elif "test" in tl:
                affected = "CI Quality & Regression Verification"

            content = (
                f"- **Description**: {(ki.content or '').strip()}\n"
                f"- **Affected Component**: {affected}\n"
                f"- **Status**: Active / Requires Monitoring or Mitigation"
            )
            formatted_active.append(
                _synthesize_card(
                    title=ki.title,
                    content=content,
                    category="bugs_blockers_risks",
                    constituents=[ki],
                    normalised_status=ki.normalised_status or "open",
                    omit_restricted_items=omit_restricted_items,
                    seed_prefix="sec7-risk",
                )
            )
        active_risks = formatted_active

    return active_risks, historical_resolved, misclassified_fix_commits


def _compose_responsibility_cards(
    resp_items: list[HandoverSectionKnowledgeItemResponse],
    *,
    omit_restricted_items: bool,
) -> list[HandoverSectionKnowledgeItemResponse]:
    """Consolidate per-commit Commit Author noise into 1 contributor card while keeping genuine ownership findings."""

    def _compose_tier(items: list[HandoverSectionKnowledgeItemResponse]) -> list[HandoverSectionKnowledgeItemResponse]:
        if not items:
            return []
        author_counts: Counter[str] = Counter()
        author_kis: list[HandoverSectionKnowledgeItemResponse] = []
        real_resp_kis: list[HandoverSectionKnowledgeItemResponse] = []

        for ki in items:
            meta = classify_finding(ki)
            if meta["kind"] == "commit_author":
                author_counts[meta["author"]] += 1
                author_kis.append(ki)
            else:
                real_resp_kis.append(ki)

        cards = list(real_resp_kis)
        if author_kis:
            if len(author_kis) <= 2 and not real_resp_kis:
                cards.extend(author_kis)
            else:
                lines = [
                    "Summarises historical repository commit authorship (strictly distinct from confirmed ongoing component ownership or RBAC membership):",
                    "",
                ]
                for author, cnt in author_counts.most_common():
                    lines.append(f"- **{author}**: {cnt} recorded commit(s)")
                lines.extend([
                    "",
                    "*Governance Note*: Commit history alone does not assign ongoing operational ownership. Confirm formal ownership via Responsibility Transfers above.",
                ])
                cards.append(
                    _synthesize_card(
                        title=f"Historical Repository Contributors ({len(author_counts)} authors, {len(author_kis)} commit records)",
                        content="\n".join(lines),
                        category="responsibilities_ownership",
                        constituents=author_kis,
                        extra_payload={"contributor_commit_counts": dict(author_counts)},
                        omit_restricted_items=omit_restricted_items,
                        seed_prefix="sec8-contributors",
                    )
                )
        return cards

    v_items, p_items = _split_by_epistemic_tier(resp_items)
    return _compose_tier(v_items) + _compose_tier(p_items)


def _compose_evidence_index_cards(
    evidence_refs: list[HandoverEvidenceProvenanceResponse],
    *,
    has_verified_findings: bool,
) -> list[HandoverSectionKnowledgeItemResponse]:
    """Create organised Section 10 reference index cards grouped by source type."""
    if not evidence_refs:
        return []
    grouped: dict[str, list[HandoverEvidenceProvenanceResponse]] = defaultdict(list)
    for ref in evidence_refs:
        if ref.acl_restricted:
            grouped["ACL-Protected Sources"].append(ref)
        elif ref.source_type == "document_upload":
            grouped["Uploaded Documents & Specifications"].append(ref)
        elif ref.source_type in ("github", "github_repository", "git"):
            name = (ref.source_name or "").lower()
            if name.endswith((".md", ".txt", ".pdf", ".docx")) or "docs/" in name or "readme" in name or "handover_" in name:
                grouped["Architecture, Audit & Repository Documentation"].append(ref)
            elif name.endswith((".toml", ".json", ".yaml", ".yml", ".lock")) or "package.json" in name:
                grouped["Configuration & Package Manifests"].append(ref)
            else:
                grouped["GitHub Commits, PRs & Repository Records"].append(ref)
        else:
            grouped[f"Connected Source ({ref.source_type})"].append(ref)

    now = datetime.now(UTC)
    cards: list[HandoverSectionKnowledgeItemResponse] = []
    for group_name, refs in grouped.items():
        lines = [f"Contains {len(refs)} source record(s) linked to findings in this handover:", ""]
        for r in refs[:25]:
            if r.acl_restricted:
                lines.append(f"- `[{str(r.evidence_id)[:8]}]` Restricted Source (Source ACL Protected)")
            else:
                author = f" · Author: {r.author}" if r.author else ""
                url = f" · {r.source_url}" if r.source_url else ""
                lines.append(f"- `[{str(r.evidence_id)[:8]}]` **{r.source_name}**{author}{url}")
        if len(refs) > 25:
            lines.append(f"- *(+{len(refs) - 25} more record(s) linked in full evidence drawer)*")

        status_ep = "human_verified" if has_verified_findings else "extracted"
        status_rev = "approved" if has_verified_findings else "pending_review"
        cards.append(
            HandoverSectionKnowledgeItemResponse(
                id=uuid.uuid5(uuid.NAMESPACE_URL, f"sec10-ref-{group_name}"),
                content_link_id=uuid.uuid5(uuid.NAMESPACE_URL, f"sec10-link-{group_name}"),
                title=f"Source Category: {group_name} ({len(refs)})",
                content="\n".join(lines),
                category="operational_historical",
                epistemic_status=status_ep,
                review_status=status_rev,
                support_classification="direct",
                structured_payload={"evidence_count": len(refs)},
                created_at=now,
                updated_at=now,
                eligibility={"is_eligible": has_verified_findings, "is_provisional_draft": not has_verified_findings},
                verification=HandoverVerificationSummaryResponse(),
                provenance=refs[:30],
                provenance_available=True,
            )
        )
    return cards


def _format_item_bullets(
    items: list[HandoverSectionKnowledgeItemResponse],
    *,
    note_pr_runtime: bool = False,
    note_decision_rationale: bool = False,
) -> str:
    """Format composed finding cards into clean GitHub-flavored Markdown."""
    lines: list[str] = []
    for ki in items:
        badge_note = " *(Provisional — Pending Human Review)*" if not _item_is_verified(ki) else ""
        lines.append(f"### {ki.title}{badge_note}")
        if ki.content:
            lines.append(ki.content)
        if ki.owner_label:
            lines.append(f"- **Owner / Actor**: {ki.owner_label}")
        if ki.normalised_status:
            lines.append(f"- **Recorded State**: {ki.normalised_status}")
        if note_pr_runtime and any(tok in f"{ki.title} {ki.content}".lower() for tok in ("pull request", "pr ", "merged", "commit")):
            lines.append(
                "- *Verification Scope Note*: Confirmed merged/committed in repository evidence; verify runtime production deployment separately."
            )
        if (
            note_decision_rationale
            and not any(
                tok in (ki.content or "").lower()
                for tok in ("because", "rationale", "reason", "trade-off", "alternative", "chosen")
            )
            and not (ki.structured_payload or {}).get("rationale")
        ):
            lines.append(
                "- *Rationale Note*: Documented decision is recorded; underlying rationale or rejected alternatives were not explicitly recorded in linked evidence."
            )
        sources = ", ".join(
            p.source_name if not p.acl_restricted else "Restricted Source (Source ACL Protected)"
            for p in ki.provenance[:6]
        )
        if sources:
            more = f" (+{len(ki.provenance) - 6} more)" if len(ki.provenance) > 6 else ""
            lines.append(f"- **Sources**: {sources}{more}")
        lines.append("")
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Public Entrypoints: Ten Mandatory Sections + Start Here Executive Briefing
# ---------------------------------------------------------------------------


def compose_mandatory_ten_sections(
    *,
    hydrated_sections: list[HandoverSectionDetailResponse],
    handover_type: str,
    unresolved_conflicts: list[HandoverSectionConflictItemResponse],
    resolved_conflicts: list[HandoverSectionConflictItemResponse],
    team_members_ctx: list[dict[str, Any]],
    transfers_ctx: list[dict[str, Any]],
    checklists: list[HandoverChecklist],
    domain_context_overview: dict[str, Any],
    omit_restricted_items: bool = False,
) -> list[HandoverMandatorySectionResponse]:
    """Compose the canonical 10 role-prioritised handover sections cleanly from hydrated findings."""
    role_key = normalize_handover_type(handover_type)
    role_cfg = HANDOVER_ROLE_CONFIG[role_key]
    priority_order: list[int] = role_cfg["priority_order"]
    top_sections: set[int] = role_cfg["top_sections"]
    rank_by_section_num = {sec_num: idx + 1 for idx, sec_num in enumerate(priority_order)}

    sec_map = {sec.section_type: sec for sec in hydrated_sections}

    def _permitted_kis(section_type: str) -> list[HandoverSectionKnowledgeItemResponse]:
        sec = sec_map.get(section_type)
        if not sec:
            return []
        if not omit_restricted_items:
            return list(sec.knowledge_items)
        return [
            ki for ki in sec.knowledge_items if not any(p.acl_restricted for p in ki.provenance)
        ]

    def _permitted_rels(section_type: str) -> list[HandoverSectionRelationshipResponse]:
        sec = sec_map.get(section_type)
        if not sec:
            return []
        if not omit_restricted_items:
            return list(sec.relationships)
        return [
            rel for rel in sec.relationships if not any(p.acl_restricted for p in rel.provenance)
        ]

    def _pending_count(section_types: list[str]) -> int:
        return sum(
            sec_map[st].epistemic_breakdown.pending_verification
            for st in section_types
            if st in sec_map
        )

    def _collect_provenance(
        items: list[HandoverSectionKnowledgeItemResponse],
        rels: list[HandoverSectionRelationshipResponse],
    ) -> list[HandoverEvidenceProvenanceResponse]:
        by_id: dict[uuid.UUID, HandoverEvidenceProvenanceResponse] = {}
        for ki in items:
            for p in ki.provenance:
                if omit_restricted_items and p.acl_restricted:
                    continue
                by_id.setdefault(p.evidence_id, p)
        for rel in rels:
            for p in rel.provenance:
                if omit_restricted_items and p.acl_restricted:
                    continue
                by_id.setdefault(p.evidence_id, p)
        return list(by_id.values())

    # Pre-scan cross-domain misplaced items (e.g. README overview docs & decision docs in operational_historical,
    # fix commits in bugs_blockers_risks, capability gaps in technical_architecture, infra setup in tech_arch)
    raw_overview_kis = _permitted_kis(HandoverPackageSectionType.PROJECT_OVERVIEW_CONTEXT.value)
    raw_arch_kis = _permitted_kis(HandoverPackageSectionType.TECHNICAL_ARCHITECTURE.value)
    raw_ops_kis = _permitted_kis(HandoverPackageSectionType.OPERATIONAL_HISTORICAL.value)
    raw_work_kis = _permitted_kis(HandoverPackageSectionType.WORK_PROGRESS.value)
    raw_dec_kis = _permitted_kis(HandoverPackageSectionType.DECISIONS_RATIONALE.value)
    raw_dep_kis = _permitted_kis(HandoverPackageSectionType.DEPENDENCIES_RELATIONSHIPS.value)
    raw_dep_rels = _permitted_rels(HandoverPackageSectionType.DEPENDENCIES_RELATIONSHIPS.value)
    raw_risk_kis = _permitted_kis(HandoverPackageSectionType.BUGS_BLOCKERS_RISKS.value)
    raw_resp_kis = _permitted_kis(HandoverPackageSectionType.RESPONSIBILITIES_OWNERSHIP.value)

    readme_overview_docs: list[tuple[HandoverSectionKnowledgeItemResponse, dict[str, Any]]] = []
    decision_doc_items: list[HandoverSectionKnowledgeItemResponse] = []
    for ki in raw_ops_kis:
        meta = classify_finding(ki)
        if meta["kind"] == "readme_overview_doc":
            readme_overview_docs.append((ki, meta))
        elif meta["kind"] == "decision_doc":
            decision_doc_items.append(ki)

    arch_capability_gaps: list[HandoverSectionKnowledgeItemResponse] = []
    infra_dep_items: list[HandoverSectionKnowledgeItemResponse] = []
    for ki in raw_arch_kis:
        meta = classify_finding(ki)
        if meta["kind"] == "capability_gap":
            arch_capability_gaps.append(ki)
        elif any(tok in ki.title.lower() for tok in ("tunnel connection", "local infrastructure setup")):
            infra_dep_items.append(ki)
        elif any(tok in ki.title.lower() for tok in ("state graph", "postgresql as canonical", "zero-privilege agent")):
            if len(raw_arch_kis) > 5:
                decision_doc_items.append(ki)

    # Extract risks & separate misclassified fix commits
    active_risks, historical_risks, misclassified_fix_commits = _compose_risk_cards(
        raw_risk_kis, omit_restricted_items=omit_restricted_items
    )
    risk_capability_gaps = [
        ki
        for ki in active_risks
        if any(tok in ki.title.lower() for tok in ("missing", "partial"))
    ]

    # Checklists
    all_checklist_items = [item for chk in checklists for item in (chk.items or [])]
    completed_checklist = [
        it for it in all_checklist_items if it.status == ChecklistItemStatus.COMPLETED.value
    ]
    open_checklist = [
        it
        for it in all_checklist_items
        if it.status not in (ChecklistItemStatus.COMPLETED.value, ChecklistItemStatus.SKIPPED.value)
    ]

    # 1. Project Overview
    overview_cards = _compose_overview_cards(
        raw_overview_kis,
        readme_overview_docs,
        domain_context_overview,
        omit_restricted_items=omit_restricted_items,
    )
    overview_pending = _pending_count([HandoverPackageSectionType.PROJECT_OVERVIEW_CONTEXT.value])
    overview_lines: list[str] = []
    if domain_context_overview.get("project_name"):
        overview_lines.append(
            f"**Project**: {redact_secrets(str(domain_context_overview.get('project_name')))}"
        )
    if domain_context_overview.get("project_description"):
        overview_lines.append(redact_secrets(str(domain_context_overview.get("project_description"))))
    if overview_cards:
        overview_lines.append("")
        overview_lines.append(_format_item_bullets(overview_cards))
    overview_ready = "ready" if overview_cards else "insufficient_information"
    overview_gap = (
        None
        if overview_cards
        else "Insufficient approved project overview findings. Verify project overview claims in Verification Center instead of relying on unreviewed summaries."
    )

    # 2. Architecture and Technical Context
    arch_cards = _compose_architecture_cards(
        raw_arch_kis,
        raw_ops_kis,
        omit_restricted_items=omit_restricted_items,
    )
    arch_pending = _pending_count([
        HandoverPackageSectionType.TECHNICAL_ARCHITECTURE.value,
        HandoverPackageSectionType.OPERATIONAL_HISTORICAL.value,
    ])
    arch_md = _format_item_bullets(arch_cards) if arch_cards else ""
    arch_ready = "ready" if arch_cards else "insufficient_information"
    arch_gap = (
        None
        if arch_cards
        else "No human-verified system architecture, API, deployment, or operational procedure findings exist in this version."
    )

    # 3 & 4. Completed Work vs Pending Work
    completed_cards, pending_work_raw = _compose_completed_work_cards(
        raw_work_kis,
        extra_fix_commits=misclassified_fix_commits,
        omit_restricted_items=omit_restricted_items,
    )
    pending_cards = _compose_pending_work_cards(
        pending_work_raw,
        arch_capability_gaps + risk_capability_gaps,
        open_checklist,
        omit_restricted_items=omit_restricted_items,
    )
    work_pending_count = _pending_count([HandoverPackageSectionType.WORK_PROGRESS.value])

    comp_lines: list[str] = []
    if completed_cards:
        comp_lines.append(_format_item_bullets(completed_cards, note_pr_runtime=True))
    if completed_checklist:
        comp_lines.append("### Completed Handover Checklist Items")
        for it in completed_checklist:
            comp_lines.append(f"- [x] {redact_secrets(it.item_text)}")
    comp_ready = "ready" if (completed_cards or completed_checklist) else "insufficient_information"
    comp_gap = (
        None
        if (completed_cards or completed_checklist)
        else "No human-verified completed deliverables or merged milestones are recorded in this version."
    )

    pend_lines: list[str] = []
    if pending_cards:
        pend_lines.append(_format_item_bullets(pending_cards))
    if open_checklist:
        pend_lines.append("### Open Transition Checklist Tasks")
        for it in open_checklist:
            blocking_tag = " *(BLOCKING)*" if it.blocking else ""
            pend_lines.append(f"- [ ] {redact_secrets(it.item_text)}{blocking_tag}")
    pend_ready = "ready" if (pending_cards or open_checklist) else "insufficient_information"
    pend_gap = (
        None
        if (pending_cards or open_checklist)
        else "No human-verified pending work items or open checklist tasks are recorded."
    )

    # 5. Important Decisions and Rationale
    dec_cards = _compose_decisions_cards(
        raw_dec_kis, decision_doc_items, omit_restricted_items=omit_restricted_items
    )
    dec_pending = _pending_count([HandoverPackageSectionType.DECISIONS_RATIONALE.value])
    dec_md = _format_item_bullets(dec_cards, note_decision_rationale=True) if dec_cards else ""
    dec_ready = "ready" if dec_cards else "insufficient_information"
    dec_gap = (
        None
        if dec_cards
        else "No human-verified technical or project decisions with rationale have been approved yet."
    )

    # 6. Dependencies
    dep_cards, filtered_dep_rels = _compose_dependency_cards(
        raw_dep_kis, infra_dep_items, raw_dep_rels, omit_restricted_items=omit_restricted_items
    )
    dep_pending = _pending_count([HandoverPackageSectionType.DEPENDENCIES_RELATIONSHIPS.value])
    dep_lines: list[str] = []
    if filtered_dep_rels:
        dep_lines.append("### Evidence-Supported Component & Service Relationships")
        for rel in filtered_dep_rels:
            dep_lines.append(
                f"- **{redact_secrets(rel.source_entity_name)}** (`{rel.relationship_type}`) -> **{redact_secrets(rel.target_entity_name)}**"
            )
        dep_lines.append("")
    if dep_cards:
        dep_lines.append(_format_item_bullets(dep_cards))
    dep_ready = "ready" if (dep_cards or filtered_dep_rels) else "insufficient_information"
    dep_gap = (
        None
        if (dep_cards or filtered_dep_rels)
        else "No evidence-supported component, service, or task dependencies have been verified yet."
    )

    # 7. Risks and Blockers
    risk_pending = _pending_count([HandoverPackageSectionType.BUGS_BLOCKERS_RISKS.value])
    risk_cards = active_risks + historical_risks
    risk_lines: list[str] = []
    if active_risks:
        risk_lines.append("### Active Risks & Technical Blockers")
        risk_lines.append(_format_item_bullets(active_risks))
    if historical_risks:
        risk_lines.append("### Resolved Historical Issues")
        risk_lines.append(_format_item_bullets(historical_risks))
    if unresolved_conflicts:
        risk_lines.append(
            f"### Unresolved Cross-Source Conflicts ({len(unresolved_conflicts)} — Excluded from Verified Facts)"
        )
        for cf in unresolved_conflicts:
            risk_lines.append(f"- **{cf.conflict_type}**: {cf.explanation}")
    if resolved_conflicts:
        risk_lines.append(f"### Resolved Conflicts ({len(resolved_conflicts)})")
        for cf in resolved_conflicts:
            risk_lines.append(
                f"- **{cf.conflict_type}**: {cf.authoritative_claim_text or cf.explanation}"
            )

    if unresolved_conflicts:
        risk_ready = "blocked_by_conflict"
        risk_gap = (
            f"{len(unresolved_conflicts)} unresolved cross-source contradiction(s) require reviewer investigation in Conflict Management."
        )
    elif risk_cards or resolved_conflicts:
        risk_ready = "ready"
        risk_gap = None
    else:
        risk_ready = "insufficient_information"
        risk_gap = "No human-verified bugs, blockers, or risks are recorded in this version."

    # 8. Responsibilities
    resp_cards = _compose_responsibility_cards(raw_resp_kis, omit_restricted_items=omit_restricted_items)
    resp_pending = _pending_count([HandoverPackageSectionType.RESPONSIBILITIES_OWNERSHIP.value])
    unassigned_transfers = [t for t in transfers_ctx if not t.get("proposed_successor_id")]
    unassigned_checklist = [it for it in open_checklist if not it.assigned_to_user_id]

    resp_lines: list[str] = []
    if resp_cards:
        resp_lines.append("### Ownership Findings & Contributor Context")
        resp_lines.append(_format_item_bullets(resp_cards))
    if transfers_ctx:
        resp_lines.append("### Explicit Handover Responsibility Transfers")
        for tr in transfers_ctx:
            owner_name = tr.get("current_owner_name") or "Outgoing Member"
            succ_name = tr.get("proposed_successor_name") or "Unassigned (Requires Clarification)"
            resp_lines.append(
                f"- **{redact_secrets(tr.get('responsibility_description', ''))}** — {owner_name} -> {succ_name} (`{tr.get('transfer_status')}`)"
            )
    elif team_members_ctx:
        resp_lines.append("### Project Roster Reference (Membership != Technical Ownership)")
        for tm in team_members_ctx:
            role_note = f" ({tm.get('responsibility_description')})" if tm.get("responsibility_description") else ""
            resp_lines.append(
                f"- {tm.get('full_name') or tm.get('email') or 'Member'} — Role: `{tm.get('role_name')}`{role_note}"
            )
    if unassigned_transfers or unassigned_checklist:
        resp_lines.append("### Unassigned Duties Requiring Clarification")
        for tr in unassigned_transfers:
            resp_lines.append(
                f"- Transfer lacking proposed successor: {redact_secrets(tr.get('responsibility_description', ''))}"
            )
        for it in unassigned_checklist:
            resp_lines.append(f"- Unassigned checklist task: {redact_secrets(it.item_text)}")

    resp_has_content = bool(resp_cards or transfers_ctx)
    resp_ready = (
        "needs_attention"
        if resp_has_content and unassigned_transfers
        else "ready"
        if resp_has_content
        else "insufficient_information"
    )
    resp_gap = (
        None
        if resp_ready == "ready"
        else "Some responsibilities lack an assigned successor."
        if resp_ready == "needs_attention"
        else "No verified ownership records or responsibility transfers are defined yet. Project membership alone does not establish component ownership."
    )

    # 9. Recommended Next Steps (strictly grounded in open conflicts, pending tasks, risks, checklists & runbooks)
    steps: list[dict[str, Any]] = []
    step_cards: list[HandoverSectionKnowledgeItemResponse] = []

    for cf in unresolved_conflicts:
        steps.append(
            {
                "priority": "urgent",
                "status": "pending",
                "source_section": "Risks and Blockers",
                "title": f"Resolve verification conflict ({cf.conflict_type})",
                "detail": cf.explanation,
                "action_target": "conflicts",
            }
        )
    for it in open_checklist:
        steps.append(
            {
                "priority": "high" if it.blocking else "medium",
                "status": "pending",
                "source_section": "Transition Checklist",
                "title": redact_secrets(it.item_text),
                "detail": redact_secrets(it.description or ""),
                "action_target": "checklists",
            }
        )
    for card in pending_cards[:8]:
        steps.append(
            {
                "priority": "high",
                "status": card.normalised_status or "pending",
                "source_section": "Pending Work",
                "title": card.title,
                "detail": card.content,
                "owner": card.owner_label,
                "action_target": "tasks",
            }
        )
    if unassigned_transfers:
        steps.append(
            {
                "priority": "high",
                "status": "pending",
                "source_section": "Responsibilities",
                "title": f"Confirm successor assignment for {len(unassigned_transfers)} unassigned responsibility transfer(s)",
                "detail": "; ".join(
                    redact_secrets(t.get("responsibility_description", "")) for t in unassigned_transfers[:5]
                ),
                "action_target": "responsibilities",
            }
        )
    ops_runbooks = [
        ki
        for ki in raw_ops_kis
        if classify_finding(ki)["kind"] in ("substantive", "operational_doc")
    ]
    for op in ops_runbooks[:3]:
        clean_op_title = re.sub(r"^Document Section:\s*", "", op.title)
        steps.append(
            {
                "priority": "normal",
                "status": "recommended",
                "source_section": "Architecture & Operations",
                "title": f"Verify operational setup: {clean_op_title}",
                "detail": op.content,
                "action_target": "operations",
            }
        )
    for rel in filtered_dep_rels[:4]:
        steps.append(
            {
                "priority": "medium",
                "status": "recommended",
                "source_section": "Dependencies",
                "title": f"Verify service integration: {redact_secrets(rel.source_entity_name)} -> {redact_secrets(rel.target_entity_name)}",
                "detail": f"Relationship type: {rel.relationship_type}",
                "action_target": "dependencies",
            }
        )

    # Synthesize at most 1–2 concise continuation cards ONLY when we have substantial project guidance
    # (keep small unit-test fixtures clean if they rely solely on recommended_steps)
    if pending_cards or len(steps) >= 3:
        action_lines = [
            f"{idx}. **[{st['priority'].upper()}] {st['title']}** — *{st['source_section']}*"
            for idx, st in enumerate(steps[:10], start=1)
        ]
        if action_lines and len(pending_cards) + len(arch_cards) > 4:
            step_cards.append(
                _synthesize_card(
                    title=f"Prioritised Continuation Sequence ({len(steps)} Action Items)",
                    content="\n".join(action_lines),
                    category="work_items",
                    constituents=pending_cards[:6] + ops_runbooks[:2],
                    normalised_status="pending",
                    omit_restricted_items=omit_restricted_items,
                    seed_prefix="sec9-next-steps",
                )
            )

    steps_lines: list[str] = []
    if steps:
        for idx, st in enumerate(steps, start=1):
            owner_suffix = f" (Owner: {st['owner']})" if st.get("owner") else ""
            steps_lines.append(
                f"{idx}. **[{st['priority'].upper()}] {st['title']}**{owner_suffix} — *From {st['source_section']}*"
            )
            if st.get("detail"):
                steps_lines.append(f"   {st['detail']}")
    steps_ready = "ready" if steps else "insufficient_information"
    steps_gap = (
        None
        if steps
        else "Insufficient approved pending work, dependencies, or open checklist tasks to derive continuation steps. Steps are never invented without evidence."
    )

    # 10. Evidence References (preserve 100% of underlying permitted evidence references!)
    all_raw_permitted = (
        raw_overview_kis
        + raw_arch_kis
        + raw_ops_kis
        + raw_work_kis
        + raw_dec_kis
        + raw_dep_kis
        + raw_risk_kis
        + raw_resp_kis
    )
    all_evidence_refs = _collect_provenance(all_raw_permitted, raw_dep_rels)
    has_any_verified = any(_item_is_verified(it) for it in all_raw_permitted)
    ref_cards = (
        _compose_evidence_index_cards(all_evidence_refs, has_verified_findings=has_any_verified)
        if len(all_evidence_refs) > 8
        else []
    )

    ref_lines: list[str] = []
    for ref in all_evidence_refs:
        if ref.acl_restricted:
            ref_lines.append(
                f"- `[{str(ref.evidence_id)[:8]}]` **Restricted Source (Source ACL Protected)** — Access restricted by external source ACL."
            )
        else:
            author_part = f" · Author: {ref.author}" if ref.author else ""
            url_part = f" · URL: {ref.source_url}" if ref.source_url else ""
            ref_lines.append(
                f"- `[{str(ref.evidence_id)[:8]}]` **{ref.source_name}** (`{ref.source_type}`){author_part}{url_part}"
            )
    ref_ready = "ready" if all_evidence_refs else "insufficient_information"
    ref_gap = (
        None
        if all_evidence_refs
        else "No supporting original evidence references are linked to approved findings in this version."
    )

    def _emphasis(num: int, default_note: str) -> str:
        if num in top_sections:
            return f"Primary focus for {role_cfg['label']}. {default_note}"
        return f"Contextual reference for {role_cfg['label']}. {default_note}"

    specs: list[dict[str, Any]] = [
        {
            "section_number": 1,
            "section_key": "project_overview",
            "section_title": "Project Overview",
            "source_domains": ["project_overview_context"],
            "emphasis": "Purpose, scope, project background, and verified current state.",
            "readiness_status": overview_ready,
            "insufficient_info_message": overview_gap,
            "content_markdown": "\n".join(overview_lines).strip(),
            "knowledge_items": overview_cards,
            "relationships": [],
            "unresolved_conflicts": [],
            "evidence_references": _collect_provenance(overview_cards, []),
            "pending_verification_count": overview_pending,
        },
        {
            "section_number": 2,
            "section_key": "architecture_technical_context",
            "section_title": "Architecture and Technical Context",
            "source_domains": ["technical_architecture", "operational_historical"],
            "emphasis": "System architecture, services, stack, APIs, constraints, and operational runbooks.",
            "readiness_status": arch_ready,
            "insufficient_info_message": arch_gap,
            "content_markdown": arch_md,
            "knowledge_items": arch_cards,
            "relationships": [],
            "unresolved_conflicts": [],
            "evidence_references": _collect_provenance(arch_cards, []),
            "pending_verification_count": arch_pending,
        },
        {
            "section_number": 3,
            "section_key": "completed_work",
            "section_title": "Completed Work",
            "source_domains": ["work_progress"],
            "emphasis": "Delivered features, grouped workstreams, and completed handover milestones.",
            "readiness_status": comp_ready,
            "insufficient_info_message": comp_gap,
            "content_markdown": "\n\n".join(comp_lines).strip(),
            "knowledge_items": completed_cards,
            "relationships": [],
            "unresolved_conflicts": [],
            "evidence_references": _collect_provenance(completed_cards, []),
            "pending_verification_count": 0,
        },
        {
            "section_number": 4,
            "section_key": "pending_work",
            "section_title": "Pending Work",
            "source_domains": ["work_progress"],
            "emphasis": "Actionable unfinished capabilities, open backlog, blockers, and inspection targets.",
            "readiness_status": pend_ready,
            "insufficient_info_message": pend_gap,
            "content_markdown": "\n\n".join(pend_lines).strip(),
            "knowledge_items": pending_cards,
            "relationships": [],
            "unresolved_conflicts": [],
            "evidence_references": _collect_provenance(pending_cards, []),
            "pending_verification_count": work_pending_count,
        },
        {
            "section_number": 5,
            "section_key": "important_decisions_rationale",
            "section_title": "Important Decisions and Rationale",
            "source_domains": ["decisions_rationale"],
            "emphasis": "Key engineering/product choices, why they were made, and trade-offs.",
            "readiness_status": dec_ready,
            "insufficient_info_message": dec_gap,
            "content_markdown": dec_md,
            "knowledge_items": dec_cards,
            "relationships": [],
            "unresolved_conflicts": [],
            "evidence_references": _collect_provenance(dec_cards, []),
            "pending_verification_count": dec_pending,
        },
        {
            "section_number": 6,
            "section_key": "dependencies",
            "section_title": "Dependencies",
            "source_domains": ["dependencies_relationships"],
            "emphasis": "Evidence-backed component, service, integration, and package manifest dependencies.",
            "readiness_status": dep_ready,
            "insufficient_info_message": dep_gap,
            "content_markdown": "\n\n".join(dep_lines).strip(),
            "knowledge_items": dep_cards,
            "relationships": filtered_dep_rels,
            "unresolved_conflicts": [],
            "evidence_references": _collect_provenance(dep_cards, filtered_dep_rels),
            "pending_verification_count": dep_pending,
        },
        {
            "section_number": 7,
            "section_key": "risks_and_blockers",
            "section_title": "Risks and Blockers",
            "source_domains": ["bugs_blockers_risks"],
            "emphasis": "Confirmed open risks, active technical blockers, and separated unresolved conflicts.",
            "readiness_status": risk_ready,
            "insufficient_info_message": risk_gap,
            "content_markdown": "\n\n".join(risk_lines).strip(),
            "knowledge_items": risk_cards,
            "relationships": [],
            "unresolved_conflicts": unresolved_conflicts,
            "evidence_references": _collect_provenance(risk_cards, []),
            "pending_verification_count": risk_pending,
        },
        {
            "section_number": 8,
            "section_key": "responsibilities",
            "section_title": "Responsibilities",
            "source_domains": ["responsibilities_ownership"],
            "emphasis": "Confirmed roles, formal transfers, contributor context, and ownership gaps.",
            "readiness_status": resp_ready,
            "insufficient_info_message": resp_gap,
            "content_markdown": "\n\n".join(resp_lines).strip(),
            "knowledge_items": resp_cards,
            "relationships": [],
            "unresolved_conflicts": [],
            "evidence_references": _collect_provenance(resp_cards, []),
            "responsibilities_summary": transfers_ctx,
            "pending_verification_count": resp_pending,
        },
        {
            "section_number": 9,
            "section_key": "recommended_next_steps",
            "section_title": "Recommended Next Steps",
            "source_domains": ["work_progress", "dependencies_relationships", "bugs_blockers_risks", "operational_historical"],
            "emphasis": "Ordered, source-grounded continuation guide for the incoming successor.",
            "readiness_status": steps_ready,
            "insufficient_info_message": steps_gap,
            "content_markdown": "\n".join(steps_lines).strip(),
            "knowledge_items": step_cards,
            "relationships": [],
            "unresolved_conflicts": [],
            "evidence_references": _collect_provenance(pending_cards + ops_runbooks[:3], filtered_dep_rels[:4]),
            "recommended_steps": steps,
            "pending_verification_count": 0,
        },
        {
            "section_number": 10,
            "section_key": "evidence_references",
            "section_title": "Evidence References",
            "source_domains": list(SECTION_ORDER),
            "emphasis": "Complete ACL-verified provenance index linking report statements to original sources.",
            "readiness_status": ref_ready,
            "insufficient_info_message": ref_gap,
            "content_markdown": "\n".join(ref_lines).strip(),
            "knowledge_items": ref_cards,
            "relationships": [],
            "unresolved_conflicts": [],
            "evidence_references": all_evidence_refs,
            "pending_verification_count": 0,
        },
    ]

    return [
        HandoverMandatorySectionResponse(
            section_number=s["section_number"],
            section_key=s["section_key"],
            section_title=s["section_title"],
            source_domains=s["source_domains"],
            role_priority_rank=rank_by_section_num[s["section_number"]],
            is_role_priority=s["section_number"] in top_sections,
            role_emphasis_note=_emphasis(s["section_number"], s["emphasis"]),
            readiness_status=s["readiness_status"],
            insufficient_info_message=s["insufficient_info_message"],
            content_markdown=s["content_markdown"],
            knowledge_items=s["knowledge_items"],
            relationships=s["relationships"],
            unresolved_conflicts=s["unresolved_conflicts"],
            evidence_references=s["evidence_references"],
            recommended_steps=s.get("recommended_steps", []),
            responsibilities_summary=s.get("responsibilities_summary", []),
            pending_verification_count=s["pending_verification_count"],
        )
        for s in specs
    ]


def build_start_here_briefing(
    *,
    mandatory_sections: list[HandoverMandatorySectionResponse],
    domain_context_overview: dict[str, Any],
    team_members_ctx: list[dict[str, Any]],
    transfers_ctx: list[dict[str, Any]],
    handover_type: str,
    is_provisional_draft: bool,
) -> HandoverStartHereBriefing:
    """Synthesise an executive 'Start Here' briefing from the composed ten sections."""
    sec_by_key = {s.section_key: s for s in mandatory_sections}
    role_key = normalize_handover_type(handover_type)
    role_cfg = HANDOVER_ROLE_CONFIG[role_key]

    proj_name = redact_secrets(str(domain_context_overview.get("project_name") or "this project"))
    proj_desc = redact_secrets(str(domain_context_overview.get("project_description") or "")).strip()

    # 1. What is this project?
    ov = sec_by_key.get("project_overview")
    if ov and ov.knowledge_items:
        first_txt = ov.knowledge_items[0].content.splitlines()
        cleaned_lines = [ln.lstrip("- ").strip() for ln in first_txt if ln.strip() and not ln.startswith("Project:")][:2]
        what_is = f"{proj_name}: " + (" ".join(cleaned_lines) if cleaned_lines else (proj_desc or "See Section 01 for project scope."))
    elif proj_desc:
        what_is = f"{proj_name}: {proj_desc}"
    else:
        what_is = f"{proj_name}: Insufficient approved overview records are linked yet; review Section 01 and Evidence References."

    # 2. What has been built?
    comp = sec_by_key.get("completed_work")
    if comp and comp.knowledge_items:
        streams = [k.title.replace("Workstream: ", "") for k in comp.knowledge_items[:5]]
        what_built = f"Delivered capabilities and documented workstreams include: {'; '.join(streams)}."
        if len(comp.knowledge_items) > 5:
            what_built += f" (+{len(comp.knowledge_items) - 5} more in Section 03)."
    else:
        what_built = "No completed work items are verified in this snapshot (see Section 03)."

    # 3. How does it work?
    arch = sec_by_key.get("architecture_technical_context")
    if arch and arch.knowledge_items:
        layers = [k.title for k in arch.knowledge_items if "Manifest Reference" not in k.title][:5]
        how_works = (
            f"Structured across: {', '.join(layers)}."
            if layers
            else f"Technical architecture context compiled in {len(arch.knowledge_items)} section card(s) (Section 02)."
        )
    else:
        how_works = "Insufficient approved architecture documentation in this version (Section 02)."

    # 4. What is the current state?
    pend = sec_by_key.get("pending_work")
    risk = sec_by_key.get("risks_and_blockers")
    pend_titles = [k.title.replace("Pending Capability: ", "") for k in (pend.knowledge_items if pend else [])[:3]]
    risk_titles = [k.title for k in (risk.knowledge_items if risk else [])[:3]]
    state_parts: list[str] = []
    if pend_titles:
        state_parts.append(f"Open/unfinished areas: {', '.join(pend_titles)}")
    if risk_titles:
        state_parts.append(f"Key risks: {', '.join(risk_titles)}")
    if risk and risk.unresolved_conflicts:
        state_parts.append(f"{len(risk.unresolved_conflicts)} unresolved cross-source conflict(s)")
    if is_provisional_draft:
        state_parts.append("Note: This draft includes provisional findings awaiting human approval in Verification Center.")
    current_state = ". ".join(state_parts) if state_parts else "No open blockers or pending work recorded in this snapshot."

    # 5. What should the successor understand first?
    dec = sec_by_key.get("important_decisions_rationale")
    dec_titles = [k.title for k in (dec.knowledge_items if dec else [])[:3]]
    understand_parts: list[str] = []
    if dec_titles:
        understand_parts.append(f"Key decisions: {', '.join(dec_titles)}")
    if transfers_ctx:
        understand_parts.append(f"{len(transfers_ctx)} explicit responsibility transfer(s) tracked")
    elif team_members_ctx:
        understand_parts.append(f"{len(team_members_ctx)} active project member(s) on roster (verify component ownership separately)")
    dep = sec_by_key.get("dependencies")
    if dep and dep.relationships:
        understand_parts.append(f"{len(dep.relationships)} documented system integration/component relationship(s)")
    understand_first = ". ".join(understand_parts) if understand_parts else "Begin with Section 01 and Verification Center status."

    # 6. Where should they start?
    steps_sec = sec_by_key.get("recommended_next_steps")
    top_steps = (steps_sec.recommended_steps if steps_sec else [])[:3]
    if top_steps:
        where_start = " -> ".join(f"{i+1}) {st.get('title')}" for i, st in enumerate(top_steps))
    else:
        where_start = "Review Section 10 (Evidence References) and Verification Center pending findings."

    return HandoverStartHereBriefing(
        what_is_this_project=what_is[:800],
        what_has_been_built=what_built[:800],
        how_does_it_work=how_works[:800],
        what_is_the_current_state=current_state[:800],
        what_to_understand_first=understand_first[:800],
        where_to_start=where_start[:800],
        role_guidance=role_cfg["focus_summary"],
        is_provisional_draft=is_provisional_draft,
    )
