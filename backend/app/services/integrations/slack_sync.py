"""Slack workspace and channel history sync orchestrator producing normalized evidence."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.core.security import utc_now
from app.models.enums import (
    ConnectorExtractionMethod,
    EvidenceCategory,
    EvidenceSourceType,
    PageExtractionOutcome,
    SourcePermissionVerificationStatus,
)
from app.models.integration import ProjectSourceMapping, SourceAccessPolicy
from app.repositories.integration import IntegrationRepository
from app.services.document_extraction import ExtractedPageData
from app.services.integrations.access_policy import SourceAccessPolicyService
from app.services.integrations.errors import IntegrationAuthError, IntegrationProviderError
from app.services.integrations.evidence_ingestor import (
    NormalizedSourceEvidence,
    SourceEvidenceIngestor,
)
from app.services.integrations.github_sync import SyncExecutionReport
from app.services.integrations.slack_client import SlackClient

logger = logging.getLogger("app.services.integrations.slack_sync")


def _page(page_num: int, text: str, section_name: str) -> ExtractedPageData:
    cleaned = text.strip()
    return ExtractedPageData(
        page_number=page_num,
        text_content=cleaned,
        extraction_outcome=(
            PageExtractionOutcome.DIGITAL_TEXT.value
            if cleaned
            else PageExtractionOutcome.EMPTY.value
        ),
        ocr_applied=False,
        ocr_truncated=False,
        structured_metadata={"section": section_name},
    )


class SlackSyncOrchestrator:
    """Orchestrates bounded, incremental synchronisation of Slack channels into Evidence."""

    def __init__(
        self,
        *,
        settings: Settings,
        client: SlackClient,
        repo: IntegrationRepository,
        policy_service: SourceAccessPolicyService,
        ingestor: SourceEvidenceIngestor,
    ) -> None:
        self._settings = settings
        self._client = client
        self._repo = repo
        self._policy = policy_service
        self._ingestor = ingestor

    def sync_mapping(
        self,
        *,
        mapping: ProjectSourceMapping,
        policy: SourceAccessPolicy,
        access_token: str,
        actor_user_id: uuid.UUID | None,
        sync_mode: str,
        on_batch_commit: Any = None,
    ) -> SyncExecutionReport:
        now = utc_now()
        report = SyncExecutionReport()
        channel_id = mapping.external_resource_id
        team_id = mapping.external_site_id or "default"
        channel_name = mapping.external_resource_name or channel_id
        config = dict(mapping.sync_config_json or {})
        cursor_before = dict(mapping.sync_cursor_json or {})

        logger.info(
            "Starting Slack sync for project=%s channel=%s (%s) mode=%s",
            mapping.project_id,
            channel_name,
            channel_id,
            sync_mode,
        )

        # 1. Verify access & ACL
        classification = self._policy.classify_resource(
            provider="slack",
            resource_visibility=mapping.provider_visibility or "private",
            policy=policy,
        )
        policy.sync_permission_status = SourcePermissionVerificationStatus.VERIFIED.value
        policy.last_acl_verified_at = now

        # 2. Ingest channel metadata container
        chan_text = (
            f"# Slack Channel: #{channel_name}\n\n"
            f"- Channel ID: {channel_id}\n"
            f"- Team ID: {team_id}\n"
            f"- Synced At: {now.isoformat()}\n"
        )
        seen_external_ids: set[str] = set()

        self._record_upsert(
            report=report,
            mapping=mapping,
            triggered_by_user_id=actor_user_id,
            now=now,
            seen_external_ids=seen_external_ids,
            record=NormalizedSourceEvidence(
                source_type=EvidenceSourceType.SLACK.value,
                source_provider="slack",
                category=EvidenceCategory.DISCUSSION_THREAD.value,
                source_external_id=f"slack:{team_id}:channel:{channel_id}:metadata",
                source_url=mapping.external_resource_url,
                source_author_identity=None,
                title=f"Slack Channel #{channel_name} Overview",
                source_created_at=None,
                source_updated_at=now,
                extraction_method=ConnectorExtractionMethod.SLACK_API.value,
                acl_scope=classification.acl_scope,
                source_access_policy_id=policy.id,
                extracted_text=chan_text,
                pages=(_page(1, chan_text, "slack_channel_metadata"),),
                metadata_json={
                    "mapping_id": str(mapping.id),
                    "slack_item_type": "channel_metadata",
                    "channel_id": channel_id,
                    "channel_name": channel_name,
                    "team_id": team_id,
                },
            ),
        )

        if on_batch_commit:
            try:
                on_batch_commit(
                    "channel_metadata",
                    report.items_discovered,
                    report.items_created,
                    report.items_updated,
                )
            except Exception:
                pass

        # 3. Retrieve users map for human names/emails
        users_map: dict[str, dict[str, Any]] = {}
        try:
            users_map = self._client.get_users_map(access_token)
        except Exception as exc:
            logger.warning("Failed to fetch Slack user map: %s", exc)

        # 4. Determine oldest timestamp for incremental sync
        oldest_ts: str | None = None
        if sync_mode == "incremental" and cursor_before.get("last_message_ts"):
            oldest_ts = str(cursor_before["last_message_ts"])

        # 5. Fetch messages from channel history
        max_items = getattr(self._settings.integrations, "sync_max_items_per_run", 500)
        remaining_budget = max(1, max_items - report.items_discovered)
        raw_messages: list[dict[str, Any]] = []
        try:
            raw_messages = self._client.fetch_channel_history(
                access_token=access_token,
                channel_id=channel_id,
                oldest=oldest_ts,
                limit=min(remaining_budget, 100),
            )
        except IntegrationProviderError as exc:
            report.warnings.append(f"Channel history fetch error: {exc.message}")
            report.partial = True
            return report

        latest_seen_ts: str | None = oldest_ts

        for msg in raw_messages:
            report.items_discovered += 1
            ts = str(msg.get("ts") or "")
            if not ts:
                continue

            # Update high-water mark
            if latest_seen_ts is None or ts > latest_seen_ts:
                latest_seen_ts = ts

            user_id = str(msg.get("user") or "")
            user_info = users_map.get(user_id, {})
            author_name = user_info.get("real_name") or user_info.get("username") or user_id or "Unknown"
            author_email = user_info.get("email")
            author_identity = f"{author_name} <{author_email}>" if author_email else author_name

            msg_text = str(msg.get("text") or "").strip()
            if not msg_text:
                continue

            # Parse timestamp to datetime
            dt = datetime.fromtimestamp(float(ts), tz=UTC) if "." in ts or ts.isdigit() else now
            permalink = self._client.get_permalink(access_token, channel_id, ts)

            # Check for thread replies if requested
            replies_text = ""
            reply_count = int(msg.get("reply_count") or 0)
            if reply_count > 0 and config.get("include_threads", True):
                try:
                    thread_replies = self._client.fetch_thread_replies(
                        access_token=access_token,
                        channel_id=channel_id,
                        thread_ts=ts,
                    )
                    # Exclude the parent message itself from replies display
                    child_replies = [r for r in thread_replies if r.get("ts") != ts]
                    if child_replies:
                        replies_text = "\n\n### Thread Replies:\n"
                        for r in child_replies:
                            ruid = str(r.get("user") or "")
                            r_info = users_map.get(ruid, {})
                            r_author = r_info.get("real_name") or r_info.get("username") or ruid or "User"
                            r_text = str(r.get("text") or "").strip()
                            r_ts = str(r.get("ts") or "")
                            r_dt = datetime.fromtimestamp(float(r_ts), tz=UTC).strftime("%Y-%m-%d %H:%M:%S") if "." in r_ts else ""
                            replies_text += f"- **{r_author}** ({r_dt}): {r_text}\n"
                except Exception as exc:
                    logger.debug("Failed to fetch replies for thread %s: %s", ts, exc)

            snippet = msg_text[:80].replace("\n", " ")
            title = f"#{channel_name}: {snippet}..." if len(msg_text) > 80 else f"#{channel_name}: {snippet}"
            full_content = (
                f"# Discussion in #{channel_name}\n\n"
                f"**Author:** {author_identity}\n"
                f"**Date:** {dt.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                f"**Channel:** #{channel_name} (`{channel_id}`)\n"
                f"**Permalink:** {permalink or 'N/A'}\n\n"
                f"## Message\n\n{msg_text}\n"
                f"{replies_text}"
            )

            record = NormalizedSourceEvidence(
                source_type=EvidenceSourceType.SLACK.value,
                source_provider="slack",
                category=EvidenceCategory.DISCUSSION_THREAD.value,
                source_external_id=f"slack:{team_id}:channel:{channel_id}:msg:{ts}",
                source_url=permalink or mapping.external_resource_url,
                source_author_identity=author_identity,
                title=title,
                source_created_at=dt,
                source_updated_at=dt,
                extraction_method=ConnectorExtractionMethod.SLACK_API.value,
                acl_scope=classification.acl_scope,
                source_access_policy_id=policy.id,
                extracted_text=full_content,
                pages=(_page(1, full_content, "slack_message"),),
                metadata_json={
                    "mapping_id": str(mapping.id),
                    "slack_item_type": "message",
                    "channel_id": channel_id,
                    "channel_name": channel_name,
                    "team_id": team_id,
                    "message_ts": ts,
                    "user_id": user_id,
                    "author_name": author_name,
                    "author_email": author_email,
                    "reply_count": reply_count,
                    "permalink": permalink,
                },
            )

            self._record_upsert(
                report=report,
                mapping=mapping,
                triggered_by_user_id=actor_user_id,
                now=now,
                seen_external_ids=seen_external_ids,
                record=record,
            )
            if on_batch_commit and (report.items_discovered % 5 == 0):
                try:
                    on_batch_commit(
                        "slack_messages",
                        report.items_discovered,
                        report.items_created,
                        report.items_updated,
                    )
                except Exception:
                    pass

        if on_batch_commit:
            try:
                on_batch_commit(
                    "slack_messages",
                    report.items_discovered,
                    report.items_created,
                    report.items_updated,
                )
            except Exception:
                pass

        new_cursor = dict(cursor_before)
        if latest_seen_ts:
            new_cursor["last_message_ts"] = latest_seen_ts
        new_cursor["last_synced_at"] = now.isoformat()
        report.new_cursor = new_cursor

        logger.info(
            "Completed Slack sync for #%s: discovered=%d created=%d updated=%d unchanged=%d",
            channel_name,
            report.items_discovered,
            report.items_created,
            report.items_updated,
            report.items_unchanged,
        )
        return report

    def _record_upsert(
        self,
        *,
        report: SyncExecutionReport,
        mapping: ProjectSourceMapping,
        triggered_by_user_id: uuid.UUID | None,
        now: datetime,
        seen_external_ids: set[str],
        record: NormalizedSourceEvidence,
    ) -> None:
        if record.source_external_id in seen_external_ids:
            return
        seen_external_ids.add(record.source_external_id)

        try:
            outcome = self._ingestor.upsert_record(
                project_id=mapping.project_id,
                organisation_id=mapping.organisation_id,
                source_connection_id=mapping.source_connection_id,
                triggered_by_user_id=triggered_by_user_id,
                record=record,
                now=now,
            )
            action = outcome.action
            if action == "created":
                report.items_created += 1
                if outcome.evidence_item and outcome.evidence_item.id:
                    report.created_evidence_ids.append(outcome.evidence_item.id)
            elif action == "updated":
                report.items_updated += 1
                if outcome.evidence_item and outcome.evidence_item.id:
                    report.updated_evidence_ids.append(outcome.evidence_item.id)
            elif action == "unchanged":
                report.items_unchanged += 1
            elif action == "inaccessible":
                report.items_inaccessible += 1
        except Exception as exc:
            logger.exception("Failed to ingest Slack record %s: %s", record.source_external_id, exc)
            report.items_failed += 1
            report.warnings.append(f"Slack record {record.source_external_id} error: {exc}")
