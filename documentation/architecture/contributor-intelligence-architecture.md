# Contributor Intelligence Architecture

## Separation of Concerns
The system strictly separates three distinct concepts in `ContributionAttribution` (`backend/app/models/team_roster.py`) and `ContributionAttributionService` (`backend/app/services/contribution_attribution.py`):
1. **Observed Authorship**: GitHub commit/PR author metadata (`github_author_id`, `github_author_login`, `git_author_name`, `git_author_email`, `co_authors`, `changed_files`).
2. **Technical Work Classification**: Multi-category classification via deterministic changed-file paths, PR/issue labels, title/message keywords, and optional bounded Qwen3 fallback.
3. **Declared Responsibility**: Read from `ProjectMembership.responsibility_description` and confirmed `TeamRosterMember` records; never overwritten by observed commit domains.

## Identity Matching Hierarchy & Bot Recognition
- **Bot Recognition (`is_bot_identity` in `github_sync.py`)**: Checks provider `type == "Bot"` first, then known automation patterns (`[bot]`, `dependabot`, `renovate`, `github-actions`, `codecov`).
- **Member Matching Priority**:
  1. Exact verified `github_author_id`
  2. Exact confirmed `github_username`
  3. Exact verified `git_author_email`
  4. Verified GitHub `users.noreply.github.com` username
  5. Display-name matches remain `contributor_type="unidentified"`, `review_status="pending"`, `match_method="unverified_candidate"` (`0.50`) until human review.
- **Privacy**: `mask_email()` masks `git_author_email` for callers without `project.manage`.
- **Notifications**: Unmatched identities trigger an unread `"Contributor identities require review."` `NotificationItem` after GitHub sync.
