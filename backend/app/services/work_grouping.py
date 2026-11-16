"""Evidence-Based Work Grouping Service & People-Centric Contributor Graph Projection.

Implements deterministic technical work-area grouping backed by persisted PostgreSQL
KnowledgeEntity (`work_cluster`), KnowledgeRelationship, and ContributionAttribution
records without requiring ML clustering libraries (HDBSCAN/K-means) or live LLM browsing.
"""

from __future__ import annotations

import uuid
from datetime import UTC
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.cache.local_cache import local_response_cache
from app.core.security import utc_now
from app.models.enums import (
    ContributorType,
    EntityType,
    RelationshipBasis,
    RelationshipRunStatus,
    RelationshipType,
)
from app.models.evidence import EvidenceItem
from app.models.relationship import (
    KnowledgeEntity,
    RelationshipReconstructionRun,
)
from app.models.team_roster import ContributionAttribution
from app.repositories.relationship import (
    EntityRepository,
    RelationshipRepository,
    _build_accessible_evidence_clause,
)
from app.services.contribution_attribution import (
    ContributionAttributionService,
    build_contributor_key,
)

_UNCLUSTERED_LABEL = "Other / Unclustered Contributions"
_WORK_GROUPING_VERSION = "deterministic-path-v1"


class WorkGroupingService:
    """Builds and queries evidence-based work clusters and people-centric contributor graphs."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._entity_repo = EntityRepository(session)
        self._rel_repo = RelationshipRepository(session)

    def _accessible_evidence_ids(
        self,
        *,
        project_id: uuid.UUID,
        viewer_user_id: uuid.UUID,
        has_project_manage: bool,
    ) -> set[uuid.UUID]:
        clause = _build_accessible_evidence_clause(
            self._session,
            project_id=project_id,
            viewer_user_id=viewer_user_id,
            has_project_manage=has_project_manage,
        )
        rows = (
            self._session.execute(
                select(EvidenceItem.id).where(
                    EvidenceItem.project_id == project_id,
                    EvidenceItem.deleted_at.is_(None),
                    clause,
                )
            )
            .scalars()
            .all()
        )
        return set(rows)

    def rebuild_work_clusters(
        self,
        *,
        organisation_id: uuid.UUID,
        project_id: uuid.UUID,
        triggered_by_user_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Group persisted project contributions into canonical WorkCluster entities."""
        run = RelationshipReconstructionRun(
            organisation_id=organisation_id,
            project_id=project_id,
            status=RelationshipRunStatus.RUNNING.value,
        )
        self._session.add(run)
        self._session.flush()

        attributions = list(
            self._session.execute(
                select(ContributionAttribution)
                .options(selectinload(ContributionAttribution.evidence_item))
                .where(ContributionAttribution.project_id == project_id)
            )
            .scalars()
            .all()
        )

        # Ensure any commit/PR/issue evidence items lacking an attribution row get attributed first
        attributed_ev_ids = {a.evidence_item_id for a in attributions}
        missing_ev_items = list(
            self._session.execute(
                select(EvidenceItem).where(
                    EvidenceItem.project_id == project_id,
                    EvidenceItem.deleted_at.is_(None),
                    EvidenceItem.category.in_(("commit", "pull_request", "issue")),
                )
            )
            .scalars()
            .all()
        )
        attr_service = ContributionAttributionService(self._session)
        for ev in missing_ev_items:
            if ev.id not in attributed_ev_ids:
                created = attr_service.attribute_evidence(ev)
                if created is not None:
                    created.evidence_item = ev
                    attributions.append(created)

        cluster_entities: dict[str, KnowledgeEntity] = {}
        links_created = 0

        for attr in attributions:
            ev = attr.evidence_item
            if ev is None or ev.deleted_at is not None:
                continue
            meta = attr.metadata_json or {}
            raw_areas = list(meta.get("work_areas") or [])
            if not raw_areas:
                raw_areas = [attr.contribution_category or "Other"]

            areas = [
                _UNCLUSTERED_LABEL if str(a).strip().lower() == "other" else str(a).strip()
                for a in raw_areas
            ]

            # Canonical contributor person entity
            ckey = str(meta.get("contributor_key") or build_contributor_key(meta, attr.contributor_identifier))
            person_name = (
                meta.get("github_author_login")
                or meta.get("git_author_name")
                or attr.contributor_identifier
            )
            is_synth = bool(getattr(ev, "is_synthetic", False))
            person_ent = self._entity_repo.create_or_get_entity(
                organisation_id=organisation_id,
                project_id=project_id,
                entity_type=EntityType.PERSON.value,
                canonical_name=str(person_name)[:255],
                external_source_id=ckey,
                source_provider="github",
                metadata_json={
                    "contributor_key": ckey,
                    "contributor_type": attr.contributor_type,
                    "review_status": attr.review_status,
                },
                is_synthetic=is_synth,
            )

            # Contribution artefact entity
            ev_cat = (ev.category or "").lower()
            art_type = (
                EntityType.PULL_REQUEST.value
                if ev_cat == "pull_request"
                else (EntityType.COMMIT.value if ev_cat == "commit" else EntityType.WORK_ITEM.value)
            )
            ev_meta = ev.metadata_json or {}
            compact_meta = {
                k: ev_meta.get(k)
                for k in ("repository", "sha", "pr_number", "author_login", "branch")
                if ev_meta.get(k) is not None
            }
            art_ent = self._entity_repo.create_or_get_entity(
                organisation_id=organisation_id,
                project_id=project_id,
                entity_type=art_type,
                canonical_name=ev.title[:255],
                primary_evidence_id=ev.id,
                external_source_id=ev.source_external_id,
                source_provider=ev.source_type,
                metadata_json=compact_meta,
                is_synthetic=is_synth,
            )

            for area_name in areas:
                if area_name not in cluster_entities:
                    c_ent = self._entity_repo.create_or_get_entity(
                        organisation_id=organisation_id,
                        project_id=project_id,
                        entity_type=EntityType.WORK_CLUSTER.value,
                        canonical_name=area_name[:255],
                        description=f"Evidence-based work area grouping for {area_name}",
                        primary_evidence_id=ev.id,
                        source_provider="work_grouping",
                        metadata_json={
                            "algorithm_version": _WORK_GROUPING_VERSION,
                            "classification_method": meta.get("classification_method") or "deterministic",
                            "run_id": str(run.id),
                        },
                        is_synthetic=is_synth,
                    )
                    cluster_entities[area_name] = c_ent
                cluster_ent = cluster_entities[area_name]

                is_synth = bool(getattr(ev, "is_synthetic", False))
                disc_method = str(meta.get("classification_method") or "deterministic_path")
                # Contribution -> BELONGS_TO_WORK_CLUSTER -> Cluster
                rel_art = self._rel_repo.create_or_get_relationship(
                    organisation_id=organisation_id,
                    project_id=project_id,
                    source_entity_id=art_ent.id,
                    target_entity_id=cluster_ent.id,
                    relationship_type=RelationshipType.BELONGS_TO_WORK_CLUSTER.value,
                    relationship_basis=RelationshipBasis.EXPLICIT.value,
                    discovery_method=disc_method,
                    confidence_score=0.92,
                    is_synthetic=is_synth,
                )
                self._rel_repo.add_evidence_link(
                    relationship_id=rel_art.id,
                    organisation_id=organisation_id,
                    project_id=project_id,
                    evidence_id=ev.id,
                    supporting_excerpt=f"{ev.title} grouped into {area_name}",
                    is_synthetic=is_synth,
                )
                links_created += 1

                # Person -> CONTRIBUTED_TO -> Cluster
                rel_pers = self._rel_repo.create_or_get_relationship(
                    organisation_id=organisation_id,
                    project_id=project_id,
                    source_entity_id=person_ent.id,
                    target_entity_id=cluster_ent.id,
                    relationship_type=RelationshipType.CONTRIBUTED_TO.value,
                    relationship_basis=RelationshipBasis.EXPLICIT.value,
                    discovery_method=disc_method,
                    confidence_score=0.92,
                    is_synthetic=is_synth,
                )
                self._rel_repo.add_evidence_link(
                    relationship_id=rel_pers.id,
                    organisation_id=organisation_id,
                    project_id=project_id,
                    evidence_id=ev.id,
                    supporting_excerpt=f"{person_name} contributed {ev.title} in {area_name}",
                    is_synthetic=is_synth,
                )
                links_created += 1

        run.status = RelationshipRunStatus.COMPLETED.value
        run.entities_discovered_count = len(cluster_entities)
        run.relationships_discovered_count = links_created
        run.explicit_links_count = links_created
        run.completed_at = utc_now()
        self._session.flush()

        return {
            "run_id": str(run.id),
            "algorithm_version": _WORK_GROUPING_VERSION,
            "clusters_count": len(cluster_entities),
            "relationships_created": links_created,
            "completed_at": run.completed_at.astimezone(UTC).isoformat(),
        }

    def list_work_clusters(
        self,
        *,
        project_id: uuid.UUID,
        viewer_user_id: uuid.UUID,
        has_project_manage: bool,
    ) -> list[dict[str, Any]]:
        """List accessible work clusters with contributor, contribution, and evidence breakdowns."""
        accessible_ev_ids = self._accessible_evidence_ids(
            project_id=project_id,
            viewer_user_id=viewer_user_id,
            has_project_manage=has_project_manage,
        )
        attributions = list(
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
        cluster_entities = {
            e.canonical_name: e
            for e in self._session.execute(
                select(KnowledgeEntity).where(
                    KnowledgeEntity.project_id == project_id,
                    KnowledgeEntity.entity_type == EntityType.WORK_CLUSTER.value,
                    KnowledgeEntity.is_deleted.is_(False),
                )
            )
            .scalars()
            .all()
        }

        groups: dict[str, dict[str, Any]] = {}
        for attr in attributions:
            if attr.evidence_item_id not in accessible_ev_ids:
                continue
            ev = attr.evidence_item
            if ev is None:
                continue
            meta = attr.metadata_json or {}
            ckey = str(meta.get("contributor_key") or build_contributor_key(meta, attr.contributor_identifier))
            raw_areas = list(meta.get("work_areas") or [attr.contribution_category or "Other"])
            areas = [
                _UNCLUSTERED_LABEL if str(a).strip().lower() == "other" else str(a).strip()
                for a in raw_areas
            ]
            for area in areas:
                ent = cluster_entities.get(area)
                grp = groups.get(area)
                if grp is None:
                    grp = {
                        "cluster_id": str(ent.id) if ent else f"cluster:{area.lower().replace(' ', '-')}",
                        "name": area,
                        "classification_method": meta.get("classification_method") or "deterministic",
                        "contribution_count": 0,
                        "contributors": {},
                        "contributions": [],
                        "changed_paths": set(),
                        "evidence_ids": set(),
                    }
                    groups[area] = grp

                grp["contribution_count"] += 1
                grp["evidence_ids"].add(str(attr.evidence_item_id))
                for p in meta.get("changed_files") or []:
                    grp["changed_paths"].add(str(p))

                if ckey not in grp["contributors"]:
                    grp["contributors"][ckey] = {
                        "contributor_key": ckey,
                        "display_name": meta.get("git_author_name") or meta.get("github_author_login") or attr.contributor_identifier,
                        "contributor_type": attr.contributor_type,
                        "count": 0,
                    }
                grp["contributors"][ckey]["count"] += 1
                grp["contributions"].append(
                    {
                        "evidence_id": str(ev.id),
                        "title": ev.title,
                        "category": ev.category,
                        "contributor_key": ckey,
                        "contributor_name": meta.get("git_author_name") or attr.contributor_identifier,
                        "contributor_type": attr.contributor_type,
                        "alignment": attr.responsibility_alignment,
                    }
                )

        out: list[dict[str, Any]] = []
        for grp in groups.values():
            out.append(
                {
                    "cluster_id": grp["cluster_id"],
                    "name": grp["name"],
                    "classification_method": grp["classification_method"],
                    "contribution_count": grp["contribution_count"],
                    "contributor_count": len(grp["contributors"]),
                    "contributors": sorted(grp["contributors"].values(), key=lambda x: -x["count"]),
                    "contributions": grp["contributions"][:50],
                    "changed_paths": sorted(grp["changed_paths"])[:40],
                    "evidence_ids": sorted(grp["evidence_ids"]),
                }
            )
        out.sort(key=lambda x: (x["name"] == _UNCLUSTERED_LABEL, -x["contribution_count"], x["name"]))
        return out

    def get_contributors_graph(
        self,
        *,
        project_id: uuid.UUID,
        viewer_user_id: uuid.UUID,
        has_project_manage: bool,
        contributor_type: str | None = None,
        work_cluster: str | None = None,
        repository: str | None = None,
        verification_state: str | None = None,
        search: str | None = None,
        include_external: bool = True,
        include_bots: bool = True,
        expand_contributor_key: str | None = None,
        expand_cluster_name: str | None = None,
        limit: int = 120,
    ) -> dict[str, Any]:
        """Build a bounded people-centric contributor graph projection strictly filtered by ACLs."""
        bind_id = id(self._session.get_bind())
        cache_key = (
            f"contrib_graph:{project_id}:{bind_id}:{viewer_user_id}:{int(has_project_manage)}:"
            f"{contributor_type or ''}:{work_cluster or ''}:{repository or ''}:"
            f"{verification_state or ''}:{search or ''}:{int(include_external)}:"
            f"{int(include_bots)}:{expand_contributor_key or ''}:{expand_cluster_name or ''}:{limit}"
        )
        cached = local_response_cache.get(cache_key)
        if isinstance(cached, dict):
            return cached

        accessible_ev_ids = self._accessible_evidence_ids(
            project_id=project_id,
            viewer_user_id=viewer_user_id,
            has_project_manage=has_project_manage,
        )
        attr_service = ContributionAttributionService(self._session)
        contributors = attr_service.list_contributor_identities(
            project_id=project_id,
            accessible_evidence_ids=accessible_ev_ids,
            has_project_manage=has_project_manage,
            contributor_type_filter=contributor_type,
        )
        clusters = self.list_work_clusters(
            project_id=project_id,
            viewer_user_id=viewer_user_id,
            has_project_manage=has_project_manage,
        )

        search_low = search.strip().lower() if search else None
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        node_ids: set[str] = set()

        # Filter contributors
        visible_contributors: list[dict[str, Any]] = []
        for c in contributors:
            ctype = c["contributor_type"]
            if not include_external and ctype == ContributorType.EXTERNAL_CONTRIBUTOR.value:
                continue
            if not include_bots and ctype == ContributorType.BOT.value:
                continue
            if repository and repository not in c["repositories"]:
                continue
            if work_cluster and work_cluster not in c["work_areas"]:
                continue
            if verification_state and c["review_status"] != verification_state:
                continue
            if search_low and (
                search_low not in c["display_name"].lower()
                and search_low not in (c["github_login"] or "").lower()
                and not any(search_low in w.lower() for w in c["work_areas"])
            ):
                continue
            visible_contributors.append(c)

        visible_contributors = visible_contributors[:limit]
        visible_ckeys = {c["contributor_key"] for c in visible_contributors}

        for c in visible_contributors:
            nid = f"person:{c['contributor_key']}"
            node_ids.add(nid)
            nodes.append(
                {
                    "id": nid,
                    "node_kind": "contributor",
                    "label": c["display_name"],
                    "contributor_key": c["contributor_key"],
                    "contributor_type": c["contributor_type"],
                    "review_status": c["review_status"],
                    "verification_status": c["review_status"],
                    "contribution_count": c["contribution_count"],
                    "metadata": {
                        "github_login": c["github_login"],
                        "github_numeric_id": c["github_numeric_id"],
                        "matched_member_name": c["matched_member_name"],
                        "declared_responsibility": c["declared_responsibility"],
                        "repositories": c["repositories"],
                        "work_areas": c["work_areas"],
                        "commits_count": c["commits_count"],
                        "prs_count": c["prs_count"],
                    },
                }
            )

        # Add Work Cluster nodes connected to visible contributors
        for cl in clusters:
            if work_cluster and cl["name"] != work_cluster:
                continue
            matching_contribs = [
                cc for cc in cl["contributors"] if cc["contributor_key"] in visible_ckeys
            ]
            if not matching_contribs:
                continue
            cid = f"cluster:{cl['cluster_id']}"
            node_ids.add(cid)
            nodes.append(
                {
                    "id": cid,
                    "node_kind": "work_cluster",
                    "label": cl["name"],
                    "contributor_type": "work_cluster",
                    "review_status": "derived",
                    "verification_status": "derived",
                    "contribution_count": cl["contribution_count"],
                    "metadata": {
                        "cluster_id": cl["cluster_id"],
                        "classification_method": cl["classification_method"],
                        "changed_paths": cl["changed_paths"][:15],
                        "evidence_ids": cl["evidence_ids"],
                    },
                }
            )
            for cc in matching_contribs:
                pid = f"person:{cc['contributor_key']}"
                if pid in node_ids:
                    edges.append(
                        {
                            "id": f"edge:{pid}->{cid}",
                            "source": pid,
                            "target": cid,
                            "relationship_type": RelationshipType.CONTRIBUTED_TO.value,
                            "label": f"{cc['count']} contrib(s)",
                            "evidence_basis": "explicit",
                        }
                    )

        # Optional lazy drill-down for selected contributor or work cluster
        if expand_contributor_key or expand_cluster_name:
            for cl in clusters:
                if expand_cluster_name and cl["name"] != expand_cluster_name:
                    continue
                cid = f"cluster:{cl['cluster_id']}"
                for item in cl["contributions"][:25]:
                    if expand_contributor_key and item["contributor_key"] != expand_contributor_key:
                        continue
                    pid = f"person:{item['contributor_key']}"
                    aid = f"art:{item['evidence_id']}"
                    if aid not in node_ids:
                        node_ids.add(aid)
                        nodes.append(
                            {
                                "id": aid,
                                "node_kind": item["category"],
                                "label": item["title"][:80],
                                "contributor_type": item["category"],
                                "review_status": item["alignment"] or "explicit",
                                "verification_status": "explicit",
                                "contribution_count": 1,
                                "metadata": {
                                    "evidence_id": item["evidence_id"],
                                    "alignment": item["alignment"],
                                },
                            }
                        )
                    if pid in node_ids:
                        edges.append(
                            {
                                "id": f"edge:{aid}->{pid}",
                                "source": aid,
                                "target": pid,
                                "relationship_type": RelationshipType.AUTHORED_BY.value,
                                "label": "Authored By",
                                "evidence_basis": "explicit",
                            }
                        )
                    if cid in node_ids:
                        edges.append(
                            {
                                "id": f"edge:{aid}->{cid}",
                                "source": aid,
                                "target": cid,
                                "relationship_type": RelationshipType.BELONGS_TO_WORK_CLUSTER.value,
                                "label": "In Cluster",
                                "evidence_basis": "explicit",
                            }
                        )

        payload = {
            "project_id": str(project_id),
            "nodes": nodes,
            "edges": edges,
            "summary": {
                "contributor_count": len(visible_contributors),
                "cluster_count": sum(1 for n in nodes if n["node_kind"] == "work_cluster"),
                "confirmed_members": sum(1 for c in visible_contributors if c["contributor_type"] == ContributorType.CONFIRMED_MEMBER.value),
                "external_contributors": sum(1 for c in visible_contributors if c["contributor_type"] == ContributorType.EXTERNAL_CONTRIBUTOR.value),
                "unidentified_contributors": sum(1 for c in visible_contributors if c["contributor_type"] == ContributorType.UNIDENTIFIED.value),
                "bots": sum(1 for c in visible_contributors if c["contributor_type"] == ContributorType.BOT.value),
                "pending_reviews": sum(1 for c in visible_contributors if c["review_status"] == "pending"),
            },
        }
        local_response_cache.set(cache_key, payload, ttl_seconds=60)
        return payload
