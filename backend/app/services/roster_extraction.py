"""Team roster extraction and human-in-the-loop member reconciliation service."""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import utc_now
from app.models.enums import NotificationType, ReconciliationStatus
from app.models.evidence import EvidenceContent, EvidenceItem
from app.models.notification import NotificationItem
from app.models.project import Project, ProjectMembership
from app.models.team_roster import TeamRosterMember
from app.models.user import User

logger = logging.getLogger("app.services.roster_extraction")

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_GITHUB_RE = re.compile(r"(?:github\.com/|@)([a-zA-Z0-9-]+)")


def _extract_roster_rows_from_text(text: str) -> list[dict[str, Any]]:
    """Parse text/markdown tables or bulleted member records from roster document."""
    records: list[dict[str, Any]] = []
    lines = text.splitlines()

    # Strategy A: Markdown table parsing
    table_lines: list[str] = [line.strip() for line in lines if "|" in line]
    if len(table_lines) >= 3:
        header_cells = [c.strip().lower() for c in table_lines[0].split("|") if c.strip()]
        # Check if table headers look like a roster
        if any(h in ("name", "member", "full name", "team member", "student name") for h in header_cells):
            # Map column indices
            id_idx = next((i for i, h in enumerate(header_cells) if "id" in h or "matric" in h or "emp" in h), -1)
            name_idx = next((i for i, h in enumerate(header_cells) if ("name" in h or "member" in h or "student" in h) and i != id_idx), 0)
            role_idx = next((i for i, h in enumerate(header_cells) if "role" in h or "title" in h or "position" in h), -1)
            resp_idx = next((i for i, h in enumerate(header_cells) if "resp" in h or "task" in h or "area" in h or "component" in h), -1)
            email_idx = next((i for i, h in enumerate(header_cells) if "email" in h or "mail" in h), -1)
            gh_idx = next((i for i, h in enumerate(header_cells) if "git" in h or "github" in h), -1)

            for line in table_lines[2:]:  # Skip header and separator
                cells = [c.strip() for c in line.split("|") if c.strip() or line.startswith("|") and line.endswith("|")]
                if not cells or len(cells) < 1:
                    continue
                # Strip out potential empty outer cells
                if line.startswith("|") and line.endswith("|"):
                    inner_cells = [c.strip() for c in line.split("|")[1:-1]]
                else:
                    inner_cells = cells

                if len(inner_cells) <= name_idx:
                    continue
                name_val = inner_cells[name_idx]
                if not name_val or name_val.startswith("---") or name_val.lower() in ("name", "total"):
                    continue

                id_val = inner_cells[id_idx] if 0 <= id_idx < len(inner_cells) else None
                role_val = inner_cells[role_idx] if 0 <= role_idx < len(inner_cells) else None
                resp_val = inner_cells[resp_idx] if 0 <= resp_idx < len(inner_cells) else None
                email_val = inner_cells[email_idx] if 0 <= email_idx < len(inner_cells) else None
                gh_val = inner_cells[gh_idx] if 0 <= gh_idx < len(inner_cells) else None

                # Clean responsibilities
                resp_list: list[str] = []
                if resp_val:
                    for item in re.split(r"[,;•\n]+", resp_val):
                        c = item.strip().strip("- ")
                        if c:
                            resp_list.append(c)

                # Extract email and github handle if embedded
                if not email_val:
                    emails = _EMAIL_RE.findall(line)
                    if emails:
                        email_val = emails[0]
                if not gh_val:
                    gh_match = _GITHUB_RE.findall(line)
                    if gh_match:
                        gh_val = gh_match[0]

                records.append({
                    "full_name": name_val,
                    "member_id": id_val,
                    "role_name": role_val or "Contributor",
                    "primary_responsibilities": resp_list,
                    "component_ownership": [r for r in resp_list if any(kw in r.lower() for kw in ("module", "service", "component", "frontend", "backend", "database", "api", "ui"))],
                    "email": email_val,
                    "github_username": gh_val.replace("@", "").strip() if gh_val else None,
                })

    # Strategy B: Section-based / bulleted records if table didn't yield records
    if not records:
        current_record: dict[str, Any] | None = None
        for line in lines:
            stripped = line.strip()
            # Detect new member heading (e.g. "### 1. Alice Smith" or "**Name:** Bob")
            name_match = re.match(r"^(?:#{1,4}\s+|\d+\.\s+|\*\s+)?(?:Name|Member|Student):\s*([^\n,]+)", stripped, re.IGNORECASE)
            if name_match:
                if current_record and current_record.get("full_name"):
                    records.append(current_record)
                current_record = {
                    "full_name": name_match.group(1).strip(),
                    "member_id": None,
                    "role_name": "Contributor",
                    "primary_responsibilities": [],
                    "component_ownership": [],
                    "email": None,
                    "github_username": None,
                }
                continue

            if current_record is not None:
                if "id:" in stripped.lower():
                    val = stripped.split(":", 1)[1].strip()
                    current_record["member_id"] = val
                elif "role:" in stripped.lower() or "title:" in stripped.lower():
                    val = stripped.split(":", 1)[1].strip()
                    current_record["role_name"] = val
                elif "email:" in stripped.lower():
                    emails = _EMAIL_RE.findall(stripped)
                    if emails:
                        current_record["email"] = emails[0]
                elif "github:" in stripped.lower() or "git:" in stripped.lower():
                    gh = _GITHUB_RE.findall(stripped)
                    if gh:
                        current_record["github_username"] = gh[0]
                elif "responsibilit" in stripped.lower() or "work area:" in stripped.lower() or "tasks:" in stripped.lower():
                    val = stripped.split(":", 1)[1].strip()
                    if val:
                        current_record["primary_responsibilities"].extend([s.strip() for s in val.split(",") if s.strip()])
                elif stripped.startswith("- ") or stripped.startswith("* "):
                    c = stripped[2:].strip()
                    if c and len(c) > 2:
                        current_record["primary_responsibilities"].append(c)

        if current_record and current_record.get("full_name"):
            records.append(current_record)

    return records


class TeamRosterExtractionService:
    """Extracts team roster members and reconciles them with project memberships."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def extract_and_reconcile(
        self,
        *,
        evidence_id: uuid.UUID,
        actor_user_id: uuid.UUID | None = None,
    ) -> list[TeamRosterMember]:
        evidence = self._session.get(EvidenceItem, evidence_id)
        if evidence is None:
            logger.warning("EvidenceItem %s not found for roster extraction", evidence_id)
            return []

        # Get extracted document content
        content = self._session.execute(
            select(EvidenceContent).where(EvidenceContent.evidence_id == evidence_id)
        ).scalars().first()
        if content is None or not content.extracted_text:
            logger.info("EvidenceItem %s has no extracted text for roster extraction", evidence_id)
            return []

        extracted_raw = _extract_roster_rows_from_text(content.extracted_text)
        if not extracted_raw:
            logger.info("No roster members could be parsed from evidence %s", evidence_id)
            return []

        # Fetch existing project memberships and users for reconciliation
        memberships_stmt = (
            select(ProjectMembership, User)
            .join(User, ProjectMembership.user_id == User.id)
            .where(
                ProjectMembership.project_id == evidence.project_id,
                ProjectMembership.status == "active",
            )
        )
        existing_members = self._session.execute(memberships_stmt).all()

        saved_members: list[TeamRosterMember] = []
        matched_count = 0
        now = utc_now()

        for raw in extracted_raw:
            full_name = str(raw.get("full_name") or "").strip()
            if not full_name:
                continue

            email = str(raw.get("email") or "").strip().lower() or None
            gh_user = str(raw.get("github_username") or "").strip().lower() or None

            matched_membership_id: uuid.UUID | None = None
            reconciliation_status = ReconciliationStatus.NEW_CANDIDATE.value
            confidence: float = 0.0
            notes: str | None = None

            # Compare against existing project members
            for membership, user in existing_members:
                user_email = (user.email or "").strip().lower()
                user_name = (user.full_name or "").strip().lower()

                # Exact email match
                if email and user_email and email == user_email:
                    matched_membership_id = membership.id
                    reconciliation_status = ReconciliationStatus.MATCHED.value
                    confidence = 1.0
                    notes = f"Matched via exact email ({email})"
                    matched_count += 1
                    break

                # Exact name match
                if full_name.lower() == user_name:
                    matched_membership_id = membership.id
                    reconciliation_status = ReconciliationStatus.MATCHED.value
                    confidence = 0.90
                    notes = f"Matched via exact name ({full_name})"
                    matched_count += 1
                    break

                # Partial / token name match
                name_tokens = set(full_name.lower().split())
                user_tokens = set(user_name.split())
                if name_tokens and user_tokens and name_tokens.intersection(user_tokens):
                    matched_membership_id = membership.id
                    reconciliation_status = ReconciliationStatus.POSSIBLE_MATCH.value
                    confidence = 0.65
                    notes = f"Possible name match with project member '{user.full_name}'"

            roster_member = TeamRosterMember(
                project_id=evidence.project_id,
                evidence_item_id=evidence.id,
                member_id_in_roster=raw.get("member_id"),
                full_name=full_name,
                email=email,
                role_name=raw.get("role_name"),
                primary_responsibilities=raw.get("primary_responsibilities") or [],
                component_ownership=raw.get("component_ownership") or [],
                github_username=gh_user,
                git_commit_email=email,
                jira_account_id=None,
                slack_user_id=None,
                reconciliation_status=reconciliation_status,
                matched_project_membership_id=matched_membership_id,
                reconciliation_confidence=confidence,
                reconciliation_notes=notes,
                metadata_json={"extracted_from_doc": evidence.title},
            )
            self._session.add(roster_member)
            saved_members.append(roster_member)

        # Record persistent notification
        notif = NotificationItem(
            organisation_id=evidence.organisation_id,
            project_id=evidence.project_id,
            user_id=actor_user_id,
            notification_type=NotificationType.ROSTER_EXTRACTED.value,
            title="Team Roster Extracted",
            body=(
                f"Extracted {len(saved_members)} members from '{evidence.title}'. "
                f"{matched_count} matched to project members, "
                f"{len(saved_members) - matched_count} ready for human reconciliation."
            ),
            severity="info",
            metadata_json={
                "evidence_id": str(evidence.id),
                "total_extracted": len(saved_members),
                "matched_count": matched_count,
            },
        )
        self._session.add(notif)
        self._session.commit()

        logger.info(
            "Extracted and reconciled %d roster members for project=%s evidence=%s",
            len(saved_members),
            evidence.project_id,
            evidence.id,
        )
        return saved_members
