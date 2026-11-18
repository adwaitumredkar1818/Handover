"""Controlled relationship and entity taxonomy for Relationship Explorer.

Enforces:
- 13 canonical Entity Types
- 40+ controlled directed Relationship Types
- Validation of allowed source and target entity type pairs
- Inverse relationship label resolution for bidirectional visual display
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from app.models.enums import EntityType, RelationshipType


@dataclass(frozen=True, slots=True)
class RelationshipRule:
    """Allowed semantic constraints for a directed relationship type."""

    relationship_type: str
    display_label: str
    inverse_label: str
    allowed_source_types: tuple[str, ...]
    allowed_target_types: tuple[str, ...]
    description: str


_TAXONOMY_RULES: Final[dict[str, RelationshipRule]] = {
    # --------------------------------------------------------------------------
    # Decision & Architecture
    # --------------------------------------------------------------------------
    RelationshipType.DECIDED_BY.value: RelationshipRule(
        relationship_type=RelationshipType.DECIDED_BY.value,
        display_label="Decided By",
        inverse_label="Decided",
        allowed_source_types=(EntityType.DECISION.value,),
        allowed_target_types=(EntityType.PERSON.value, EntityType.TEAM.value),
        description="Connects an architectural or project decision to the person or team who decided it.",
    ),
    RelationshipType.INFLUENCED_BY.value: RelationshipRule(
        relationship_type=RelationshipType.INFLUENCED_BY.value,
        display_label="Influenced By",
        inverse_label="Influenced",
        allowed_source_types=(EntityType.DECISION.value, EntityType.WORK_ITEM.value),
        allowed_target_types=(
            EntityType.DISCUSSION_THREAD.value,
            EntityType.MEETING_NOTE.value,
            EntityType.DOCUMENT.value,
            EntityType.PERSON.value,
        ),
        description="Links a decision or work item to the meeting, discussion, or person that shaped it.",
    ),
    RelationshipType.IMPLEMENTED_BY.value: RelationshipRule(
        relationship_type=RelationshipType.IMPLEMENTED_BY.value,
        display_label="Implemented By",
        inverse_label="Implements",
        allowed_source_types=(EntityType.DECISION.value, EntityType.WORK_ITEM.value),
        allowed_target_types=(
            EntityType.PULL_REQUEST.value,
            EntityType.COMMIT.value,
            EntityType.WORK_ITEM.value,
            EntityType.PERSON.value,
        ),
        description="Connects a decision or task to the pull request, commit, or developer that implemented it.",
    ),
    RelationshipType.SUPERSEDES.value: RelationshipRule(
        relationship_type=RelationshipType.SUPERSEDES.value,
        display_label="Supersedes",
        inverse_label="Superseded By",
        allowed_source_types=(
            EntityType.DECISION.value,
            EntityType.DOCUMENT.value,
            EntityType.PROCEDURE.value,
        ),
        allowed_target_types=(
            EntityType.DECISION.value,
            EntityType.DOCUMENT.value,
            EntityType.PROCEDURE.value,
        ),
        description="Indicates a new decision, specification, or SOP replaces a previous one.",
    ),
    RelationshipType.AFFECTS_COMPONENT.value: RelationshipRule(
        relationship_type=RelationshipType.AFFECTS_COMPONENT.value,
        display_label="Affects Component",
        inverse_label="Affected By",
        allowed_source_types=(
            EntityType.DECISION.value,
            EntityType.WORK_ITEM.value,
            EntityType.PULL_REQUEST.value,
            EntityType.COMMIT.value,
            EntityType.RISK.value,
            EntityType.BLOCKER.value,
        ),
        allowed_target_types=(EntityType.COMPONENT.value,),
        description="Links an event, decision, task, or code artifact to the software module or service it alters.",
    ),
    RelationshipType.ARCHITECTURAL_DEPENDENCY.value: RelationshipRule(
        relationship_type=RelationshipType.ARCHITECTURAL_DEPENDENCY.value,
        display_label="Architecturally Depends On",
        inverse_label="Architectural Prerequisite For",
        allowed_source_types=(EntityType.COMPONENT.value, EntityType.DECISION.value),
        allowed_target_types=(EntityType.COMPONENT.value, EntityType.DECISION.value),
        description="Structural dependency between components or architecture decisions.",
    ),
    # --------------------------------------------------------------------------
    # Work & Code
    # --------------------------------------------------------------------------
    RelationshipType.IMPLEMENTS.value: RelationshipRule(
        relationship_type=RelationshipType.IMPLEMENTS.value,
        display_label="Implements",
        inverse_label="Implemented By",
        allowed_source_types=(EntityType.PULL_REQUEST.value, EntityType.COMMIT.value),
        allowed_target_types=(EntityType.WORK_ITEM.value, EntityType.DECISION.value),
        description="Code delivery artefact realizing a work item or decision.",
    ),
    RelationshipType.FIXES.value: RelationshipRule(
        relationship_type=RelationshipType.FIXES.value,
        display_label="Fixes",
        inverse_label="Fixed By",
        allowed_source_types=(
            EntityType.PULL_REQUEST.value,
            EntityType.COMMIT.value,
            EntityType.WORK_ITEM.value,
        ),
        allowed_target_types=(
            EntityType.WORK_ITEM.value,
            EntityType.BLOCKER.value,
            EntityType.RISK.value,
        ),
        description="Resolves a defect, blocker, or risk.",
    ),
    RelationshipType.PART_OF.value: RelationshipRule(
        relationship_type=RelationshipType.PART_OF.value,
        display_label="Part Of",
        inverse_label="Contains",
        allowed_source_types=(
            EntityType.WORK_ITEM.value,
            EntityType.COMMIT.value,
            EntityType.COMPONENT.value,
            EntityType.PERSON.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
            EntityType.SERVICE.value,
            EntityType.API.value,
            EntityType.FEATURE.value,
        ),
        allowed_target_types=(
            EntityType.WORK_ITEM.value,
            EntityType.PULL_REQUEST.value,
            EntityType.COMPONENT.value,
            EntityType.TEAM.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
            EntityType.SERVICE.value,
            EntityType.DATABASE.value,
            EntityType.PROJECT.value,
            EntityType.FEATURE.value,
        ),
        description="Sub-task, constituent commit, child component, subsystem, or team membership.",
    ),
    RelationshipType.BLOCKS.value: RelationshipRule(
        relationship_type=RelationshipType.BLOCKS.value,
        display_label="Blocks",
        inverse_label="Blocked By",
        allowed_source_types=(
            EntityType.WORK_ITEM.value,
            EntityType.BLOCKER.value,
            EntityType.DECISION.value,
        ),
        allowed_target_types=(
            EntityType.WORK_ITEM.value,
            EntityType.PULL_REQUEST.value,
            EntityType.DECISION.value,
        ),
        description="Identifies a prerequisite that halts progress on target item.",
    ),
    RelationshipType.BLOCKED_BY.value: RelationshipRule(
        relationship_type=RelationshipType.BLOCKED_BY.value,
        display_label="Blocked By",
        inverse_label="Blocks",
        allowed_source_types=(
            EntityType.WORK_ITEM.value,
            EntityType.PULL_REQUEST.value,
            EntityType.DECISION.value,
        ),
        allowed_target_types=(
            EntityType.WORK_ITEM.value,
            EntityType.BLOCKER.value,
            EntityType.DECISION.value,
        ),
        description="Direct blocker citation.",
    ),
    RelationshipType.DEPENDS_ON.value: RelationshipRule(
        relationship_type=RelationshipType.DEPENDS_ON.value,
        display_label="Depends On",
        inverse_label="Required By",
        allowed_source_types=(
            EntityType.WORK_ITEM.value,
            EntityType.PULL_REQUEST.value,
            EntityType.COMPONENT.value,
            EntityType.DECISION.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
            EntityType.SERVICE.value,
            EntityType.API.value,
            EntityType.FEATURE.value,
            EntityType.PROJECT.value,
        ),
        allowed_target_types=(
            EntityType.WORK_ITEM.value,
            EntityType.PULL_REQUEST.value,
            EntityType.COMPONENT.value,
            EntityType.DECISION.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
            EntityType.SERVICE.value,
            EntityType.DATABASE.value,
            EntityType.API.value,
            EntityType.TECHNOLOGY.value,
            EntityType.FEATURE.value,
        ),
        description="Execution, component, or design dependency.",
    ),
    RelationshipType.MERGED_IN.value: RelationshipRule(
        relationship_type=RelationshipType.MERGED_IN.value,
        display_label="Merged In",
        inverse_label="Included PR",
        allowed_source_types=(EntityType.PULL_REQUEST.value,),
        allowed_target_types=(EntityType.COMPONENT.value, EntityType.PULL_REQUEST.value),
        description="Merge of PR into target branch or component repository.",
    ),
    RelationshipType.BRANCHED_FROM.value: RelationshipRule(
        relationship_type=RelationshipType.BRANCHED_FROM.value,
        display_label="Branched From",
        inverse_label="Parent Branch Of",
        allowed_source_types=(EntityType.PULL_REQUEST.value, EntityType.COMMIT.value),
        allowed_target_types=(EntityType.COMPONENT.value, EntityType.PULL_REQUEST.value),
        description="Base branch or commit lineage.",
    ),
    # --------------------------------------------------------------------------
    # Ownership & Responsibility
    # --------------------------------------------------------------------------
    RelationshipType.OWNS.value: RelationshipRule(
        relationship_type=RelationshipType.OWNS.value,
        display_label="Owns",
        inverse_label="Owned By",
        allowed_source_types=(EntityType.PERSON.value, EntityType.TEAM.value),
        allowed_target_types=(
            EntityType.COMPONENT.value,
            EntityType.DOCUMENT.value,
            EntityType.PROCEDURE.value,
            EntityType.WORK_ITEM.value,
        ),
        description="Clear primary ownership of a system, document, or initiative.",
    ),
    RelationshipType.MAINTAINS.value: RelationshipRule(
        relationship_type=RelationshipType.MAINTAINS.value,
        display_label="Maintains",
        inverse_label="Maintained By",
        allowed_source_types=(EntityType.PERSON.value, EntityType.TEAM.value),
        allowed_target_types=(EntityType.COMPONENT.value, EntityType.PROCEDURE.value),
        description="Ongoing engineering maintenance and support responsibility.",
    ),
    RelationshipType.ASSIGNED_TO.value: RelationshipRule(
        relationship_type=RelationshipType.ASSIGNED_TO.value,
        display_label="Assigned To",
        inverse_label="Assigned Task",
        allowed_source_types=(
            EntityType.WORK_ITEM.value,
            EntityType.BLOCKER.value,
            EntityType.RISK.value,
        ),
        allowed_target_types=(EntityType.PERSON.value, EntityType.TEAM.value),
        description="Active assignee handling the item.",
    ),
    RelationshipType.AUTHORED_BY.value: RelationshipRule(
        relationship_type=RelationshipType.AUTHORED_BY.value,
        display_label="Authored By",
        inverse_label="Authored",
        allowed_source_types=(
            EntityType.DOCUMENT.value,
            EntityType.DECISION.value,
            EntityType.PULL_REQUEST.value,
            EntityType.COMMIT.value,
            EntityType.PROCEDURE.value,
            EntityType.WORK_ITEM.value,
        ),
        allowed_target_types=(EntityType.PERSON.value,),
        description="Author or creator of an artefact.",
    ),
    RelationshipType.REVIEWED_BY.value: RelationshipRule(
        relationship_type=RelationshipType.REVIEWED_BY.value,
        display_label="Reviewed By",
        inverse_label="Reviewed",
        allowed_source_types=(
            EntityType.PULL_REQUEST.value,
            EntityType.DOCUMENT.value,
            EntityType.DECISION.value,
        ),
        allowed_target_types=(EntityType.PERSON.value,),
        description="Sign-off or code review participant.",
    ),
    RelationshipType.REPORTED_BY.value: RelationshipRule(
        relationship_type=RelationshipType.REPORTED_BY.value,
        display_label="Reported By",
        inverse_label="Reported",
        allowed_source_types=(
            EntityType.WORK_ITEM.value,
            EntityType.BLOCKER.value,
            EntityType.RISK.value,
        ),
        allowed_target_types=(EntityType.PERSON.value,),
        description="Person who filed the issue or raised the alert.",
    ),
    # --------------------------------------------------------------------------
    # Discussion & Documentation
    # --------------------------------------------------------------------------
    RelationshipType.DISCUSSED_IN.value: RelationshipRule(
        relationship_type=RelationshipType.DISCUSSED_IN.value,
        display_label="Discussed In",
        inverse_label="Discusses",
        allowed_source_types=(
            EntityType.DECISION.value,
            EntityType.WORK_ITEM.value,
            EntityType.RISK.value,
            EntityType.BLOCKER.value,
            EntityType.COMPONENT.value,
        ),
        allowed_target_types=(
            EntityType.DISCUSSION_THREAD.value,
            EntityType.MEETING_NOTE.value,
            EntityType.DOCUMENT.value,
        ),
        description="Connects subject matter to the communication thread or meeting where it occurred.",
    ),
    RelationshipType.DOCUMENTED_IN.value: RelationshipRule(
        relationship_type=RelationshipType.DOCUMENTED_IN.value,
        display_label="Documented In",
        inverse_label="Documents",
        allowed_source_types=(
            EntityType.DECISION.value,
            EntityType.COMPONENT.value,
            EntityType.PROCEDURE.value,
            EntityType.WORK_ITEM.value,
        ),
        allowed_target_types=(EntityType.DOCUMENT.value, EntityType.PROCEDURE.value),
        description="Cites official documentation or runbook.",
    ),
    RelationshipType.REFERENCES.value: RelationshipRule(
        relationship_type=RelationshipType.REFERENCES.value,
        display_label="References",
        inverse_label="Referenced By",
        allowed_source_types=(
            EntityType.DOCUMENT.value,
            EntityType.PULL_REQUEST.value,
            EntityType.COMMIT.value,
            EntityType.DISCUSSION_THREAD.value,
            EntityType.WORK_ITEM.value,
        ),
        allowed_target_types=(
            EntityType.DOCUMENT.value,
            EntityType.DECISION.value,
            EntityType.WORK_ITEM.value,
            EntityType.COMPONENT.value,
        ),
        description="Generic citation or mention.",
    ),
    RelationshipType.RESOLVED_BY.value: RelationshipRule(
        relationship_type=RelationshipType.RESOLVED_BY.value,
        display_label="Resolved By",
        inverse_label="Resolves",
        allowed_source_types=(
            EntityType.BLOCKER.value,
            EntityType.RISK.value,
            EntityType.WORK_ITEM.value,
        ),
        allowed_target_types=(
            EntityType.PULL_REQUEST.value,
            EntityType.COMMIT.value,
            EntityType.DECISION.value,
            EntityType.WORK_ITEM.value,
        ),
        description="Item that cured a blocker or risk.",
    ),
    # --------------------------------------------------------------------------
    # Risk & Failure
    # --------------------------------------------------------------------------
    RelationshipType.INTRODUCES_RISK.value: RelationshipRule(
        relationship_type=RelationshipType.INTRODUCES_RISK.value,
        display_label="Introduces Risk",
        inverse_label="Introduced By",
        allowed_source_types=(
            EntityType.DECISION.value,
            EntityType.PULL_REQUEST.value,
            EntityType.WORK_ITEM.value,
        ),
        allowed_target_types=(EntityType.RISK.value,),
        description="A technical choice or scope change introducing operational risk.",
    ),
    RelationshipType.MITIGATES_RISK.value: RelationshipRule(
        relationship_type=RelationshipType.MITIGATES_RISK.value,
        display_label="Mitigates Risk",
        inverse_label="Mitigated By",
        allowed_source_types=(
            EntityType.DECISION.value,
            EntityType.WORK_ITEM.value,
            EntityType.PROCEDURE.value,
            EntityType.PULL_REQUEST.value,
        ),
        allowed_target_types=(EntityType.RISK.value,),
        description="Action or procedure reducing known project risk.",
    ),
    RelationshipType.CAUSED_BY.value: RelationshipRule(
        relationship_type=RelationshipType.CAUSED_BY.value,
        display_label="Caused By",
        inverse_label="Caused",
        allowed_source_types=(EntityType.BLOCKER.value, EntityType.RISK.value),
        allowed_target_types=(
            EntityType.DECISION.value,
            EntityType.COMMIT.value,
            EntityType.PULL_REQUEST.value,
            EntityType.WORK_ITEM.value,
        ),
        description="Root cause connection for a failure or delay.",
    ),
    # --------------------------------------------------------------------------
    # Technology Stack, Architecture, Features & Work Grouping Extensions
    # --------------------------------------------------------------------------
    RelationshipType.USES_TECHNOLOGY.value: RelationshipRule(
        relationship_type=RelationshipType.USES_TECHNOLOGY.value,
        display_label="Uses Technology",
        inverse_label="Used By",
        allowed_source_types=(
            EntityType.PROJECT.value,
            EntityType.COMPONENT.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
            EntityType.SERVICE.value,
            EntityType.FEATURE.value,
            EntityType.REPOSITORY.value,
        ),
        allowed_target_types=(
            EntityType.TECHNOLOGY.value,
            EntityType.FRAMEWORK.value,
            EntityType.LIBRARY.value,
            EntityType.DATABASE.value,
        ),
        description="Links a project or component to a technology it uses.",
    ),
    RelationshipType.CONFIGURED_IN.value: RelationshipRule(
        relationship_type=RelationshipType.CONFIGURED_IN.value,
        display_label="Configured In",
        inverse_label="Configures",
        allowed_source_types=(
            EntityType.TECHNOLOGY.value,
            EntityType.SERVICE.value,
            EntityType.DATABASE.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
        ),
        allowed_target_types=(EntityType.DOCUMENT.value, EntityType.REPOSITORY.value),
        description="Links a technology or service to the manifest or config file declaring it.",
    ),
    RelationshipType.CALLS.value: RelationshipRule(
        relationship_type=RelationshipType.CALLS.value,
        display_label="Calls",
        inverse_label="Called By",
        allowed_source_types=(
            EntityType.COMPONENT.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
            EntityType.SERVICE.value,
            EntityType.API.value,
        ),
        allowed_target_types=(
            EntityType.COMPONENT.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
            EntityType.SERVICE.value,
            EntityType.API.value,
        ),
        description="Runtime or API invocation between system components.",
    ),
    RelationshipType.READS_FROM.value: RelationshipRule(
        relationship_type=RelationshipType.READS_FROM.value,
        display_label="Reads From",
        inverse_label="Read By",
        allowed_source_types=(
            EntityType.COMPONENT.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
            EntityType.SERVICE.value,
            EntityType.API.value,
        ),
        allowed_target_types=(
            EntityType.DATABASE.value,
            EntityType.COMPONENT.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
            EntityType.SERVICE.value,
            EntityType.TECHNOLOGY.value,
        ),
        description="Component or service reads state or records from a data store.",
    ),
    RelationshipType.WRITES_TO.value: RelationshipRule(
        relationship_type=RelationshipType.WRITES_TO.value,
        display_label="Writes To",
        inverse_label="Written By",
        allowed_source_types=(
            EntityType.COMPONENT.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
            EntityType.SERVICE.value,
            EntityType.API.value,
        ),
        allowed_target_types=(
            EntityType.DATABASE.value,
            EntityType.COMPONENT.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
            EntityType.SERVICE.value,
            EntityType.TECHNOLOGY.value,
        ),
        description="Component or service persists state or records to a data store.",
    ),
    RelationshipType.AUTHENTICATES_WITH.value: RelationshipRule(
        relationship_type=RelationshipType.AUTHENTICATES_WITH.value,
        display_label="Authenticates With",
        inverse_label="Authenticates",
        allowed_source_types=(
            EntityType.COMPONENT.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
            EntityType.SERVICE.value,
            EntityType.API.value,
            EntityType.PROJECT.value,
        ),
        allowed_target_types=(
            EntityType.COMPONENT.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
            EntityType.SERVICE.value,
            EntityType.API.value,
            EntityType.TECHNOLOGY.value,
        ),
        description="Security boundary or authentication provider verification.",
    ),
    RelationshipType.USES_MODEL.value: RelationshipRule(
        relationship_type=RelationshipType.USES_MODEL.value,
        display_label="Uses Model",
        inverse_label="Model Used By",
        allowed_source_types=(
            EntityType.COMPONENT.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
            EntityType.SERVICE.value,
            EntityType.API.value,
            EntityType.PROJECT.value,
        ),
        allowed_target_types=(
            EntityType.COMPONENT.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
            EntityType.SERVICE.value,
            EntityType.TECHNOLOGY.value,
        ),
        description="AI or embedding model invocation by a service or worker.",
    ),
    RelationshipType.SENDS_TO.value: RelationshipRule(
        relationship_type=RelationshipType.SENDS_TO.value,
        display_label="Sends To",
        inverse_label="Receives From",
        allowed_source_types=(
            EntityType.COMPONENT.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
            EntityType.SERVICE.value,
            EntityType.API.value,
        ),
        allowed_target_types=(
            EntityType.COMPONENT.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
            EntityType.SERVICE.value,
            EntityType.API.value,
        ),
        description="Message dispatch or asynchronous event transmission between services.",
    ),
    RelationshipType.HAS_FEATURE.value: RelationshipRule(
        relationship_type=RelationshipType.HAS_FEATURE.value,
        display_label="Has Feature",
        inverse_label="Feature Of",
        allowed_source_types=(EntityType.PROJECT.value,),
        allowed_target_types=(EntityType.FEATURE.value,),
        description="Connects a project to its canonical user-facing product features.",
    ),
    RelationshipType.STORES_IN.value: RelationshipRule(
        relationship_type=RelationshipType.STORES_IN.value,
        display_label="Stores In",
        inverse_label="Stores Data For",
        allowed_source_types=(
            EntityType.COMPONENT.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
            EntityType.SERVICE.value,
        ),
        allowed_target_types=(
            EntityType.DATABASE.value,
            EntityType.TECHNOLOGY.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
        ),
        description="Persistence flow from a service/component into a data store.",
    ),
    RelationshipType.INTEGRATES_WITH.value: RelationshipRule(
        relationship_type=RelationshipType.INTEGRATES_WITH.value,
        display_label="Integrates With",
        inverse_label="Integrated With",
        allowed_source_types=(
            EntityType.PROJECT.value,
            EntityType.COMPONENT.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
            EntityType.SERVICE.value,
        ),
        allowed_target_types=(
            EntityType.SERVICE.value,
            EntityType.TECHNOLOGY.value,
            EntityType.API.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
            EntityType.REPOSITORY.value,
        ),
        description="Integration boundary between internal services and external systems.",
    ),
    RelationshipType.HAS_REQUIREMENT.value: RelationshipRule(
        relationship_type=RelationshipType.HAS_REQUIREMENT.value,
        display_label="Has Requirement",
        inverse_label="Requirement For",
        allowed_source_types=(EntityType.FEATURE.value, EntityType.PROJECT.value),
        allowed_target_types=(EntityType.REQUIREMENT.value, EntityType.DOCUMENT.value),
        description="Links a feature to its formal requirement specification.",
    ),
    RelationshipType.TRACKED_BY.value: RelationshipRule(
        relationship_type=RelationshipType.TRACKED_BY.value,
        display_label="Tracked By",
        inverse_label="Tracks",
        allowed_source_types=(EntityType.FEATURE.value, EntityType.DECISION.value),
        allowed_target_types=(EntityType.WORK_ITEM.value, EntityType.ISSUE.value),
        description="Links a feature or decision to its issue tracker item.",
    ),
    RelationshipType.USES_COMPONENT.value: RelationshipRule(
        relationship_type=RelationshipType.USES_COMPONENT.value,
        display_label="Uses Component",
        inverse_label="Used By Feature",
        allowed_source_types=(EntityType.FEATURE.value, EntityType.OPERATIONAL_PROCEDURE.value),
        allowed_target_types=(
            EntityType.COMPONENT.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
            EntityType.SERVICE.value,
        ),
        description="Connects a product feature to the technical component implementing it.",
    ),
    RelationshipType.HAS_WORKFLOW_STEP.value: RelationshipRule(
        relationship_type=RelationshipType.HAS_WORKFLOW_STEP.value,
        display_label="Has Workflow Step",
        inverse_label="Workflow Step Of",
        allowed_source_types=(EntityType.FEATURE.value, EntityType.OPERATIONAL_PROCEDURE.value),
        allowed_target_types=(
            EntityType.OPERATIONAL_PROCEDURE.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.WORK_ITEM.value,
        ),
        description="Links a feature or workflow to its constituent operational steps.",
    ),
    RelationshipType.TESTED_BY.value: RelationshipRule(
        relationship_type=RelationshipType.TESTED_BY.value,
        display_label="Tested By",
        inverse_label="Tests",
        allowed_source_types=(
            EntityType.FEATURE.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
        ),
        allowed_target_types=(
            EntityType.PULL_REQUEST.value,
            EntityType.COMMIT.value,
            EntityType.DOCUMENT.value,
            EntityType.WORK_ITEM.value,
        ),
        description="Links a feature or component to supporting test evidence.",
    ),
    RelationshipType.BELONGS_TO_WORK_CLUSTER.value: RelationshipRule(
        relationship_type=RelationshipType.BELONGS_TO_WORK_CLUSTER.value,
        display_label="Belongs To Work Cluster",
        inverse_label="Contains Contribution",
        allowed_source_types=(
            EntityType.COMMIT.value,
            EntityType.PULL_REQUEST.value,
            EntityType.WORK_ITEM.value,
            EntityType.ISSUE.value,
            EntityType.TECHNICAL_COMPONENT.value,
        ),
        allowed_target_types=(EntityType.WORK_CLUSTER.value,),
        description="Groups a contribution or component into an evidence-backed technical work area.",
    ),
    RelationshipType.CONTRIBUTED_TO.value: RelationshipRule(
        relationship_type=RelationshipType.CONTRIBUTED_TO.value,
        display_label="Contributed To",
        inverse_label="Contributor",
        allowed_source_types=(EntityType.PERSON.value, EntityType.TEAM.value),
        allowed_target_types=(
            EntityType.WORK_CLUSTER.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
            EntityType.COMPONENT.value,
            EntityType.FEATURE.value,
            EntityType.REPOSITORY.value,
        ),
        description="Observed contributor activity toward a work cluster, component, or feature.",
    ),
    RelationshipType.MODIFIED.value: RelationshipRule(
        relationship_type=RelationshipType.MODIFIED.value,
        display_label="Modified",
        inverse_label="Modified By",
        allowed_source_types=(EntityType.COMMIT.value, EntityType.PULL_REQUEST.value),
        allowed_target_types=(
            EntityType.COMPONENT.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
            EntityType.FEATURE.value,
        ),
        description="Connects a commit or pull request to the component it modified.",
    ),
    RelationshipType.CONTAINS_COMMIT.value: RelationshipRule(
        relationship_type=RelationshipType.CONTAINS_COMMIT.value,
        display_label="Contains Commit",
        inverse_label="Part Of PR",
        allowed_source_types=(EntityType.PULL_REQUEST.value,),
        allowed_target_types=(EntityType.COMMIT.value,),
        description="Links a pull request to its verified constituent commits.",
    ),
    RelationshipType.RESPONSIBLE_FOR.value: RelationshipRule(
        relationship_type=RelationshipType.RESPONSIBLE_FOR.value,
        display_label="Responsible For",
        inverse_label="Responsibility Owned By",
        allowed_source_types=(EntityType.PERSON.value, EntityType.TEAM.value),
        allowed_target_types=(
            EntityType.WORK_CLUSTER.value,
            EntityType.COMPONENT.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
            EntityType.FEATURE.value,
            EntityType.DOCUMENT.value,
        ),
        description="Declared project responsibility separate from observed contributions.",
    ),
}


def get_relationship_rule(relationship_type: str) -> RelationshipRule | None:
    """Retrieve rule definition for a relationship type."""
    return _TAXONOMY_RULES.get(relationship_type)


def validate_relationship_endpoints(
    relationship_type: str,
    source_type: str,
    target_type: str,
) -> tuple[bool, str | None]:
    """Validate that source_type -> target_type is permitted for relationship_type."""
    rule = get_relationship_rule(relationship_type)
    if rule is None:
        return False, f"Unrecognised relationship type: '{relationship_type}'"

    if source_type not in rule.allowed_source_types:
        return (
            False,
            f"Source type '{source_type}' is not allowed for '{relationship_type}'. "
            f"Allowed: {list(rule.allowed_source_types)}",
        )

    if target_type not in rule.allowed_target_types:
        return (
            False,
            f"Target type '{target_type}' is not allowed for '{relationship_type}'. "
            f"Allowed: {list(rule.allowed_target_types)}",
        )

    return True, None


def get_display_label(relationship_type: str, *, inverse: bool = False) -> str:
    """Return human-readable display label (or inverse label for bidirectional edges)."""
    rule = get_relationship_rule(relationship_type)
    if rule is None:
        return relationship_type.replace("_", " ").title()
    return rule.inverse_label if inverse else rule.display_label
