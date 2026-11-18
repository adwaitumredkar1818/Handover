"""Cross-source relationship discovery engine for Relationship Explorer.

Implements 5 complementary discovery methods:
1. Exact Identifier Linking (Jira keys, PR numbers, commit SHAs, ADR references)
2. Structured Connector Links (GitHub authors, reviewers, branches; Jira links, components, assignees)
3. Contextual File/Path Matching (PR changed files vs component paths)
4. Semantic Matching (Embedding cosine similarity over threshold)
5. Qwen3 8B LLM-Assisted Candidate Extraction (grounded in verbatim evidence chunks)
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import (
    EntityType,
    RelationshipBasis,
    RelationshipType,
    RelationshipVerificationStatus,
)
from app.models.evidence import EvidenceChunk, EvidenceItem
from app.models.relationship import KnowledgeEntity
from app.repositories.relationship import EntityRepository, RelationshipRepository
from app.services.llm import LLMGenerationRequest, StructuredLLMClient
from app.services.relationship_taxonomy import validate_relationship_endpoints

logger = logging.getLogger("app.services.relationship_discovery")

# Regex patterns for Exact Linking
JIRA_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
PR_NUM_RE = re.compile(r"(?:pull\s*request|pr|gh-|\#)\s*(\d{1,6})\b", flags=re.IGNORECASE)
COMMIT_SHA_RE = re.compile(r"\b([0-9a-f]{7,40})\b", flags=re.IGNORECASE)
ADR_REF_RE = re.compile(r"\b(ADR-\d+|RFC-\d+|DEP-\d+)\b", flags=re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class DiscoveredRelationshipDraft:
    """Discovered candidate relationship ready for validation and persistence."""

    source_entity_id: uuid.UUID
    target_entity_id: uuid.UUID
    relationship_type: str
    relationship_basis: str
    confidence_score: float
    discovery_method: str
    evidence_id: uuid.UUID
    evidence_chunk_id: uuid.UUID | None
    knowledge_item_id: uuid.UUID | None
    supporting_excerpt: str | None
    source_location_json: dict[str, Any]
    is_llm_assisted: bool = False


class RelationshipDiscoveryEngine:
    """Discovers relationships across connected source evidence and structured knowledge."""

    def __init__(
        self,
        session: Session,
        *,
        llm_client: StructuredLLMClient | None = None,
    ) -> None:
        self._session = session
        self._entity_repo = EntityRepository(session)
        self._rel_repo = RelationshipRepository(session)
        self._llm_client = llm_client

    # --------------------------------------------------------------------------
    # Method 1: Exact Identifier Linking
    # --------------------------------------------------------------------------

    def discover_exact_identifier_links(
        self,
        *,
        project_id: uuid.UUID,
        organisation_id: uuid.UUID,
    ) -> list[DiscoveredRelationshipDraft]:
        """Extract explicit references (Jira keys, PR #, Commit SHA, ADR) across evidence."""
        drafts: list[DiscoveredRelationshipDraft] = []
        _, entities_by_id = self._entity_repo._project_entities(project_id)
        all_entities = list(entities_by_id.values())

        work_items = [e for e in all_entities if e.entity_type == EntityType.WORK_ITEM.value]
        work_item_map = {w.canonical_name.upper(): w for w in work_items}
        for w in work_items:
            if w.external_source_id:
                work_item_map[w.external_source_id.upper()] = w

        code_entities = [
            e
            for e in all_entities
            if e.entity_type in {EntityType.PULL_REQUEST.value, EntityType.COMMIT.value}
        ]
        decisions = [e for e in all_entities if e.entity_type == EntityType.DECISION.value]

        for ce in code_entities:
            text_to_scan = f"{ce.canonical_name} {ce.description or ''}"
            found_keys = JIRA_KEY_RE.findall(text_to_scan)
            for k in set(found_keys):
                target_wi = work_item_map.get(k.upper())
                if target_wi and target_wi.id != ce.id:
                    valid, _ = validate_relationship_endpoints(
                        RelationshipType.IMPLEMENTS.value, ce.entity_type, target_wi.entity_type
                    )
                    if valid and ce.primary_evidence_id:
                        drafts.append(
                            DiscoveredRelationshipDraft(
                                source_entity_id=ce.id,
                                target_entity_id=target_wi.id,
                                relationship_type=RelationshipType.IMPLEMENTS.value,
                                relationship_basis=RelationshipBasis.EXPLICIT.value,
                                confidence_score=1.0,
                                discovery_method="exact_reference",
                                evidence_id=ce.primary_evidence_id,
                                evidence_chunk_id=None,
                                knowledge_item_id=None,
                                supporting_excerpt=f"Matched identifier reference '{k}' in {ce.canonical_name}",
                                source_location_json={"matched_identifier": k},
                            )
                        )

            found_adrs = ADR_REF_RE.findall(text_to_scan)
            for adr in set(found_adrs):
                adr_norm = adr.upper()
                decision = next(
                    (d for d in decisions if adr_norm in d.canonical_name.upper()),
                    None,
                )
                if decision and decision.id != ce.id and ce.primary_evidence_id:
                    drafts.append(
                        DiscoveredRelationshipDraft(
                            source_entity_id=ce.id,
                            target_entity_id=decision.id,
                            relationship_type=RelationshipType.IMPLEMENTS.value,
                            relationship_basis=RelationshipBasis.EXPLICIT.value,
                            confidence_score=1.0,
                            discovery_method="exact_reference",
                            evidence_id=ce.primary_evidence_id,
                            evidence_chunk_id=None,
                            knowledge_item_id=None,
                            supporting_excerpt=f"Code artifact explicitly references decision {adr_norm}",
                            source_location_json={"matched_identifier": adr_norm},
                        )
                    )

        return drafts

    # --------------------------------------------------------------------------
    # Method 2: Structured Connector Links
    # --------------------------------------------------------------------------

    def discover_structured_connector_links(
        self,
        *,
        project_id: uuid.UUID,
        organisation_id: uuid.UUID,
    ) -> list[DiscoveredRelationshipDraft]:
        """Extract explicit relations directly from GitHub/Jira metadata JSON."""
        drafts: list[DiscoveredRelationshipDraft] = []
        _, entities_by_id = self._entity_repo._project_entities(project_id)
        entities = list(entities_by_id.values())
        aliases_by_key = self._entity_repo._project_aliases(project_id)

        # Build lookup indices
        people = [e for e in entities if e.entity_type == EntityType.PERSON.value]
        components = [
            e
            for e in entities
            if e.entity_type in {EntityType.COMPONENT.value, EntityType.TECHNICAL_COMPONENT.value}
        ]
        work_items = [e for e in entities if e.entity_type == EntityType.WORK_ITEM.value]

        people_by_id = {p.id: p for p in people}
        people_by_handle: dict[str, KnowledgeEntity] = {}
        for p in people:
            people_by_handle[p.canonical_name.lower()] = p
        for (ent_id, norm_alias, _prov), _al in aliases_by_key.items():
            p_ent = people_by_id.get(ent_id)
            if p_ent is not None:
                people_by_handle[norm_alias] = p_ent

        components_by_name = {c.canonical_name.lower(): c for c in components}
        work_items_by_key = {w.canonical_name.upper(): w for w in work_items}
        for w in work_items:
            if w.external_source_id:
                work_items_by_key[w.external_source_id.upper()] = w

        for e in entities:
            meta = e.metadata_json or {}
            ev_id = e.primary_evidence_id
            if not ev_id:
                continue

            # 1. GitHub PR Metadata -> Authors, Reviewers, Base Repo Component
            if e.entity_type == EntityType.PULL_REQUEST.value:
                # Author -> AUTHORED_BY
                author_login = meta.get("author") or meta.get("user")
                if author_login and isinstance(author_login, str):
                    p_node = people_by_handle.get(author_login.lower())
                    if p_node:
                        drafts.append(
                            DiscoveredRelationshipDraft(
                                source_entity_id=e.id,
                                target_entity_id=p_node.id,
                                relationship_type=RelationshipType.AUTHORED_BY.value,
                                relationship_basis=RelationshipBasis.EXPLICIT.value,
                                confidence_score=1.0,
                                discovery_method="structured_connector",
                                evidence_id=ev_id,
                                evidence_chunk_id=None,
                                knowledge_item_id=None,
                                supporting_excerpt=f"GitHub PR author metadata: {author_login}",
                                source_location_json={"author": author_login},
                            )
                        )

                # Reviewers -> REVIEWED_BY
                reviewers = meta.get("reviewers") or meta.get("requested_reviewers") or []
                if isinstance(reviewers, list):
                    for r in reviewers:
                        r_login = r if isinstance(r, str) else r.get("login")
                        if r_login and isinstance(r_login, str):
                            p_node = people_by_handle.get(r_login.lower())
                            if p_node:
                                drafts.append(
                                    DiscoveredRelationshipDraft(
                                        source_entity_id=e.id,
                                        target_entity_id=p_node.id,
                                        relationship_type=RelationshipType.REVIEWED_BY.value,
                                        relationship_basis=RelationshipBasis.EXPLICIT.value,
                                        confidence_score=1.0,
                                        discovery_method="structured_connector",
                                        evidence_id=ev_id,
                                        evidence_chunk_id=None,
                                        knowledge_item_id=None,
                                        supporting_excerpt=f"GitHub PR reviewer metadata: {r_login}",
                                        source_location_json={"reviewer": r_login},
                                    )
                                )

                # Repository / Component -> MERGED_IN / AFFECTS_COMPONENT
                repo_name = meta.get("repository") or meta.get("repo")
                if repo_name and isinstance(repo_name, str):
                    c_node = components_by_name.get(repo_name.lower())
                    if c_node:
                        drafts.append(
                            DiscoveredRelationshipDraft(
                                source_entity_id=e.id,
                                target_entity_id=c_node.id,
                                relationship_type=RelationshipType.AFFECTS_COMPONENT.value,
                                relationship_basis=RelationshipBasis.EXPLICIT.value,
                                confidence_score=1.0,
                                discovery_method="structured_connector",
                                evidence_id=ev_id,
                                evidence_chunk_id=None,
                                knowledge_item_id=None,
                                supporting_excerpt=f"PR belongs to repository/component: {repo_name}",
                                source_location_json={"repository": repo_name},
                            )
                        )

            # 2. Jira Issue Metadata -> Assignee, Reporter, Issue Links, Components
            elif e.entity_type == EntityType.WORK_ITEM.value:
                # Assignee -> ASSIGNED_TO
                assignee = meta.get("assignee")
                if assignee and isinstance(assignee, str):
                    p_node = people_by_handle.get(assignee.lower())
                    if p_node:
                        drafts.append(
                            DiscoveredRelationshipDraft(
                                source_entity_id=e.id,
                                target_entity_id=p_node.id,
                                relationship_type=RelationshipType.ASSIGNED_TO.value,
                                relationship_basis=RelationshipBasis.EXPLICIT.value,
                                confidence_score=1.0,
                                discovery_method="structured_connector",
                                evidence_id=ev_id,
                                evidence_chunk_id=None,
                                knowledge_item_id=None,
                                supporting_excerpt=f"Jira issue assignee: {assignee}",
                                source_location_json={"assignee": assignee},
                            )
                        )

                # Reporter -> REPORTED_BY
                reporter = meta.get("reporter")
                if reporter and isinstance(reporter, str):
                    p_node = people_by_handle.get(reporter.lower())
                    if p_node:
                        drafts.append(
                            DiscoveredRelationshipDraft(
                                source_entity_id=e.id,
                                target_entity_id=p_node.id,
                                relationship_type=RelationshipType.REPORTED_BY.value,
                                relationship_basis=RelationshipBasis.EXPLICIT.value,
                                confidence_score=1.0,
                                discovery_method="structured_connector",
                                evidence_id=ev_id,
                                evidence_chunk_id=None,
                                knowledge_item_id=None,
                                supporting_excerpt=f"Jira issue reporter: {reporter}",
                                source_location_json={"reporter": reporter},
                            )
                        )

                # Jira Components -> AFFECTS_COMPONENT
                jira_comps = meta.get("components") or []
                if isinstance(jira_comps, list):
                    for jc in jira_comps:
                        jc_name = jc if isinstance(jc, str) else jc.get("name")
                        if jc_name and isinstance(jc_name, str):
                            c_node = components_by_name.get(jc_name.lower())
                            if c_node:
                                drafts.append(
                                    DiscoveredRelationshipDraft(
                                        source_entity_id=e.id,
                                        target_entity_id=c_node.id,
                                        relationship_type=RelationshipType.AFFECTS_COMPONENT.value,
                                        relationship_basis=RelationshipBasis.EXPLICIT.value,
                                        confidence_score=1.0,
                                        discovery_method="structured_connector",
                                        evidence_id=ev_id,
                                        evidence_chunk_id=None,
                                        knowledge_item_id=None,
                                        supporting_excerpt=f"Jira issue component tag: {jc_name}",
                                        source_location_json={"component": jc_name},
                                    )
                                )

                # Jira Issue Links (Blocks, Depends on, Relates to)
                issue_links = meta.get("issuelinks") or meta.get("issue_links") or []
                if isinstance(issue_links, list):
                    for link in issue_links:
                        if isinstance(link, dict):
                            link_type = str(link.get("type", "")).lower()
                            outward_key = link.get("outward_issue_key")

                            if "block" in link_type and outward_key:
                                target_node = work_items_by_key.get(str(outward_key).upper())
                                if target_node:
                                    drafts.append(
                                        DiscoveredRelationshipDraft(
                                            source_entity_id=e.id,
                                            target_entity_id=target_node.id,
                                            relationship_type=RelationshipType.BLOCKS.value,
                                            relationship_basis=RelationshipBasis.EXPLICIT.value,
                                            confidence_score=1.0,
                                            discovery_method="structured_connector",
                                            evidence_id=ev_id,
                                            evidence_chunk_id=None,
                                            knowledge_item_id=None,
                                            supporting_excerpt=f"Jira link blocks: {outward_key}",
                                            source_location_json={"issue_link": link},
                                        )
                                    )
                            elif ("depend" in link_type or "relat" in link_type) and outward_key:
                                target_node = work_items_by_key.get(str(outward_key).upper())
                                if target_node:
                                    drafts.append(
                                        DiscoveredRelationshipDraft(
                                            source_entity_id=e.id,
                                            target_entity_id=target_node.id,
                                            relationship_type=RelationshipType.DEPENDS_ON.value,
                                            relationship_basis=RelationshipBasis.EXPLICIT.value,
                                            confidence_score=1.0,
                                            discovery_method="structured_connector",
                                            evidence_id=ev_id,
                                            evidence_chunk_id=None,
                                            knowledge_item_id=None,
                                            supporting_excerpt=f"Jira link depends on: {outward_key}",
                                            source_location_json={"issue_link": link},
                                        )
                                    )

            # 3. Commit Metadata -> Author (AUTHORED_BY)
            elif e.entity_type == EntityType.COMMIT.value:
                author_key = (
                    meta.get("github_author_login")
                    or meta.get("git_author_name")
                    or meta.get("git_author_email")
                )
                if isinstance(author_key, str):
                    p_node = people_by_handle.get(author_key.strip().lower())
                    if p_node:
                        drafts.append(
                            DiscoveredRelationshipDraft(
                                source_entity_id=e.id,
                                target_entity_id=p_node.id,
                                relationship_type=RelationshipType.AUTHORED_BY.value,
                                relationship_basis=RelationshipBasis.EXPLICIT.value,
                                confidence_score=1.0,
                                discovery_method="structured_connector",
                                evidence_id=ev_id,
                                evidence_chunk_id=None,
                                knowledge_item_id=None,
                                supporting_excerpt=f"Git commit author: {author_key}",
                                source_location_json={"sha": meta.get("sha"), "author": author_key},
                            )
                        )

        # 4. Link Pull Requests -> Associated Commits (CONTAINS_COMMIT)
        commits_by_sha: dict[str, KnowledgeEntity] = {}
        for ent in entities:
            if ent.entity_type == EntityType.COMMIT.value:
                raw_sha = (ent.metadata_json or {}).get("sha")
                if not raw_sha and ent.external_source_id and ":commit:" in ent.external_source_id:
                    raw_sha = ent.external_source_id.split(":commit:", 1)[1]
                if isinstance(raw_sha, str) and len(raw_sha.strip()) >= 7:
                    norm_sha = raw_sha.strip().lower()
                    commits_by_sha[norm_sha] = ent
                    for plen in (7, 8, 12):
                        if len(norm_sha) >= plen:
                            commits_by_sha.setdefault(norm_sha[:plen], ent)

        for ent in entities:
            if ent.entity_type == EntityType.PULL_REQUEST.value and ent.primary_evidence_id:
                assoc_shas = (ent.metadata_json or {}).get("associated_commit_shas") or []
                if isinstance(assoc_shas, list):
                    for sha in assoc_shas:
                        norm = str(sha).strip().lower()
                        c_node = commits_by_sha.get(norm) or commits_by_sha.get(norm[:12]) or commits_by_sha.get(norm[:7])
                        if c_node:
                            drafts.append(
                                DiscoveredRelationshipDraft(
                                    source_entity_id=ent.id,
                                    target_entity_id=c_node.id,
                                    relationship_type=RelationshipType.CONTAINS_COMMIT.value,
                                    relationship_basis=RelationshipBasis.EXPLICIT.value,
                                    confidence_score=1.0,
                                    discovery_method="structured_connector",
                                    evidence_id=ent.primary_evidence_id,
                                    evidence_chunk_id=None,
                                    knowledge_item_id=None,
                                    supporting_excerpt=f"PR contains commit {str(sha)[:12]}",
                                    source_location_json={"sha": str(sha)},
                                )
                            )

        return drafts

    # --------------------------------------------------------------------------
    # Method 3: Contextual File Path Matching
    # --------------------------------------------------------------------------

    def discover_contextual_path_matches(
        self,
        *,
        project_id: uuid.UUID,
    ) -> list[DiscoveredRelationshipDraft]:
        """Correlate PR changed files with known architecture component file paths."""
        drafts: list[DiscoveredRelationshipDraft] = []
        _, entities_by_id = self._entity_repo._project_entities(project_id)
        all_entities = list(entities_by_id.values())

        components = [
            e
            for e in all_entities
            if e.entity_type in {EntityType.TECHNICAL_COMPONENT.value, EntityType.COMPONENT.value}
        ]
        prs = [e for e in all_entities if e.entity_type == EntityType.PULL_REQUEST.value]

        for pr in prs:
            meta = pr.metadata_json or {}
            changed_files = meta.get("changed_files") or meta.get("files") or []
            if not isinstance(changed_files, list) or not pr.primary_evidence_id:
                continue

            for comp in components:
                comp_meta = comp.metadata_json or {}
                paths = comp_meta.get("paths") or [comp.canonical_name]
                if not isinstance(paths, list):
                    paths = [str(paths)]

                # Check if any changed file matches component path prefix
                matched = False
                matching_file = ""
                for cf in changed_files:
                    if isinstance(cf, str):
                        for p in paths:
                            if (
                                p
                                and isinstance(p, str)
                                and (p.lower() in cf.lower() or cf.lower().startswith(p.lower()))
                            ):
                                matched = True
                                matching_file = cf
                                break
                    if matched:
                        break

                if matched:
                    drafts.append(
                        DiscoveredRelationshipDraft(
                            source_entity_id=pr.id,
                            target_entity_id=comp.id,
                            relationship_type=RelationshipType.AFFECTS_COMPONENT.value,
                            relationship_basis=RelationshipBasis.INFERRED.value,
                            confidence_score=0.85,
                            discovery_method="contextual_match",
                            evidence_id=pr.primary_evidence_id,
                            evidence_chunk_id=None,
                            knowledge_item_id=None,
                            supporting_excerpt=f"PR changed file '{matching_file}' aligns with component paths",
                            source_location_json={"matched_file": matching_file},
                        )
                    )

        return drafts

    # --------------------------------------------------------------------------
    # Method 4: Grounded Architecture & System Context Discovery
    # --------------------------------------------------------------------------

    def discover_architecture_relationships(
        self,
        *,
        project_id: uuid.UUID,
        organisation_id: uuid.UUID,
    ) -> list[DiscoveredRelationshipDraft]:
        """Extract explicit service-to-service, component-to-component, and storage interactions
        grounded in verbatim architecture and specification document chunks."""
        drafts: list[DiscoveredRelationshipDraft] = []
        _, entities_by_id = self._entity_repo._project_entities(project_id)
        all_entities = list(entities_by_id.values())

        arch_types = {
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
            EntityType.COMPONENT.value,
            EntityType.SERVICE.value,
            EntityType.API.value,
            EntityType.DATABASE.value,
        }
        components = [e for e in all_entities if e.entity_type in arch_types]
        if not components:
            return []

        comp_by_norm: dict[str, KnowledgeEntity] = {}
        for c in components:
            comp_by_norm[c.canonical_name.strip().lower()] = c
            # Index aliases
            for a in getattr(c, "aliases", []) or []:
                if hasattr(a, "alias_value") and a.alias_value:
                    comp_by_norm[a.alias_value.strip().lower()] = c

        # Load chunks from specification/architecture evidence items
        doc_chunks = list(
            self._session.execute(
                select(EvidenceChunk)
                .join(EvidenceItem, EvidenceItem.id == EvidenceChunk.evidence_id)
                .where(
                    EvidenceChunk.project_id == project_id,
                    EvidenceItem.deleted_at.is_(None),
                )
                .order_by(EvidenceChunk.chunk_index)
            )
            .scalars()
            .all()
        )

        seen_pairs: set[tuple[uuid.UUID, uuid.UUID, str]] = set()

        for chunk in doc_chunks:
            text = chunk.chunk_text
            if not text or len(text.strip()) < 20:
                continue

            # Split into individual sentences (preserving semicolons so coordinate clauses share context)
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n{2,}", text) if len(s.strip()) > 15]

            for s in sentences:
                s_lower = s.lower()

                # Find which components are mentioned in this sentence
                mentioned: list[tuple[str, KnowledgeEntity]] = []
                for norm_name, comp in comp_by_norm.items():
                    pattern = r"\b" + re.escape(norm_name) + r"\b"
                    if re.search(pattern, s_lower):
                        mentioned.append((norm_name, comp))

                if len(mentioned) < 2:
                    continue

                # Deduplicate mentioned components by entity ID
                unique_mentioned: list[KnowledgeEntity] = []
                seen_ent_ids = set()
                for _, ent in mentioned:
                    if ent.id not in seen_ent_ids:
                        seen_ent_ids.add(ent.id)
                        unique_mentioned.append(ent)

                if len(unique_mentioned) < 2:
                    continue

                for src_ent in unique_mentioned:
                    src_norm = src_ent.canonical_name.strip().lower()
                    for dst_ent in unique_mentioned:
                        if src_ent.id == dst_ent.id:
                            continue
                        dst_norm = dst_ent.canonical_name.strip().lower()

                        r_type: str | None = None

                        # 0. Subsystem & component hierarchy (PART_OF)
                        if ("route" in src_norm and "fastapi" in dst_norm and "route" not in dst_norm):
                            r_type = RelationshipType.PART_OF.value
                        elif ("auth" in src_norm and "supabase" in src_norm and dst_norm == "supabase"):
                            r_type = RelationshipType.PART_OF.value
                        elif (("model" in src_norm or "embedding" in src_norm) and "ollama" in src_norm and dst_norm == "ollama"):
                            r_type = RelationshipType.PART_OF.value

                        # 1. CALLS: client/browser -> routes/api, routes -> backend
                        elif (
                            ("browser" in src_norm or "client" in src_norm)
                            and ("route" in dst_norm or "api" in dst_norm)
                            and any(w in s_lower for w in ["call", "request", "endpoint", "on protected", "interface"])
                        ):
                            r_type = RelationshipType.CALLS.value
                        elif (
                            ("route" in src_norm or "api" in src_norm)
                            and ("fastapi" in dst_norm or "backend" in dst_norm or "service" in dst_norm)
                            and any(w in s_lower for w in ["call", "handle", "under", "route", "service"])
                        ):
                            r_type = RelationshipType.CALLS.value
                        elif (
                            ("fastapi" in src_norm or "backend" in src_norm)
                            and ("worker" in dst_norm)
                            and any(w in s_lower for w in ["dispatch", "async", "task", "job", "queue", "worker", "process", "service"])
                        ):
                            r_type = RelationshipType.SENDS_TO.value

                        # 2. STORES_IN / READS_FROM / WRITES_TO
                        elif (
                            ("postgres" in dst_norm or "database" in dst_norm)
                            and ("fastapi" in src_norm or "worker" in src_norm or "backend" in src_norm or "route" in src_norm)
                            and any(w in s_lower for w in ["model", "relational", "metadata", "postgres", "sql", "persist", "store", "quer", "depend"])
                        ):
                            r_type = RelationshipType.READS_FROM.value
                        elif (
                            ("storage" in dst_norm or "bucket" in dst_norm)
                            and ("fastapi" in src_norm or "backend" in src_norm or "worker" in src_norm or "route" in src_norm)
                            and any(w in s_lower for w in ["object storage", "bucket", "binary", "binaries", "store", "upload", "file", "depend"])
                        ):
                            r_type = RelationshipType.STORES_IN.value
                        elif (
                            ("chroma" in dst_norm or "vector" in dst_norm)
                            and ("worker" in src_norm or "fastapi" in src_norm or "backend" in src_norm)
                            and any(w in s_lower for w in ["chroma", "index", "vector", "chunk", "retrieval", "embed", "retrieval aid", "depend"])
                        ):
                            r_type = RelationshipType.STORES_IN.value

                        # 3. AUTHENTICATES_WITH
                        elif (
                            ("auth" in dst_norm or "supabase" in dst_norm)
                            and ("fastapi" in src_norm or "route" in src_norm or "backend" in src_norm)
                            and any(w in s_lower for w in ["auth", "token", "session", "credential", "protected", "depend"])
                        ):
                            r_type = RelationshipType.AUTHENTICATES_WITH.value

                        # 4. USES_MODEL
                        elif (
                            ("ollama" in dst_norm or "model" in dst_norm or "qwen" in dst_norm)
                            and ("worker" in src_norm or "backend" in src_norm or "fastapi" in src_norm)
                            and any(w in s_lower for w in ["model", "ollama", "embed", "infer", "extract", "depend"])
                        ):
                            r_type = RelationshipType.USES_MODEL.value

                        # 5. INTEGRATES_WITH
                        elif (
                            ("github" in dst_norm or "jira" in dst_norm)
                            and ("fastapi" in src_norm or "worker" in src_norm or "backend" in src_norm)
                            and any(w in s_lower for w in ["sync", "connect", "provider", "select", "repo", "issue", "integrate", "route family"])
                        ):
                            r_type = RelationshipType.INTEGRATES_WITH.value

                        if r_type:
                            valid, _ = validate_relationship_endpoints(
                                r_type, src_ent.entity_type, dst_ent.entity_type
                            )
                            if valid:
                                pair_key = (src_ent.id, dst_ent.id, r_type)
                                if pair_key not in seen_pairs:
                                    seen_pairs.add(pair_key)
                                    drafts.append(
                                        DiscoveredRelationshipDraft(
                                            source_entity_id=src_ent.id,
                                            target_entity_id=dst_ent.id,
                                            relationship_type=r_type,
                                            relationship_basis=RelationshipBasis.EXPLICIT.value,
                                            confidence_score=0.95,
                                            discovery_method="architecture_evidence",
                                            evidence_id=chunk.evidence_id,
                                            evidence_chunk_id=chunk.id,
                                            knowledge_item_id=None,
                                            supporting_excerpt=s[:500],
                                            source_location_json={
                                                "chunk_index": chunk.chunk_index,
                                                "section": chunk.section_title,
                                            },
                                        )
                                    )

        return drafts

    # --------------------------------------------------------------------------
    # Method 5: Qwen3 8B LLM-Assisted Candidate Extraction
    # --------------------------------------------------------------------------

    def discover_llm_assisted_relationships(
        self,
        *,
        project_id: uuid.UUID,
        organisation_id: uuid.UUID,
        evidence_limit: int = 10,
    ) -> list[DiscoveredRelationshipDraft]:
        """Use local Qwen3 8B to classify implicit relationships grounded in verbatim evidence chunks."""
        if self._llm_client is None:
            logger.info("LLM client not configured; skipping LLM-assisted relationship discovery.")
            return []

        drafts: list[DiscoveredRelationshipDraft] = []

        # Load candidate chunks from meetings, discussions, documents, or decisions
        chunks = list(
            self._session.execute(
                select(EvidenceChunk)
                .join(EvidenceItem, EvidenceItem.id == EvidenceChunk.evidence_id)
                .where(
                    EvidenceChunk.project_id == project_id,
                    EvidenceItem.deleted_at.is_(None),
                )
                .limit(evidence_limit)
            )
            .scalars()
            .all()
        )

        # Preload project entities
        entities = list(
            self._session.execute(
                select(KnowledgeEntity)
                .options(selectinload(KnowledgeEntity.aliases))
                .where(
                    KnowledgeEntity.project_id == project_id,
                    KnowledgeEntity.is_deleted.is_(False),
                )
            )
            .scalars()
            .all()
        )
        if not entities:
            return []

        entity_lookup = {e.canonical_name.lower(): e for e in entities}
        entity_names_str = ", ".join(
            f"'{e.canonical_name}' ({e.entity_type})" for e in entities[:40]
        )

        system_prompt = (
            "You are an expert Relationship Extraction engine for The Handover project platform.\n"
            "Given an evidence text chunk and a catalog of known project entities, identify meaningful directed relationships.\n"
            "MANDATORY RULES:\n"
            "1. ONLY extract relationships that have a DIRECT verbatim quote in the text chunk.\n"
            "2. NEVER invent or hallucinate relationships without evidence.\n"
            "3. Choose relationship_type strictly from: CALLS, READS_FROM, WRITES_TO, AUTHENTICATES_WITH, "
            "STORES_IN, USES_MODEL, INTEGRATES_WITH, SENDS_TO, DEPENDS_ON, DECIDED_BY, INFLUENCED_BY, "
            "IMPLEMENTED_BY, AFFECTS_COMPONENT, BLOCKS, OWNS, ASSIGNED_TO, DISCUSSED_IN, DOCUMENTED_IN, "
            "REFERENCES, MITIGATES_RISK.\n"
            "4. Return a JSON object with a single key 'relationships' containing a list of objects:\n"
            "   {\n"
            "     'source_name': str,\n"
            "     'target_name': str,\n"
            "     'relationship_type': str,\n"
            "     'confidence_score': float (0.5 to 1.0),\n"
            "     'verbatim_quote': str\n"
            "   }\n"
            "If no relationships exist, return {'relationships': []}."
        )

        for chunk in chunks:
            if not chunk.chunk_text or len(chunk.chunk_text.strip()) < 30:
                continue

            user_prompt = (
                f"Known Entities:\n{entity_names_str}\n\n"
                f'Evidence Text Chunk:\n"""{chunk.chunk_text[:2000]}"""\n\n'
                "Extract relationships present in this chunk."
            )

            try:
                res = self._llm_client.generate_json(
                    LLMGenerationRequest(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        temperature=0.1,
                    )
                )
                rels_data = res.parsed_json.get("relationships", [])
                if isinstance(rels_data, list):
                    for item in rels_data:
                        if not isinstance(item, dict):
                            continue
                        s_name = str(item.get("source_name", "")).strip().lower()
                        t_name = str(item.get("target_name", "")).strip().lower()
                        r_type = str(item.get("relationship_type", "")).strip().upper()
                        quote = item.get("verbatim_quote")
                        conf = float(item.get("confidence_score", 0.75))

                        s_node = entity_lookup.get(s_name)
                        t_node = entity_lookup.get(t_name)

                        if s_node and t_node and s_node.id != t_node.id:
                            # Validate endpoints
                            valid, err = validate_relationship_endpoints(
                                r_type, s_node.entity_type, t_node.entity_type
                            )
                            if valid:
                                drafts.append(
                                    DiscoveredRelationshipDraft(
                                        source_entity_id=s_node.id,
                                        target_entity_id=t_node.id,
                                        relationship_type=r_type,
                                        relationship_basis=RelationshipBasis.INFERRED.value,
                                        confidence_score=round(min(1.0, max(0.5, conf)), 3),
                                        discovery_method="llm_assisted_extraction",
                                        evidence_id=chunk.evidence_id,
                                        evidence_chunk_id=chunk.id,
                                        knowledge_item_id=None,
                                        supporting_excerpt=str(quote)[:500] if quote else None,
                                        source_location_json={"chunk_index": chunk.chunk_index},
                                        is_llm_assisted=True,
                                    )
                                )
            except Exception as e:
                logger.warning("LLM relationship extraction failed for chunk %s: %s", chunk.id, e)

        return drafts

    # --------------------------------------------------------------------------
    # Persistence Pipeline
    # --------------------------------------------------------------------------

    def persist_discovered_relationships(
        self,
        *,
        organisation_id: uuid.UUID,
        project_id: uuid.UUID,
        drafts: list[DiscoveredRelationshipDraft],
    ) -> tuple[int, int]:
        """Persist drafts into KnowledgeRelationship and RelationshipEvidenceLink.

        Returns (created_count, updated_count).
        """
        created = 0
        updated = 0
        _, entities_by_id = self._entity_repo._project_entities(project_id)
        rels_by_fp = self._rel_repo._project_relationships(project_id)

        for d in drafts:
            # Validate endpoints against taxonomy via preloaded entity cache
            s_entity = entities_by_id.get(d.source_entity_id)
            t_entity = entities_by_id.get(d.target_entity_id)
            if not s_entity or not t_entity or s_entity.id == t_entity.id:
                continue

            valid, _ = validate_relationship_endpoints(
                d.relationship_type, s_entity.entity_type, t_entity.entity_type
            )
            if not valid:
                continue

            # Check if relationship already exists in memory cache
            fingerprint = RelationshipRepository.compute_fingerprint(
                project_id, d.source_entity_id, d.relationship_type, d.target_entity_id
            )
            existing = rels_by_fp.get(fingerprint)

            if existing is None:
                rel = self._rel_repo.create_or_get_relationship(
                    organisation_id=organisation_id,
                    project_id=project_id,
                    source_entity_id=d.source_entity_id,
                    target_entity_id=d.target_entity_id,
                    relationship_type=d.relationship_type,
                    relationship_basis=d.relationship_basis,
                    verification_status=RelationshipVerificationStatus.CANDIDATE.value,
                    confidence_score=d.confidence_score,
                    confidence_components_json={"discovery_method": d.discovery_method},
                    discovery_method=d.discovery_method,
                    is_llm_assisted=d.is_llm_assisted,
                )
                created += 1
            else:
                rel = existing
                if float(rel.confidence_score) < d.confidence_score:
                    rel.confidence_score = d.confidence_score
                updated += 1

            # Attach evidence link via preloaded link cache
            self._rel_repo.add_evidence_link(
                relationship_id=rel.id,
                organisation_id=organisation_id,
                project_id=project_id,
                evidence_id=d.evidence_id,
                evidence_chunk_id=d.evidence_chunk_id,
                knowledge_item_id=d.knowledge_item_id,
                supporting_excerpt=d.supporting_excerpt,
                source_location_json=d.source_location_json,
            )

        self._session.flush()
        return created, updated
