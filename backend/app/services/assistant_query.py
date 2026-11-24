"""Query Classifier and Entity Extractor for Project Knowledge Assistant.

Platform: The Handover
Module: Project Knowledge Assistant (Module 5 / AI Assistant Area)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models.enums import AssistantQueryType, KnowledgeCategory


@dataclass
class ClassifiedQuery:
    """Structured representation of a classified user question with extracted entities."""

    raw_query: str
    query_type: AssistantQueryType
    confidence: float
    extracted_jira_keys: list[str] = field(default_factory=list)
    extracted_pr_numbers: list[int] = field(default_factory=list)
    extracted_commit_hashes: list[str] = field(default_factory=list)
    extracted_file_paths: list[str] = field(default_factory=list)
    extracted_mentions: list[str] = field(default_factory=list)
    target_categories: list[KnowledgeCategory] = field(default_factory=list)
    search_keywords: list[str] = field(default_factory=list)
    expanded_queries: list[str] = field(default_factory=list)
    is_out_of_scope: bool = False
    out_of_scope_category: str | None = None
    refusal_reason: str | None = None


# Mapping of AssistantQueryType to related KnowledgeCategory values
_QUERY_TYPE_TO_CATEGORIES: dict[AssistantQueryType, list[KnowledgeCategory]] = {
    AssistantQueryType.PROJECT_OVERVIEW: [
        KnowledgeCategory.PROJECT_OVERVIEW_CONTEXT,
    ],
    AssistantQueryType.DECISION_RATIONALE: [
        KnowledgeCategory.DECISIONS_RATIONALE,
    ],
    AssistantQueryType.TECHNICAL_ARCHITECTURE: [
        KnowledgeCategory.TECHNICAL_ARCHITECTURE,
        KnowledgeCategory.ARCHITECTURE_TECHNICAL,
    ],
    AssistantQueryType.WORK_PROGRESS: [
        KnowledgeCategory.WORK_PROGRESS,
        KnowledgeCategory.WORK_ITEMS,
    ],
    AssistantQueryType.RESPONSIBILITY_OWNERSHIP: [
        KnowledgeCategory.RESPONSIBILITIES_OWNERSHIP,
    ],
    AssistantQueryType.DEPENDENCY_RELATIONSHIP: [
        KnowledgeCategory.DEPENDENCIES,
        KnowledgeCategory.DEPENDENCIES_RELATIONSHIPS,
    ],
    AssistantQueryType.RISK_PROBLEM: [
        KnowledgeCategory.BUGS_BLOCKERS_RISKS,
        KnowledgeCategory.RISKS_BLOCKERS_QUESTIONS,
    ],
    AssistantQueryType.OPERATIONAL_HISTORICAL: [
        KnowledgeCategory.OPERATIONAL_HISTORICAL,
    ],
    AssistantQueryType.TIMELINE_EVOLUTION: [
        KnowledgeCategory.OPERATIONAL_HISTORICAL,
        KnowledgeCategory.DECISIONS_RATIONALE,
    ],
    AssistantQueryType.COMPARATIVE: [
        KnowledgeCategory.DECISIONS_RATIONALE,
        KnowledgeCategory.TECHNICAL_ARCHITECTURE,
    ],
    AssistantQueryType.MULTI_HOP: [
        KnowledgeCategory.DEPENDENCIES,
        KnowledgeCategory.RESPONSIBILITIES_OWNERSHIP,
        KnowledgeCategory.DECISIONS_RATIONALE,
    ],
    AssistantQueryType.KNOWLEDGE_GAP: [
        KnowledgeCategory.BUGS_BLOCKERS_RISKS,
        KnowledgeCategory.PROJECT_OVERVIEW_CONTEXT,
    ],
    AssistantQueryType.GENERAL: [
        KnowledgeCategory.PROJECT_OVERVIEW_CONTEXT,
        KnowledgeCategory.TECHNICAL_ARCHITECTURE,
    ],
}


class AssistantQueryClassifier:
    """Classifies user queries across 12 product domains and extracts structural entities."""

    # Entity regex patterns
    JIRA_KEY_REGEX = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
    PR_NUMBER_REGEX = re.compile(r"(?:PR|pull request|#)\s*#?(\d+)\b", re.IGNORECASE)
    COMMIT_HASH_REGEX = re.compile(r"\b([0-9a-f]{7,40})\b", re.IGNORECASE)
    FILE_PATH_REGEX = re.compile(
        r"\b(?:[a-zA-Z0-9_\-./\\]+/[a-zA-Z0-9_\-./\\]+\.[a-zA-Z0-9]{1,8}|[a-zA-Z0-9_\-]+\.(?:py|ts|tsx|js|jsx|json|md|yaml|yml|sql|sh|toml|dockerfile))\b",
        re.IGNORECASE,
    )
    MENTION_REGEX = re.compile(r"@([a-zA-Z0-9_-]+)")

    # Classification keyword / regex rules (checked in prioritized order)
    RULES: list[tuple[AssistantQueryType, list[str], list[str]]] = [
        (
            AssistantQueryType.KNOWLEDGE_GAP,
            [
                "missing documentation",
                "knowledge gap",
                "unverified finding",
                "missing evidence",
                "unresolved conflict",
                "unsupported claim",
                "incomplete information",
                "what is unknown",
                "what is not documented",
            ],
            [r"\bmissing\b", r"\bgaps?\b", r"\bunverified\b", r"\bunresolved\b"],
        ),
        (
            AssistantQueryType.TIMELINE_EVOLUTION,
            [
                "timeline",
                "chronology",
                "chronological",
                "sequence of events",
                "evolution of",
                "history of",
                "when was",
                "what happened on",
                "what happened in",
            ],
            [r"\btimeline\b", r"\bchronolog\w+\b", r"\bsequence\b", r"\bwhen was\b"],
        ),
        (
            AssistantQueryType.COMPARATIVE,
            [
                "compare",
                "difference between",
                "versus",
                "trade-offs between",
                "pros and cons",
                "how does .* compare",
                "alternative to",
            ],
            [r"\bcompare\b", r"\bvs\.?\b", r"\bversus\b", r"\bdifference between\b"],
        ),
        (
            AssistantQueryType.MULTI_HOP,
            [
                "which commit introduced the bug in",
                "which commit introduced",
                "who made the decision that blocked",
                "which pr implements the decision",
                "how does the task connect to",
                "chain of events connecting",
            ],
            [
                r"\bwhich commit (?:introduced|fixed|caused|changed)\b",
                r"\bwho (?:made the decision|wrote the code) that (?:blocked|caused|fixed)\b",
                r"\bhow does .* connect to\b",
                r"\bmulti.?hop\b",
            ],
        ),
        (
            AssistantQueryType.RESPONSIBILITY_OWNERSHIP,
            [
                "who owns",
                "who is responsible",
                "ownership",
                "owner of",
                "who worked on",
                "maintainer",
                "who wrote",
                "who created",
                "assigned to",
                "point of contact",
                "successor",
                "departing member",
            ],
            [r"\bwho owns\b", r"\bwho is responsible\b", r"\bwho wrote\b", r"\bmaintainer\b"],
        ),
        (
            AssistantQueryType.DECISION_RATIONALE,
            [
                "why was",
                "why did we choose",
                "decision",
                "rationale",
                "adr",
                "architectural decision",
                "trade-off",
                "why use",
                "why select",
                "alternative considered",
                "reason for choosing",
            ],
            [r"\bwhy was\b", r"\bdecision\b", r"\brationale\b", r"\badr\b"],
        ),
        (
            AssistantQueryType.RISK_PROBLEM,
            [
                "risk",
                "blocker",
                "vulnerability",
                "bug",
                "flaw",
                "incident",
                "outage",
                "security issue",
                "technical debt",
                "known problem",
            ],
            [r"\brisks?\b", r"\bblockers?\b", r"\bbugs?\b", r"\bvulnerabilit\w+\b"],
        ),
        (
            AssistantQueryType.WORK_PROGRESS,
            [
                "progress",
                "status of",
                "what is completed",
                "unfinished",
                "in progress",
                "open tasks",
                "sprint",
                "backlog",
                "pending work",
                "what remains to be done",
                "work items",
            ],
            [r"\bstatus\b", r"\bcompleted\b", r"\bunfinished\b", r"\bprogress\b", r"\btasks?\b"],
        ),
        (
            AssistantQueryType.OPERATIONAL_HISTORICAL,
            [
                "how to deploy",
                "deployment",
                "runbook",
                "operational procedure",
                "how to configure",
                "environment variable",
                "setup instructions",
                "ci/cd",
                "how to run",
                "backup",
                "restore procedure",
            ],
            [r"\bdeploy\w*\b", r"\brunbook\b", r"\boperational\b", r"\bconfigure\b", r"\bsetup\b"],
        ),
        (
            AssistantQueryType.DEPENDENCY_RELATIONSHIP,
            [
                "dependency",
                "dependencies",
                "depends on",
                "relies on",
                "relationship between",
                "prerequisite",
                "what does .* depend",
                "downstream",
                "upstream",
            ],
            [r"\bdepend\w*\b", r"\brelies on\b", r"\bprerequisite\b"],
        ),
        (
            AssistantQueryType.TECHNICAL_ARCHITECTURE,
            [
                "architecture",
                "system design",
                "database schema",
                "endpoints",
                "api design",
                "data model",
                "backend design",
                "tech stack",
                "how does .* work",
                "implementation details",
            ],
            [r"\barchitectur\w*\b", r"\bschema\b", r"\bapi\b", r"\bendpoints?\b", r"\bdesign\b"],
        ),
        (
            AssistantQueryType.PROJECT_OVERVIEW,
            [
                "what is this project",
                "project overview",
                "core purpose",
                "mission",
                "summary of the project",
                "high-level overview",
                "about this project",
                "explain the project",
                "hello",
                "hi",
                "hey",
                "greetings",
            ],
            [r"\bwhat is (?:this|the) project\b", r"\bproject overview\b", r"\bcore purpose\b", r"^(?:hi|hello|hey|greetings)\b"],
        ),
    ]

    @classmethod
    def classify_scope(cls, query: str) -> tuple[bool, str | None, str | None]:
        """Detect out-of-scope personal, cross-project, platform secret, or injection queries."""
        q = (query or "").strip().lower()
        if not q:
            return False, None, None

        # 1. Prompt Injection / Jailbreak attempt
        if re.search(
            r"\b(?:ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions|disregard\s+(?:all\s+)?(?:previous|prior)\s+instructions|system\s+override|reveal\s+(?:the\s+)?system\s+prompt|print\s+(?:the\s+)?system\s+prompt|show\s+(?:the\s+)?developer\s+instructions)\b",
            q,
        ):
            return (
                True,
                "prompt_injection",
                "I cannot comply with instructions attempting to override system guardrails or extract confidential system instructions.",
            )

        # 2. Personal Device & Workstation Hardware Information (RTX 4050, laptop, RAM, CPU, OS, etc.)
        if re.search(
            r"\b(?:what\s+gpu\s+does\s+my\s+laptop\s+have|what\s+gpu\s+do\s+i\s+have|what\s+is\s+my\s+gpu|what\s+laptop\s+do\s+i\s+have|what\s+laptop\s+model|what\s+is\s+my\s+laptop|my\s+laptop\s+(?:specs|ram|cpu|gpu|model)|how\s+much\s+ram\s+do\s+i\s+have|what\s+is\s+my\s+ram|what\s+cpu\s+do\s+i\s+have|what\s+is\s+my\s+cpu|my\s+computer\s+specs|my\s+machine\s+specs|my\s+workstation\s+specs|what\s+operating\s+system\s+(?:do\s+i\s+have|is\s+on\s+my)|what\s+is\s+my\s+operating\s+system|what\s+is\s+my\s+ip\b|what\s+is\s+my\s+location|where\s+do\s+i\s+live|my\s+phone\s+number)\b",
            q,
        ) or (
            re.search(r"\b(?:my\s+laptop|my\s+workstation|my\s+computer|my\s+pc|my\s+machine|my\s+device)\b", q)
            and re.search(r"\b(?:gpu|cpu|ram|specs|graphics|vram|hardware|model|processor)\b", q)
        ):
            return (
                True,
                "personal_device",
                "I'm here to assist with the currently selected Handover project. I don't provide personal device or environment information through the Project Knowledge Assistant.",
            )

        # 3. Cross-Project Inquiries
        if re.search(
            r"\b(?:my\s+other\s+project|another\s+project|different\s+project|previous\s+project|other\s+project['s]?\s+architecture|architecture\s+(?:did\s+we\s+use|is\s+used)\s+in\s+my\s+other\s+project|what\s+did\s+we\s+do\s+in\s+(?:my\s+)?other\s+project)\b",
            q,
        ):
            return (
                True,
                "cross_project",
                "I can only access information from the currently selected project. Please switch to the relevant project if you have permission to access it.",
            )

        # 4. Personal History / Academic / Education
        if re.search(
            r"\b(?:what\s+course\s+am\s+i\s+studying|what\s+course\s+do\s+i\s+take|what\s+degree\s+am\s+i\s+pursuing|which\s+college\s+do\s+i\s+attend|what\s+is\s+my\s+education|my\s+girlfriend|my\s+family|my\s+personal\s+background)\b",
            q,
        ):
            return (
                True,
                "personal_history",
                "That information is outside the scope of this Project Knowledge Assistant. I can help with the currently selected project's documentation, architecture and work.",
            )

        # 5. Internal Platform Security Secrets (JWT keys, db passwords, live secrets)
        if re.search(
            r"\b(?:what\s+is\s+the\s+jwt\s+secret|jwt\s+signing\s+key|database\s+password|db\s+password|system\s+environment\s+variables|show\s+me\s+your\s+\.env)\b",
            q,
        ):
            return (
                True,
                "platform_secret",
                "Internal platform security credentials and configuration secrets are confidential and cannot be disclosed.",
            )

        return False, None, None

    def classify(self, query: str) -> ClassifiedQuery:
        """Classify a question string into an AssistantQueryType and extract key entities."""
        query_text = (query or "").strip()
        query_lower = query_text.lower()

        # Check project scope and disclosure guardrails upfront
        is_out_of_scope, scope_cat, refusal_reason = self.classify_scope(query_text)

        # 1. Extract entities
        jira_keys = list(dict.fromkeys(self.JIRA_KEY_REGEX.findall(query_text)))
        pr_matches = self.PR_NUMBER_REGEX.findall(query_text)
        pr_numbers = list(dict.fromkeys(int(m) for m in pr_matches if m.isdigit()))

        # Filter out git hashes that might accidentally match jira keys or short words
        potential_hashes = self.COMMIT_HASH_REGEX.findall(query_text)
        commit_hashes = [
            h for h in potential_hashes
            if len(h) >= 7 and not h.upper().startswith(("PROJ-", "HAND-", "JIRA-")) and any(c.isdigit() for c in h)
        ]

        file_paths = list(dict.fromkeys(self.FILE_PATH_REGEX.findall(query_text)))
        mentions = list(dict.fromkeys(m.rstrip(".,;:!?") for m in self.MENTION_REGEX.findall(query_text)))

        # 2. Check for multi-hop indicator: if multiple distinct entities appear together
        entity_types_count = sum(bool(x) for x in [jira_keys, pr_numbers, commit_hashes, file_paths, mentions])

        selected_type = AssistantQueryType.GENERAL
        confidence = 0.5

        # Check explicit rules
        best_score = 0
        for q_type, phrases, patterns in self.RULES:
            score = 0
            for phrase in phrases:
                if phrase in query_lower:
                    score += 6 if q_type in {AssistantQueryType.MULTI_HOP, AssistantQueryType.KNOWLEDGE_GAP} else 3
            for pat in patterns:
                if re.search(pat, query_lower, re.IGNORECASE):
                    score += 5 if q_type in {AssistantQueryType.MULTI_HOP, AssistantQueryType.KNOWLEDGE_GAP} else 2

            if score > best_score:
                best_score = score
                selected_type = q_type
                confidence = min(0.95, 0.5 + (score * 0.1))

        # Check multi-hop override if multiple distinct entities are queried together with relation terms
        if selected_type == AssistantQueryType.GENERAL and entity_types_count >= 2:
            selected_type = AssistantQueryType.MULTI_HOP
            confidence = 0.85
        elif entity_types_count >= 2 and any(k in query_lower for k in ["connect", "lead to", "introduced", "related", "path"]):
            selected_type = AssistantQueryType.MULTI_HOP
            confidence = 0.90

        # Extract search keywords (strip common stopwords)
        stopwords = {
            "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "with",
            "is", "was", "are", "were", "what", "which", "who", "whom", "how", "why",
            "can", "could", "would", "should", "does", "did", "do", "this", "that",
            "these", "those", "tell", "me", "about", "please", "give", "show",
        }
        tokens = re.findall(r"\b[a-zA-Z0-9_\-\.]{2,}\b", query_lower)
        search_keywords = [t for t in tokens if t not in stopwords]

        target_categories = _QUERY_TYPE_TO_CATEGORIES.get(selected_type, [
            KnowledgeCategory.PROJECT_OVERVIEW_CONTEXT,
        ])

        expanded_queries = self._generate_expanded_queries(
            raw_query=query_text,
            query_type=selected_type,
            keywords=search_keywords,
        )

        return ClassifiedQuery(
            raw_query=query_text,
            query_type=selected_type,
            confidence=confidence,
            extracted_jira_keys=jira_keys,
            extracted_pr_numbers=pr_numbers,
            extracted_commit_hashes=commit_hashes,
            extracted_file_paths=file_paths,
            extracted_mentions=mentions,
            target_categories=target_categories,
            search_keywords=search_keywords,
            expanded_queries=expanded_queries,
            is_out_of_scope=is_out_of_scope,
            out_of_scope_category=scope_cat,
            refusal_reason=refusal_reason,
        )

    def _generate_expanded_queries(
        self,
        *,
        raw_query: str,
        query_type: AssistantQueryType,
        keywords: list[str],
    ) -> list[str]:
        """Generate targeted subqueries and domain synonyms to maximize retrieval recall."""
        expansions: list[str] = [raw_query]
        kw_set = {k.lower() for k in keywords}

        # 1. Cleaned keyword sequence and OR disjunction for high recall
        if len(keywords) >= 2:
            expansions.append(" ".join(keywords))
            expansions.append(" OR ".join(keywords[:3]))

        # 2. Domain-targeted conceptual expansion
        if kw_set.intersection({"citation", "citations", "priority", "priorities", "ranking", "evidence", "scoring", "types"}):
            expansions.append("citation priority ranking algorithm evidence scoring reciprocal rank fusion authority")
            expansions.append("evidence retrieval ranking weighting source authority verified status")

        if kw_set.intersection({"auth", "authentication", "login", "identity", "jwt", "session", "token", "tokens"}):
            expansions.append("platform identity authentication argon2id jwt access token refreshsession rbac")

        if kw_set.intersection({"storage", "provider", "upload", "encryption", "s3", "supabase", "bucket", "file"}):
            expansions.append("storage provider local encrypted supabase aes-256-gcm private bucket envelope encryption")

        if kw_set.intersection({"vram", "ollama", "rtx", "4050", "gpu", "inference", "concurrency", "contention"}):
            expansions.append("rtx 4050 vram contention ollama inference scheduler qwen3 glm-ocr concurrency")

        if kw_set.intersection({"database", "postgres", "postgresql", "chroma", "chromadb", "vector", "fts", "search"}):
            expansions.append("postgresql canonical database chromadb vector store fts tsvector hybrid retrieval")

        if kw_set.intersection({"handover", "package", "transfer", "signoff", "approval", "checklist", "export"}):
            expansions.append("handover package approval workflow human reviewer signoff checklist receipt acknowledgement")

        # 3. Query-type structural variation
        if query_type == AssistantQueryType.DECISION_RATIONALE:
            expansions.append(f"{' '.join(keywords[:4])} architectural decision rationale trade-offs")
        elif query_type == AssistantQueryType.TECHNICAL_ARCHITECTURE:
            expansions.append(f"{' '.join(keywords[:4])} technical architecture implementation specification")
        elif query_type == AssistantQueryType.DEPENDENCY_RELATIONSHIP:
            expansions.append(f"{' '.join(keywords[:4])} relationship dependencies graph connections")
        elif query_type == AssistantQueryType.RISK_PROBLEM:
            expansions.append(f"{' '.join(keywords[:4])} blockers risks issues bugs mitigation")
        elif query_type == AssistantQueryType.WORK_PROGRESS:
            expansions.append(f"{' '.join(keywords[:4])} unfinished tasks progress milestones status")

        # Deduplicate while preserving order, cap at 5
        seen = set()
        unique_expansions = []
        for q in expansions:
            cleaned = q.strip()
            if cleaned and cleaned.lower() not in seen:
                seen.add(cleaned.lower())
                unique_expansions.append(cleaned)
                if len(unique_expansions) >= 5:
                    break

        return unique_expansions

