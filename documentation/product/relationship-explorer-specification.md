# Relationship Explorer — Product Specification

## Purpose
Relationship Explorer reconstructs who contributed to the project, how GitHub/Jira identities map to team members vs. external contributors vs. bots, how work groups into technical areas, and how people, commits, pull requests, tasks, components, and declared responsibilities connect.

## Primary Views (`frontend/src/components/relationships/RelationshipWorkspace.tsx`)
1. **People & Contributions (`people`)**: Default `@xyflow/react` contributor and work-cluster graph with distinct visual styling for `confirmed_member`, `external_contributor`, `unidentified` (`Unresolved Identity`), `bot`, and `work_cluster` nodes, lazy drill-down into commits/PRs/issues, table fallback, and an Entity Graph toggle with depth-bounded neighborhood expansion (`center_node_id`, `depth`).
2. **Work Clusters (`clusters`)**: Interactive evidence-based work area groups (`Frontend`, `Backend`, `Authentication`, `Database`, `API`, `AI/ML`, `RAG`, `OCR`, `Infrastructure`, `Testing`, `Documentation`, `Security`, `Integration`, and `Other / Unclustered Contributions`) with contributor counts and deep links to Knowledge Intelligence and Evidence Center.
3. **Identity Review (`identity_review`)**: Displays unresolved and candidate GitHub contributor identities triggered by post-sync `"Contributor identities require review."` notifications. Authorised project managers can confirm a match to an existing `ProjectMembership`, mark as `external_contributor`, mark as `bot`, reject, or revert.
4. **Responsibilities (`responsibilities`)**: Compares declared responsibilities (`ProjectMembership.responsibility_description`, `TeamRosterMember`) separately against observed contribution categories with alignment states (`ALIGNED`, `PARTIALLY_ALIGNED`, `OUTSIDE_DECLARED_RESPONSIBILITY`, `UNCERTAIN`, `NOT_APPLICABLE`).
5. **Traceability (`traceability`)**: 5-stage decision-to-implementation chains.
6. **Dependencies (`dependencies`)**: Directed dependency traversal, cycle detection, and root-blocker analysis filtered by source ACLs.
7. **Timeline (`timeline`)**: Chronological project event stream.
