/**
 * Centralized illustrative data for the landing page.
 *
 * Uses a consistent "Payment Platform" sample project
 * with the same personnel, identifiers, and evidence
 * references across every section.
 *
 * ALL data is fictional / illustrative — clearly labeled
 * as such in every section that renders it.
 */

/* ───────────── People ───────────── */

export const PEOPLE = {
  outgoing: { name: "Alex Chen", initials: "AC", role: "Staff Backend Engineer" },
  reviewer: { name: "Jordan Lee", initials: "JL", role: "Engineering Lead" },
  incoming: { name: "Priya Shah", initials: "PS", role: "Backend Engineer" },
} as const;

/* ───────────── Project ───────────── */

export const PROJECT = {
  name: "Payment Platform",
  handoverId: "HO-1042",
  teamSize: 6,
} as const;

/* ───────────── Evidence References ───────────── */

export const EVIDENCE = {
  pr4827: {
    source: "github" as const,
    ref: "payment-core#4827",
    title: "Introduce Redis caching layer for session tokens",
    shortRef: "PR-4827",
  },
  proj103: {
    source: "jira" as const,
    ref: "PROJ-103",
    title: "Improve API response time for dashboard endpoints",
    shortRef: "PROJ-103",
  },
  dep014: {
    source: "jira" as const,
    ref: "DEP-014",
    title: "Redis 7.x dependency — upgrade before EOL",
    shortRef: "DEP-014",
  },
  slackArch: {
    source: "slack" as const,
    ref: "#payments-arch",
    title: "Thread: Redis vs Memcached for session caching",
    shortRef: "#payments-arch",
  },
  adr007: {
    source: "docs" as const,
    ref: "ADR-007.pdf",
    title: "Architecture Decision Record: Event-driven settlement decoupling",
    shortRef: "ADR-007",
  },
  adr012: {
    source: "docs" as const,
    ref: "ADR-012.pdf",
    title: "Architecture Decision Record: Redis caching strategy",
    shortRef: "ADR-012",
  },
  runbook: {
    source: "docs" as const,
    ref: "settlement-runbook.pdf",
    title: "Settlement Worker Operational Runbook",
    shortRef: "Runbook",
  },
} as const;

/* ───────────── Knowledge Domains ───────────── */

export const KNOWLEDGE_DOMAINS = [
  {
    key: "Decisions & Rationale",
    shortKey: "Decisions",
    icon: "Lightbulb" as const,
    color: "#315FBA",
    accentRgb: "49,95,186",
    description: "Architectural choices, trade-offs, and the reasoning behind them.",
    finding: "Decouple settlement from ledger via Kafka event stream",
    findingMeta: "Alex Chen · Accepted · 3 evidence sources",
    count: 12,
  },
  {
    key: "Technical & Architectural Knowledge",
    shortKey: "Architecture",
    icon: "Layers" as const,
    color: "#203653",
    accentRgb: "32,54,83",
    description: "System design, data flows, infrastructure constraints, and patterns.",
    finding: "Settlement worker consumes Kafka events with idempotent writes",
    findingMeta: "Component: Settlement Service · 4 evidence sources",
    count: 9,
  },
  {
    key: "Completed & Unfinished Work",
    shortKey: "Work Status",
    icon: "ListChecks" as const,
    color: "#299B80",
    accentRgb: "41,155,128",
    description: "What was delivered, what was deferred, and what remains in progress.",
    finding: "Redis caching layer merged but performance benchmarks incomplete",
    findingMeta: "PR-4827 · Merged · Follow-up PROJ-108 pending",
    count: 8,
  },
  {
    key: "Responsibilities & Ownership",
    shortKey: "Ownership",
    icon: "UserRound" as const,
    color: "#7997BE",
    accentRgb: "121,151,190",
    description: "Who owns what, operational duties, and pending transitions.",
    finding: "Rotate acquirer API credentials and update certificates",
    findingMeta: "Primary: Alex Chen → Successor: Priya Shah · Due Jun 30",
    count: 6,
  },
  {
    key: "Dependencies",
    shortKey: "Dependencies",
    icon: "Network" as const,
    color: "#D39B43",
    accentRgb: "211,155,67",
    description: "Service relationships, third-party APIs, and blocking constraints.",
    finding: "SOAP migration blocked until acquirer credential rotation completes",
    findingMeta: "Component blocking dependency · Critical path",
    count: 7,
  },
  {
    key: "Bugs, Blockers & Risks",
    shortKey: "Risks",
    icon: "AlertTriangle" as const,
    color: "#D36D72",
    accentRgb: "211,109,114",
    description: "Unresolved failure modes, technical debt, and known blockers.",
    finding: "Settlement worker has no retry mechanism on acquirer timeouts",
    findingMeta: "High severity · Settlement Service · Manual recovery required",
    count: 5,
  },
  {
    key: "Operational Procedures",
    shortKey: "Procedures",
    icon: "ClipboardList" as const,
    color: "#8B78C9",
    accentRgb: "139,120,201",
    description: "Runbooks, deployment processes, incident response, and maintenance routines.",
    finding: "Settlement batch requires manual restart after acquirer outages",
    findingMeta: "Runbook section 4.2 · Last updated Mar 14",
    count: 6,
  },
  {
    key: "Historical Discussions & Context",
    shortKey: "Discussions",
    icon: "MessageSquare" as const,
    color: "#A0AEC0",
    accentRgb: "160,174,192",
    description: "Threaded debates, rejected alternatives, and institutional memory.",
    finding: "RabbitMQ was considered and rejected for settlement due to durability concerns",
    findingMeta: "#payments-arch · 14 replies · Concluded Feb 22",
    count: 5,
  },
] as const;

/* ───────────── Workflow Steps ───────────── */

export const WORKFLOW_STEPS = [
  {
    key: "Connect",
    description: "Link authorized GitHub repos, Jira projects, Slack channels, and uploaded documents to the project workspace.",
  },
  {
    key: "Reconstruct",
    description: "AI extracts decisions, architecture, ownership, risks, and dependencies with full source provenance.",
  },
  {
    key: "Verify",
    description: "Human reviewers evaluate candidate findings against original evidence and confirm, edit, or reject.",
  },
  {
    key: "Review",
    description: "Technical reviewers and project leads inspect the reconstructed knowledge for accuracy and completeness.",
  },
  {
    key: "Handover",
    description: "Generate structured, role-tailored handover packages for incoming team members with full audit trail.",
  },
] as const;

/* ───────────── Epistemic Tiers ───────────── */

export const EPISTEMIC_TIERS = [
  {
    tier: 1,
    label: "Original Source Evidence",
    description: "Commits, pull requests, issue threads, Slack messages, and uploaded documents exactly as authored.",
    color: "#A0AEC0",
    bgColor: "#F7FAFC",
    borderColor: "#E2E8F0",
  },
  {
    tier: 2,
    label: "Extracted Information",
    description: "Structured data parsed from source evidence — dates, authors, identifiers, and content segments.",
    color: "#315FBA",
    bgColor: "#EEF2FA",
    borderColor: "#C3D2EC",
  },
  {
    tier: 3,
    label: "AI-Generated Interpretation",
    description: "Candidate findings, relationship inferences, and confidence scores produced by the AI model.",
    color: "#8B78C9",
    bgColor: "#F4F2FA",
    borderColor: "#D3CCEC",
  },
  {
    tier: 4,
    label: "Human-Verified Knowledge",
    description: "Findings confirmed by designated reviewers. Only verified items contribute to handover completeness.",
    color: "#299B80",
    bgColor: "#EEF6F3",
    borderColor: "#BFDCD3",
  },
] as const;

/* ───────────── Domain Counts (must total 58) ───────────── */

export const DOMAIN_COUNTS = KNOWLEDGE_DOMAINS.map((d) => ({
  domain: d.shortKey,
  count: d.count,
}));

// Verification: 12+9+8+6+7+5+6+5 = 58
