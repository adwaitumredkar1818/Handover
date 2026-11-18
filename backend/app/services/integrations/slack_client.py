"""Read-only Slack Web API client for workspace discovery and channel history sync."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

from app.core.config import Settings
from app.services.integrations.errors import IntegrationAuthError, IntegrationProviderError
from app.services.integrations.http_utils import (
    create_integration_http_client,
    is_rate_limit_response,
    parse_provider_datetime,
    raise_for_provider_error,
)

logger = logging.getLogger("app.services.integrations.slack")


@dataclass(frozen=True)
class SlackChannelCandidate:
    """Accessible Slack channel discovered through the caller's token."""

    id: str
    name: str
    is_private: bool
    is_archived: bool
    num_members: int = 0
    topic: str = ""
    purpose: str = ""


@dataclass(frozen=True)
class SlackMessageRecord:
    """A single Slack message or reply."""

    ts: str
    channel_id: str
    user_id: str
    username: str | None
    user_real_name: str | None
    user_email: str | None
    text: str
    thread_ts: str | None
    reply_count: int
    permalink: str | None
    created_at: datetime
    raw_json: dict[str, Any] = field(default_factory=dict)


class SlackClient:
    """Strict read-only Slack Web API client using bot user token or user token."""

    BASE_URL = "https://slack.com/api"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._timeout = getattr(settings.integrations, "http_timeout_seconds", 30.0)

    def _headers(self, access_token: str) -> dict[str, str]:
        token = access_token.strip()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "TheHandover-SlackSync/1.0",
        }

    def _check_slack_response(self, data: dict[str, Any], method: str) -> None:
        if not data.get("ok"):
            err = data.get("error", "unknown_error")
            logger.warning("Slack API call %s returned ok=false error=%s", method, err)
            if err in ("invalid_auth", "not_authed", "account_inactive", "token_revoked"):
                raise IntegrationAuthError(
                    f"Slack authentication failed: {err}",
                    provider="slack",
                    code="SLACK_AUTH_FAILED",
                )
            if err == "ratelimited":
                raise IntegrationProviderError(
                    "Slack API rate limit exceeded.",
                    provider="slack",
                    code="SLACK_RATE_LIMITED",
                    retry_after_seconds=5,
                )
            raise IntegrationProviderError(
                f"Slack API error during {method}: {err}",
                provider="slack",
                code=f"SLACK_{err.upper()}",
            )

    def auth_test(self, access_token: str) -> dict[str, Any]:
        """Verify token validity and retrieve bot/user identity and team name."""
        with create_integration_http_client(timeout_seconds=self._timeout) as client:
            resp = client.post(
                f"{self.BASE_URL}/auth.test",
                headers=self._headers(access_token),
            )
            if is_rate_limit_response(resp):
                raise IntegrationProviderError(
                    "Slack rate limit reached on auth.test.",
                    provider="slack",
                    code="SLACK_RATE_LIMITED",
                )
            raise_for_provider_error(resp, provider="slack", endpoint_label="auth.test")
            data = resp.json()
            self._check_slack_response(data, "auth.test")
            return data

    def list_channels(
        self,
        access_token: str,
        *,
        types: str = "public_channel,private_channel",
        limit: int = 100,
    ) -> list[SlackChannelCandidate]:
        """Fetch all accessible public and private channels in the workspace."""
        channels: list[SlackChannelCandidate] = []
        cursor: str | None = None

        with create_integration_http_client(timeout_seconds=self._timeout) as client:
            while True:
                params: dict[str, Any] = {
                    "types": types,
                    "limit": min(limit, 200),
                    "exclude_archived": "false",
                }
                if cursor:
                    params["cursor"] = cursor

                resp = client.get(
                    f"{self.BASE_URL}/conversations.list",
                    headers=self._headers(access_token),
                    params=params,
                )
                if is_rate_limit_response(resp):
                    break
                raise_for_provider_error(resp, provider="slack", endpoint_label="conversations.list")
                data = resp.json()
                if (
                    not data.get("ok")
                    and data.get("error") == "missing_scope"
                    and "private_channel" in str(params.get("types", ""))
                ):
                    logger.info("Slack token lacks groups:read; falling back to public channels only.")
                    params["types"] = "public_channel"
                    types = "public_channel"
                    resp = client.get(
                        f"{self.BASE_URL}/conversations.list",
                        headers=self._headers(access_token),
                        params=params,
                    )
                    raise_for_provider_error(resp, provider="slack", endpoint_label="conversations.list")
                    data = resp.json()
                self._check_slack_response(data, "conversations.list")

                for ch in data.get("channels", []):
                    channels.append(
                        SlackChannelCandidate(
                            id=str(ch.get("id")),
                            name=str(ch.get("name") or ch.get("id")),
                            is_private=bool(ch.get("is_private")),
                            is_archived=bool(ch.get("is_archived")),
                            num_members=int(ch.get("num_members") or 0),
                            topic=str(ch.get("topic", {}).get("value") or ""),
                            purpose=str(ch.get("purpose", {}).get("value") or ""),
                        )
                    )

                next_cursor = (
                    data.get("response_metadata", {}).get("next_cursor")
                    if isinstance(data.get("response_metadata"), dict)
                    else None
                )
                if not next_cursor or len(channels) >= 500:
                    break
                cursor = str(next_cursor).strip()

        return channels

    def get_users_map(self, access_token: str) -> dict[str, dict[str, Any]]:
        """Fetch workspace users mapping user_id -> {name, real_name, email}."""
        users_map: dict[str, dict[str, Any]] = {}
        cursor: str | None = None

        with create_integration_http_client(timeout_seconds=self._timeout) as client:
            while True:
                params: dict[str, Any] = {"limit": 200}
                if cursor:
                    params["cursor"] = cursor

                resp = client.get(
                    f"{self.BASE_URL}/users.list",
                    headers=self._headers(access_token),
                    params=params,
                )
                if is_rate_limit_response(resp):
                    break
                raise_for_provider_error(resp, provider="slack", endpoint_label="users.list")
                data = resp.json()
                self._check_slack_response(data, "users.list")

                for u in data.get("members", []):
                    uid = str(u.get("id"))
                    prof = u.get("profile") or {}
                    users_map[uid] = {
                        "username": str(u.get("name") or prof.get("display_name") or ""),
                        "real_name": str(prof.get("real_name") or u.get("real_name") or ""),
                        "email": str(prof.get("email") or ""),
                    }

                next_cursor = (
                    data.get("response_metadata", {}).get("next_cursor")
                    if isinstance(data.get("response_metadata"), dict)
                    else None
                )
                if not next_cursor or len(users_map) >= 1000:
                    break
                cursor = str(next_cursor).strip()

        return users_map

    def fetch_channel_history(
        self,
        access_token: str,
        channel_id: str,
        *,
        oldest: str | None = None,
        latest: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch top-level messages from a channel."""
        messages: list[dict[str, Any]] = []
        cursor: str | None = None

        with create_integration_http_client(timeout_seconds=self._timeout) as client:
            while True:
                params: dict[str, Any] = {
                    "channel": channel_id,
                    "limit": min(limit, 100),
                }
                if oldest:
                    params["oldest"] = oldest
                if latest:
                    params["latest"] = latest
                if cursor:
                    params["cursor"] = cursor

                resp = client.get(
                    f"{self.BASE_URL}/conversations.history",
                    headers=self._headers(access_token),
                    params=params,
                )
                if is_rate_limit_response(resp):
                    logger.warning("Slack rate limit encountered during conversations.history for %s", channel_id)
                    break
                raise_for_provider_error(resp, provider="slack", endpoint_label="conversations.history")
                data = resp.json()
                self._check_slack_response(data, "conversations.history")

                batch = data.get("messages", [])
                messages.extend(batch)

                next_cursor = (
                    data.get("response_metadata", {}).get("next_cursor")
                    if isinstance(data.get("response_metadata"), dict)
                    else None
                )
                if not next_cursor or len(messages) >= 300:
                    break
                cursor = str(next_cursor).strip()

        return messages

    def fetch_thread_replies(
        self,
        access_token: str,
        channel_id: str,
        thread_ts: str,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch replies in a specific thread."""
        replies: list[dict[str, Any]] = []
        cursor: str | None = None

        with create_integration_http_client(timeout_seconds=self._timeout) as client:
            while True:
                params: dict[str, Any] = {
                    "channel": channel_id,
                    "ts": thread_ts,
                    "limit": min(limit, 100),
                }
                if cursor:
                    params["cursor"] = cursor

                resp = client.get(
                    f"{self.BASE_URL}/conversations.replies",
                    headers=self._headers(access_token),
                    params=params,
                )
                if is_rate_limit_response(resp):
                    break
                raise_for_provider_error(resp, provider="slack", endpoint_label="conversations.replies")
                data = resp.json()
                self._check_slack_response(data, "conversations.replies")

                batch = data.get("messages", [])
                replies.extend(batch)

                next_cursor = (
                    data.get("response_metadata", {}).get("next_cursor")
                    if isinstance(data.get("response_metadata"), dict)
                    else None
                )
                if not next_cursor or len(replies) >= 200:
                    break
                cursor = str(next_cursor).strip()

        return replies

    def get_permalink(self, access_token: str, channel_id: str, message_ts: str) -> str | None:
        """Get canonical web permalink for a Slack message."""
        try:
            with create_integration_http_client(timeout_seconds=self._timeout) as client:
                resp = client.get(
                    f"{self.BASE_URL}/chat.getPermalink",
                    headers=self._headers(access_token),
                    params={"channel": channel_id, "message_ts": message_ts},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        return str(data.get("permalink") or "")
        except Exception as exc:
            logger.debug("Failed to get Slack permalink: %s", exc)
        return None
