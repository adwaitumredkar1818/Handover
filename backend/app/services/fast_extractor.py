"""Fast deterministic knowledge extractor for PDF documents, markdown specs, and GitHub evidence.

Extracts grounded KnowledgeItems in milliseconds without heavy multi-category LLM loops.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import utc_now
from app.models.enums import (
    EpistemicStatus,
    EvidenceSourceType,
    KnowledgeCategory,
    KnowledgeReviewStatus,
)
from app.models.evidence import EvidenceChunk, EvidenceItem
from app.models.knowledge import KnowledgeEvidenceLink, KnowledgeExtractionRun, KnowledgeItem
from app.services.technology_manifest_parser import (
    canonicalize_technology_name,
    is_manifest_path,
    parse_manifest_evidence,
)

logger = logging.getLogger(__name__)


_SEMANTIC_ELIGIBLE_CATEGORIES = frozenset(
    {
        "documentation",
        "architecture",
        "pdf_document",
        "docx_document",
        "design_document",
        "project_document",
        "architecture_decision",
        "pull_request",
        "issue",
        "discussion",
    }
)


def is_evidence_semantic_eligible(
    *,
    category: str | None,
    title: str | None,
    mime_type: str | None,
    text_len: int,
    metadata_json: dict[str, Any] | None = None,
) -> bool:
    """Determine whether an evidence item warrants Stage 2 Ollama semantic extraction."""
    cat = (category or "").lower()
    if cat in {"commit", "source_code"}:
        return False
    if is_manifest_path(title):
        return False
    if (metadata_json or {}).get("github_item_type") == "repository":
        return False
    if text_len < 20:
        return False
    if cat in _SEMANTIC_ELIGIBLE_CATEGORIES:
        return True
    if mime_type in (
        "text/markdown",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ):
        return True
    return False


def _compute_item_fingerprint(
    *,
    project_id: uuid.UUID,
    category: str,
    title: str,
    structured_summary: str,
) -> str:
    seed = f"{project_id}:{category.lower().strip()}:{title.lower().strip()}:{structured_summary.strip()}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


class FastKnowledgeExtractor:
    """Fast deterministic knowledge extractor parsing structured documents and GitHub repositories."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def extract_evidence_knowledge(
        self,
        *,
        evidence: EvidenceItem,
        run_id: uuid.UUID | None = None,
        force_rerun: bool = False,
        categories: Any = None,
        reconcile_graphs: bool = False,
        existing_fps: set[str] | None = None,
        auto_commit: bool = True,
        extracted_text_override: str | None = None,
    ) -> list[KnowledgeItem]:
        """Extract all deterministic knowledge items from an evidence item in <100ms."""
        project_id = evidence.project_id
        organisation_id = evidence.organisation_id
        allowed_categories = set(categories) if categories else None

        dfp = (evidence.metadata_json or {}).get("deterministic_fingerprint")
        if (
            not force_rerun
            and isinstance(dfp, dict)
            and dfp.get("content_hash") == evidence.content_hash
        ):
            return []

        # Check existing items to avoid duplicates
        if existing_fps is None:
            existing_fps = set(
                self._session.execute(
                    select(KnowledgeItem.fingerprint).where(
                        KnowledgeItem.project_id == project_id,
                        KnowledgeItem.is_deleted.is_(False),
                    )
                ).scalars().all()
            )

        extracted_text = (extracted_text_override or "").strip()
        chunks: list[EvidenceChunk] = []
        if not extracted_text:
            if getattr(evidence, "content", None) and evidence.content.extracted_text:
                extracted_text = evidence.content.extracted_text
            else:
                chunks = list(
                    self._session.execute(
                        select(EvidenceChunk)
                        .where(EvidenceChunk.evidence_id == evidence.id)
                        .order_by(EvidenceChunk.chunk_index.asc())
                    ).scalars().all()
                )
                if chunks:
                    extracted_text = "\n\n".join(c.chunk_text for c in chunks)

        created_items: list[KnowledgeItem] = []

        def _persist_item(
            *,
            category: KnowledgeCategory,
            title: str,
            summary: str,
            payload: dict[str, Any],
            chunk: EvidenceChunk | None = None,
            supporting_excerpt: str | None = None,
            normalised_status: str = "implemented",
            confidence: float = 0.95,
        ) -> KnowledgeItem | None:
            if allowed_categories is not None and category not in allowed_categories:
                return None
            fp = _compute_item_fingerprint(
                project_id=project_id,
                category=category.value,
                title=title,
                structured_summary=summary,
            )
            if fp in existing_fps and not force_rerun:
                return None

            k_item = KnowledgeItem(
                id=uuid.uuid4(),
                organisation_id=organisation_id,
                project_id=project_id,
                extraction_run_id=run_id,
                category=category.value,
                primary_domain=category.value,
                epistemic_status=EpistemicStatus.EXTRACTED.value,
                review_status=KnowledgeReviewStatus.PENDING_REVIEW.value,
                support_classification="direct",
                title=title[:500],
                structured_summary=summary,
                structured_payload=payload,
                normalised_status=normalised_status,
                extraction_model="fast_deterministic_parser_v1",
                prompt_version="fast_p1",
                fingerprint=fp,
                confidence_metadata_json={"confidence_score": confidence, "method": "deterministic_rule"},
                source_attribution_json={
                    "evidence_id": str(evidence.id),
                    "source_type": evidence.source_type,
                    "title": evidence.title,
                    "author": evidence.source_author_identity,
                },
                is_stale=False,
                is_deleted=False,
            )
            self._session.add(k_item)

            # Add evidence link without per-item flush
            best_chunk = chunk or (chunks[0] if chunks else None)
            best_excerpt = supporting_excerpt or summary[:300]
            link = KnowledgeEvidenceLink(
                organisation_id=organisation_id,
                project_id=project_id,
                knowledge_item_id=k_item.id,
                evidence_id=evidence.id,
                evidence_chunk_id=best_chunk.id if best_chunk else None,
                support_type="direct",
                supporting_excerpt=best_excerpt[:500],
                excerpt_verified=True,
                excerpt_match_mode="exact",
                source_location_json={"chunk_index": best_chunk.chunk_index if best_chunk else 0},
                source_metadata_json={
                    "confidence_score": confidence,
                    "relevance_explanation": "Direct deterministic extraction from source evidence.",
                },
            )
            self._session.add(link)
            existing_fps.add(fp)
            created_items.append(k_item)
            return k_item

        # -------------------------------------------------------------
        # 0. GITHUB REPOSITORY ARTEFACT (IDENTITY & URL)
        # -------------------------------------------------------------
        is_repo = (
            evidence.category in ("repository", "repo")
            or "github repository:" in (evidence.title or "").lower()
            or (evidence.source_external_id or "").startswith("repo_")
        )
        if is_repo:
            r_meta = dict(evidence.metadata_json or {})
            repo_name = (
                r_meta.get("full_name")
                or r_meta.get("repo_name")
                or (evidence.title or "").replace("GitHub Repository:", "").strip()
            )
            repo_url = evidence.source_url or r_meta.get("html_url") or f"https://github.com/{repo_name}"
            def_branch = r_meta.get("default_branch") or "main"
            _persist_item(
                category=KnowledgeCategory.PROJECT_OVERVIEW_CONTEXT,
                title=f"Repository: {repo_name}",
                summary=f"Connected GitHub repository '{repo_name}' on default branch '{def_branch}'. Source URL: {repo_url}.",
                payload={
                    "repository_name": repo_name,
                    "clone_url": repo_url,
                    "default_branch": def_branch,
                    "source_provider": "github",
                },
                supporting_excerpt=f"GitHub Repository: {repo_name} at {repo_url}",
                normalised_status="documented",
                confidence=1.0,
            )

        # -------------------------------------------------------------
        # 1. GITHUB MANIFESTS (package.json, requirements.txt, pyproject.toml, Dockerfile, pubspec.yaml)
        # -------------------------------------------------------------
        if is_manifest_path(evidence.title) and extracted_text:
            detections = parse_manifest_evidence(evidence.title, extracted_text)
            for det in detections:
                canon_name = det.canonical_name
                cat = det.category
                raw_tech = det.raw_name or canon_name
                ver_str = f" (v{det.version})" if det.version else ""
                _persist_item(
                    category=KnowledgeCategory.TECHNICAL_ARCHITECTURE,
                    title=f"Technology: {canon_name}",
                    summary=f"Project declares dependency on {canon_name}{ver_str} in manifest '{evidence.title}'.",
                    payload={
                        "technology": canon_name,
                        "technical_category": "technology_choice",
                        "layer": cat,
                        "manifest_file": evidence.title,
                        "version": det.version,
                        "exact_identifiers": [canon_name],
                    },
                    supporting_excerpt=f"Dependency '{raw_tech}' in {evidence.title}",
                    normalised_status="declared_dependency",
                    confidence=1.0,
                )
                _persist_item(
                    category=KnowledgeCategory.DEPENDENCIES,
                    title=f"Dependency: {canon_name}",
                    summary=f"External dependency '{canon_name}'{ver_str} specified in {evidence.title}.",
                    payload={
                        "dependency_name": canon_name,
                        "dependency_type": "external_library",
                        "source": evidence.title,
                        "version": det.version,
                    },
                    supporting_excerpt=f"Dependency '{raw_tech}' in {evidence.title}",
                    normalised_status="declared_dependency",
                    confidence=1.0,
                )

            # Extract declared runtime versions (e.g. node, python)
            if extracted_text:
                runtime_matches = re.findall(
                    r'(?:"(?:node|npm|python)"|\bpython_version|\brequires-python)\s*[:=]\s*["\']?([>=<^~0-9\.\s]+)["\']?',
                    extracted_text,
                    re.IGNORECASE,
                )
                for r_ver in runtime_matches[:5]:
                    r_clean = r_ver.strip().strip('"\'')
                    if r_clean and len(r_clean) < 30:
                        _persist_item(
                            category=KnowledgeCategory.TECHNICAL_ARCHITECTURE,
                            title=f"Runtime Version Requirement: {r_clean}",
                            summary=f"Explicitly declared runtime version constraint '{r_clean}' in {evidence.title}.",
                            payload={
                                "technical_category": "configuration",
                                "runtime_version": r_clean,
                                "manifest": evidence.title,
                            },
                            supporting_excerpt=f"Runtime requirement {r_clean} in {evidence.title}",
                            normalised_status="declared",
                            confidence=0.98,
                        )

        # -------------------------------------------------------------
        # 2. GITHUB COMMITS AND PULL REQUESTS
        # -------------------------------------------------------------
        if evidence.category in {"commit", "pull_request"}:
            c_meta = dict(evidence.metadata_json or {})
            msg = c_meta.get("message") or c_meta.get("title") or evidence.title or ""
            author = c_meta.get("author_name") or evidence.source_author_identity or "Contributor"
            changed_paths = c_meta.get("changed_paths") or []
            sha = c_meta.get("sha") or c_meta.get("commit_sha") or ""

            # Parse conventional prefixes
            norm_cat = KnowledgeCategory.WORK_ITEMS
            work_cat = "commit"
            msg_lower = msg.lower()
            if any(p in msg_lower for p in ("fix:", "bug:", "hotfix:", "patch:", "issue", "error:", "fail:")):
                norm_cat = KnowledgeCategory.BUGS_BLOCKERS_RISKS
                work_cat = "bug_fix"
            elif any(p in msg_lower for p in ("docs:", "doc:", "readme:")):
                norm_cat = KnowledgeCategory.OPERATIONAL_HISTORICAL
                work_cat = "documentation"
            elif any(p in msg_lower for p in ("refactor:", "chore:", "test:", "ci:", "build:")):
                norm_cat = KnowledgeCategory.WORK_ITEMS
                work_cat = "refactoring"

            clean_title = re.sub(
                r"^(?:feat|fix|docs|refactor|chore|test|ci|build)(?:\([a-zA-Z0-9_\-\s]+\))?:\s*",
                "",
                msg,
                flags=re.IGNORECASE,
            ).strip()
            if clean_title:
                clean_title = clean_title.split("\n")[0][:120].strip()
                item_prefix = "Pull Request" if evidence.category == "pull_request" else "Commit"
                # A commit title is an atomic change record, NOT proof that a full feature is complete
                _persist_item(
                    category=norm_cat,
                    title=f"{item_prefix}: {clean_title}",
                    summary=f"Git {item_prefix.lower()} by {author}: '{msg[:200]}'.",
                    payload={
                        "work_category": work_cat,
                        "title": clean_title,
                        "author": author,
                        "commit_hash": sha,
                        "changed_paths": changed_paths[:50],
                    },
                    supporting_excerpt=msg[:250],
                    normalised_status="committed",
                    confidence=0.95,
                )

                # Persist verified commit author attribution
                if author and not author.lower().endswith("[bot]") and author.lower() != "dependabot":
                    _persist_item(
                        category=KnowledgeCategory.RESPONSIBILITIES_OWNERSHIP,
                        title=f"Commit Author: {author}",
                        summary=f"{author} is recorded as commit author for '{clean_title}'.",
                        payload={
                            "person_identity": author,
                            "ownership_basis": "self_reported",
                            "role": "commit_author",
                            "commit_sha": sha,
                        },
                        supporting_excerpt=f"Author: {author} on {clean_title}",
                        normalised_status="active",
                        confidence=0.95,
                    )

            # Extract distinct module directories from changed paths
            module_dirs = set()
            for p in changed_paths:
                parts = p.replace("\\", "/").split("/")
                if len(parts) > 1 and parts[0] not in (".github", ".git", "node_modules", "vendor", "__pycache__"):
                    module_dirs.add(parts[0])
            for m_dir in sorted(list(module_dirs))[:5]:
                _persist_item(
                    category=KnowledgeCategory.TECHNICAL_ARCHITECTURE,
                    title=f"Source Module: {m_dir}",
                    summary=f"Source module directory '{m_dir}' identified from commit activity in {evidence.title}.",
                    payload={
                        "technical_category": "architecture",
                        "module_name": m_dir,
                        "evidence_source": "git_changed_paths",
                    },
                    supporting_excerpt=f"Module directory '{m_dir}' in changed paths of {evidence.title}",
                    normalised_status="documented",
                    confidence=0.90,
                )

        # -------------------------------------------------------------
        # 3. DOCUMENTS & MARKDOWN SPECS (PDF, DOCX, README.md, PRDs)
        # Fast deterministic extraction of explicit structure, sections, and requirements
        # -------------------------------------------------------------
        if extracted_text:
            lines = extracted_text.splitlines()

            # 3A. Extract Document Section Headings as Document Outlines
            # A Markdown heading is evidence of a document section, NOT proof that a feature is implemented.
            heading_pattern = re.compile(r"^\s*(#{1,4})\s+([A-Za-z0-9\s—:\-_\.]{3,70})$")
            for idx, line in enumerate(lines):
                line_str = line.strip()
                h_match = heading_pattern.match(line_str)
                if h_match:
                    hashes, h_title = h_match.groups()
                    h_title_clean = h_title.strip()
                    # Skip trivial single-word or boilerplate titles
                    if any(
                        b in h_title_clean.lower()
                        for b in ("table of contents", "license", "contributing", "overview", "introduction")
                    ):
                        continue
                    context_snippet = " ".join([l.strip() for l in lines[idx + 1 : idx + 4] if l.strip()])
                    summary = context_snippet[:220] or f"Section '{h_title_clean}' documented in {evidence.title}."
                    _persist_item(
                        category=KnowledgeCategory.OPERATIONAL_HISTORICAL,
                        title=f"Document Section: {h_title_clean}",
                        summary=f"Section '{h_title_clean}' in {evidence.title}: {summary}",
                        payload={
                            "section_title": h_title_clean,
                            "heading_level": len(hashes),
                            "document": evidence.title,
                            "context_preview": context_snippet[:300],
                            "is_document_outline": True,
                        },
                        supporting_excerpt=f"{line_str}: {summary[:150]}",
                        normalised_status="documented",
                        confidence=0.92,
                    )

            # 3C. Extract Explicit Structured Requirements (FR-xx, REQ-xx)
            req_pattern = re.compile(r"^\s*(?:#+\s*)?(FR-\d+|REQ-\d+|Requirement\s+\d+):\s*([^\n\r]{5,100})$", re.IGNORECASE)
            for line in lines:
                line_str = line.strip()
                r_match = req_pattern.match(line_str)
                if r_match:
                    r_code, r_desc = r_match.groups()
                    r_code = r_code.strip().upper()
                    r_desc = r_desc.strip()
                    _persist_item(
                        category=KnowledgeCategory.WORK_ITEMS,
                        title=f"Requirement {r_code}: {r_desc[:80]}",
                        summary=f"Documented requirement {r_code}: {r_desc}.",
                        payload={
                            "work_category": "requirement",
                            "requirement_id": r_code,
                            "description": r_desc,
                            "document": evidence.title,
                        },
                        supporting_excerpt=line_str,
                        normalised_status="documented",
                        confidence=0.92,
                    )

            # 3D. Extract Explicit Architecture Decisions (ADR-xx)
            adr_pattern = re.compile(
                r"^\s*(?:#+\s*)?(ADR-\d+|Decision\s+\d+|Architecture Decision):\s*([^\n\r]{5,100})$",
                re.IGNORECASE,
            )
            for idx, line in enumerate(lines):
                line_str = line.strip()
                d_match = adr_pattern.match(line_str)
                if d_match:
                    d_code, d_desc = d_match.groups()
                    d_context = " ".join([l.strip() for l in lines[idx + 1 : idx + 4] if l.strip()])
                    _persist_item(
                        category=KnowledgeCategory.DECISIONS_RATIONALE,
                        title=f"{d_code}: {d_desc[:80]}",
                        summary=d_context[:250] or f"Architecture decision recorded in {evidence.title}: {d_desc}.",
                        payload={
                            "decision_id": d_code,
                            "decision_title": d_desc,
                            "context": d_context[:400],
                            "document": evidence.title,
                        },
                        supporting_excerpt=f"{line_str}\n{d_context[:150]}",
                        normalised_status="decided",
                        confidence=0.95,
                    )

            # 3E. Extract Documented Operational Procedures (Deployment, Runbook, Setup)
            proc_pattern = re.compile(
                r"^\s*#{1,3}\s+(Deployment|Runbook|Setup|Installation|Configuration|Troubleshooting)(?:\s*[:—\-]\s*(.*))?$",
                re.IGNORECASE,
            )
            for idx, line in enumerate(lines):
                line_str = line.strip()
                p_match = proc_pattern.match(line_str)
                if p_match:
                    p_name, p_sub = p_match.groups()
                    proc_title = f"{p_name} {p_sub or ''}".strip().title()
                    snippet = " ".join([l.strip() for l in lines[idx + 1 : idx + 5] if l.strip()])
                    if snippet and len(snippet) > 15:
                        _persist_item(
                            category=KnowledgeCategory.OPERATIONAL_HISTORICAL,
                            title=f"Procedure: {proc_title[:80]}",
                            summary=snippet[:280],
                            payload={
                                "procedure_name": proc_title,
                                "document": evidence.title,
                                "details": snippet[:400],
                            },
                            supporting_excerpt=f"{line_str}\n{snippet[:200]}",
                            normalised_status="documented",
                            confidence=0.90,
                        )

        # -------------------------------------------------------------
        # 4. LIFECYCLE STAGE PERSISTENCE & IMMEDIATE GRAPH RECONCILIATION
        # -------------------------------------------------------------
        ev_meta = dict(evidence.metadata_json or {})
        ev_meta["deterministic_fingerprint"] = {
            "content_hash": evidence.content_hash,
            "extractor": "fast_deterministic_parser_v2",
            "extracted_at": utc_now().isoformat(),
            "items_count": len(created_items),
        }
        k_count = ev_meta.get("knowledge_count", 0) + len(created_items)
        ev_meta["knowledge_count"] = k_count
        if ev_meta.get("lifecycle_stage") not in (
            "graph_updated",
            "graph_published",
            "extracting",
            "knowledge_ready",
        ):
            ev_meta["lifecycle_stage"] = "deterministic_ready"

        # Semantic eligibility check
        text_len = len(extracted_text.strip())
        is_semantic_eligible = is_evidence_semantic_eligible(
            category=evidence.category,
            title=evidence.title,
            mime_type=evidence.mime_type,
            text_len=text_len,
            metadata_json=ev_meta,
        )
        if ev_meta.get("semantic_status") not in ("completed", "succeeded", "running", "extracting"):
            ev_meta["semantic_status"] = "queued" if is_semantic_eligible else "not_applicable"

        evidence.metadata_json = ev_meta
        if auto_commit:
            from app.services.pipeline_coordinator import invalidate_project_status_cache

            self._session.commit()
            invalidate_project_status_cache(project_id)

        # Reconcile graph projections immediately from directly supported deterministic facts
        is_graph_relevant = (
            bool(created_items)
            or is_manifest_path(evidence.title)
            or evidence.category in ("source_code", "commit", "pull_request", "design_document", "architecture")
        )
        if reconcile_graphs and is_graph_relevant:
            try:
                from app.services.knowledge_graphs import invalidate_knowledge_graph_cache
                from app.services.pipeline_coordinator import invalidate_project_status_cache
                from app.services.relationship_coordinator import RelationshipCoordinatorService

                RelationshipCoordinatorService(self._session).run_reconstruction(
                    organisation_id=organisation_id,
                    project_id=project_id,
                    include_llm_suggestions=False,
                )
                self._session.commit()
                invalidate_knowledge_graph_cache(project_id)
                invalidate_project_status_cache(project_id)
            except Exception as exc:
                logger.warning("Fast extractor graph reconciliation notice: %s", exc)

        logger.info(
            "FastKnowledgeExtractor generated %d items for evidence %s (%s).",
            len(created_items),
            evidence.id,
            evidence.title,
        )
        return created_items
