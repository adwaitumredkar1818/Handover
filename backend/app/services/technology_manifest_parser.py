"""Canonical technology normalisation and deterministic manifest parsers.

Parses repository manifest/configuration evidence (`package.json`, `requirements.txt`,
`pyproject.toml`, `Dockerfile`, `docker-compose.yml` / `compose.yaml`) safely without
executing any repository code or installation scripts, preserving exact source provenance
and distinguishing declared/configured/documented/implemented/proposed technologies.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

# Canonical technology registry: alias_lowercase -> (canonical_name, category, entity_type)
_TECH_ALIASES: dict[str, tuple[str, str, str]] = {
    # Frontend
    "next": ("Next.js", "frontend", "framework"),
    "next.js": ("Next.js", "frontend", "framework"),
    "nextjs": ("Next.js", "frontend", "framework"),
    "react": ("React", "frontend", "framework"),
    "react.js": ("React", "frontend", "framework"),
    "reactjs": ("React", "frontend", "framework"),
    "react-dom": ("React", "frontend", "framework"),
    "typescript": ("TypeScript", "frontend", "technology"),
    "tailwindcss": ("Tailwind CSS", "frontend", "framework"),
    "tailwind css": ("Tailwind CSS", "frontend", "framework"),
    "tailwind": ("Tailwind CSS", "frontend", "framework"),
    "@xyflow/react": ("React Flow", "frontend", "library"),
    "react flow": ("React Flow", "frontend", "library"),
    "reactflow": ("React Flow", "frontend", "library"),
    "@tanstack/react-query": ("TanStack Query", "frontend", "library"),
    "lucide-react": ("Lucide Icons", "frontend", "library"),
    "shadcn/ui": ("shadcn/ui", "frontend", "library"),
    # Backend
    "fastapi": ("FastAPI", "backend", "framework"),
    "fast api": ("FastAPI", "backend", "framework"),
    "python": ("Python", "backend", "technology"),
    "pydantic": ("Pydantic", "backend", "library"),
    "pydantic-settings": ("Pydantic", "backend", "library"),
    "uvicorn": ("Uvicorn", "backend", "technology"),
    "httpx": ("HTTPX", "backend", "library"),
    "pymupdf": ("PyMuPDF", "backend", "library"),
    "fitz": ("PyMuPDF", "backend", "library"),
    "python-docx": ("python-docx", "backend", "library"),
    "argon2-cffi": ("Argon2", "backend", "library"),
    "argon2": ("Argon2", "backend", "library"),
    "argon2id": ("Argon2", "backend", "library"),
    "pyjwt": ("PyJWT", "backend", "library"),
    "cryptography": ("Cryptography", "backend", "library"),
    # Database & Vector
    "postgresql": ("PostgreSQL", "database", "database"),
    "postgres": ("PostgreSQL", "database", "database"),
    "postgresql database": ("PostgreSQL", "database", "database"),
    "sqlalchemy": ("SQLAlchemy", "database", "library"),
    "alembic": ("Alembic", "database", "library"),
    "psycopg": ("Psycopg 3", "database", "library"),
    "psycopg 3": ("Psycopg 3", "database", "library"),
    "psycopg-binary": ("Psycopg 3", "database", "library"),
    "chromadb": ("ChromaDB", "database", "database"),
    "chroma": ("ChromaDB", "database", "database"),
    "redis": ("Redis", "database", "database"),
    # AI / ML
    "ollama": ("Ollama", "ai_ml", "technology"),
    "qwen3": ("Qwen3 8B", "ai_ml", "technology"),
    "qwen3:8b": ("Qwen3 8B", "ai_ml", "technology"),
    "qwen3 8b": ("Qwen3 8B", "ai_ml", "technology"),
    "nomic-embed-text": ("nomic-embed-text", "ai_ml", "technology"),
    "nomic-embed-text:latest": ("nomic-embed-text", "ai_ml", "technology"),
    "glm-ocr": ("GLM OCR", "ai_ml", "technology"),
    "glm-ocr:latest": ("GLM OCR", "ai_ml", "technology"),
    "gemini api": ("Gemini API", "ai_ml", "technology"),
    "gemini": ("Gemini API", "ai_ml", "technology"),
    # Backend / Security / Docs additions
    "reportlab": ("ReportLab", "backend", "library"),
    "jwt": ("PyJWT", "backend", "library"),
    "oauth 2.0": ("OAuth 2.0", "external_integrations", "technology"),
    "aes-256-gcm": ("AES-256-GCM", "backend", "technology"),
    "aes-256": ("AES-256-GCM", "backend", "technology"),
    # Storage & Auth & External
    "supabase": ("Supabase", "storage", "technology"),
    "supabase storage": ("Supabase Storage", "storage", "technology"),
    "@supabase/supabase-js": ("Supabase", "external_integrations", "library"),
    "@supabase/ssr": ("Supabase SSR", "external_integrations", "library"),
    "github": ("GitHub API", "external_integrations", "technology"),
    "jira": ("Jira API", "external_integrations", "technology"),
    "slack": ("Slack API", "external_integrations", "technology"),
    "resend": ("Resend", "external_integrations", "technology"),
    # Mobile
    "flutter": ("Flutter", "mobile", "framework"),
    "dart": ("Dart", "mobile", "technology"),
    # Infrastructure & Testing
    "docker": ("Docker", "infrastructure", "technology"),
    "docker compose": ("Docker Compose", "infrastructure", "technology"),
    "github actions": ("GitHub Actions", "infrastructure", "technology"),
    "cloudflare": ("Cloudflare", "infrastructure", "technology"),
    "pytest": ("Pytest", "testing", "library"),
    "vitest": ("Vitest", "testing", "library"),
    "@testing-library/react": ("React Testing Library", "testing", "library"),
    "eslint": ("ESLint", "testing", "library"),
    "ruff": ("Ruff", "testing", "library"),
    "mypy": ("Mypy", "testing", "library"),
}

_KNOWN_PREFIX_CATEGORIES: tuple[tuple[str, str, str], ...] = (
    ("node:", "infrastructure", "technology"),
    ("python:", "backend", "technology"),
    ("postgres:", "database", "database"),
    ("chromadb/", "database", "database"),
    ("redis:", "database", "database"),
)

_MANIFEST_FILENAMES = frozenset(
    {
        "package.json",
        "requirements.txt",
        "pyproject.toml",
        "dockerfile",
        "compose.yaml",
        "compose.yml",
        "docker-compose.yml",
        "docker-compose.yaml",
        "pubspec.yaml",
    }
)


@dataclass(frozen=True, slots=True)
class ParsedTechnologyDetection:
    """Deterministic technology detection extracted from a repository manifest or doc."""

    canonical_name: str
    raw_name: str
    category: str
    entity_type: str
    version: str | None = None
    usage_basis: str = "declared_dependency"
    purpose: str | None = None
    source_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def is_manifest_path(path: str | None) -> bool:
    """Return True when the repository path points to a supported technical manifest."""
    if not path:
        return False
    clean_path = path.split(":", 1)[1].strip() if (":" in path and not path.startswith("http")) else path
    basename = clean_path.replace("\\", "/").strip().split("/")[-1].lower()
    return basename in _MANIFEST_FILENAMES or basename.startswith("dockerfile.")


def canonicalize_technology_name(
    raw_name: str,
    *,
    default_category: str = "backend",
) -> tuple[str, str, str]:
    """Conservatively canonicalize a technology label to `(canonical_name, category, entity_type)`.

    Never collapses distinct technologies (e.g. `GitHub Actions` stays distinct from `GitHub`).
    """
    cleaned = re.sub(r"\s+", " ", (raw_name or "").strip())
    if not cleaned:
        return "", default_category, "technology"

    key = cleaned.lower()
    if key in _TECH_ALIASES:
        return _TECH_ALIASES[key]

    # Strip trailing parenthetical version/notes if base matches a known tech
    base_only = re.sub(r"\s*\([^)]*\)$", "", key).strip()
    if base_only in _TECH_ALIASES:
        return _TECH_ALIASES[base_only]

    for prefix, cat, etype in _KNOWN_PREFIX_CATEGORIES:
        if key.startswith(prefix):
            return cleaned.split(":")[0].capitalize(), cat, etype

    # Heuristic category classification for unrecognized dependencies
    cat = default_category
    if any(k in key for k in ("test", "pytest", "vitest", "jest", "playwright", "eslint", "mypy", "ruff")):
        cat = "testing"
    elif any(k in key for k in ("react", "next", "tailwind", "radix", "lucide", "css", "html", "vite")):
        cat = "frontend"
    elif any(k in key for k in ("postgres", "sql", "alembic", "chroma", "redis", "mongo", "sqlite")):
        cat = "database"
    elif any(k in key for k in ("ollama", "qwen", "llm", "torch", "transformers", "ocr", "embed")):
        cat = "ai_ml"
    elif any(k in key for k in ("docker", "compose", "k8s", "nginx", "cloudflare", "uvicorn")):
        cat = "infrastructure"
    elif any(k in key for k in ("s3", "storage", "supabase")):
        cat = "storage"

    return cleaned, cat, "technology"


def _parse_package_json(path: str, content: str) -> list[ParsedTechnologyDetection]:
    try:
        data = json.loads(content)
    except Exception:
        return []
    if not isinstance(data, dict):
        return []

    results: list[ParsedTechnologyDetection] = []
    for section, is_dev in (("dependencies", False), ("devDependencies", True)):
        deps = data.get(section)
        if not isinstance(deps, dict):
            continue
        for pkg_name, ver in deps.items():
            if not isinstance(pkg_name, str) or not pkg_name.strip():
                continue
            canon, cat, etype = canonicalize_technology_name(
                pkg_name,
                default_category="testing" if is_dev else "frontend",
            )
            results.append(
                ParsedTechnologyDetection(
                    canonical_name=canon,
                    raw_name=pkg_name,
                    category=cat,
                    entity_type=etype,
                    version=str(ver).strip() if ver is not None else None,
                    usage_basis="declared_dependency",
                    purpose=f"Declared in {path} ({section})",
                    source_path=path,
                    metadata={"manifest_section": section, "is_dev_dependency": is_dev},
                )
            )
    return results


_REQ_LINE_RE = re.compile(r"^([A-Za-z0-9_.\-]+)(?:\[[^\]]+\])?\s*([<>=!~]=?[^\s;#]+)?")


def _parse_requirements_txt(path: str, content: str) -> list[ParsedTechnologyDetection]:
    results: list[ParsedTechnologyDetection] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        m = _REQ_LINE_RE.match(line)
        if not m:
            continue
        pkg_name = m.group(1)
        ver = m.group(2)
        canon, cat, etype = canonicalize_technology_name(pkg_name, default_category="backend")
        results.append(
            ParsedTechnologyDetection(
                canonical_name=canon,
                raw_name=pkg_name,
                category=cat,
                entity_type=etype,
                version=ver.strip() if ver else None,
                usage_basis="declared_dependency",
                purpose=f"Declared Python dependency in {path}",
                source_path=path,
                metadata={"manifest_section": "requirements"},
            )
        )
    return results


def _parse_pyproject_toml(path: str, content: str) -> list[ParsedTechnologyDetection]:
    results: list[ParsedTechnologyDetection] = []
    # Lightweight safe TOML dependency array scan without executing code
    in_deps = False
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line.startswith("dependencies") and "[" in line:
            in_deps = True
            continue
        if in_deps:
            if line.startswith("]"):
                in_deps = False
                continue
            cleaned = line.strip('", ')
            if not cleaned or cleaned.startswith("#"):
                continue
            m = _REQ_LINE_RE.match(cleaned)
            if m:
                pkg_name = m.group(1)
                ver = m.group(2)
                canon, cat, etype = canonicalize_technology_name(pkg_name, default_category="backend")
                results.append(
                    ParsedTechnologyDetection(
                        canonical_name=canon,
                        raw_name=pkg_name,
                        category=cat,
                        entity_type=etype,
                        version=ver.strip() if ver else None,
                        usage_basis="declared_dependency",
                        purpose=f"Declared in {path} [project.dependencies]",
                        source_path=path,
                        metadata={"manifest_section": "pyproject.dependencies"},
                    )
                )
    return results


def _parse_dockerfile(path: str, content: str) -> list[ParsedTechnologyDetection]:
    results: list[ParsedTechnologyDetection] = [
        ParsedTechnologyDetection(
            canonical_name="Docker",
            raw_name="Docker",
            category="infrastructure",
            entity_type="technology",
            usage_basis="configured_infrastructure",
            purpose=f"Container build defined in {path}",
            source_path=path,
        )
    ]
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line.upper().startswith("FROM "):
            image_spec = line.split()[1] if len(line.split()) > 1 else ""
            if image_spec:
                image_name, _, tag = image_spec.partition(":")
                base_short = image_name.split("/")[-1]
                canon, cat, etype = canonicalize_technology_name(
                    base_short, default_category="infrastructure"
                )
                results.append(
                    ParsedTechnologyDetection(
                        canonical_name=canon,
                        raw_name=image_spec,
                        category=cat,
                        entity_type=etype,
                        version=tag or None,
                        usage_basis="configured_infrastructure",
                        purpose=f"Container base image in {path}",
                        source_path=path,
                        metadata={"docker_image": image_spec},
                    )
                )
    return results


def _parse_compose_yaml(path: str, content: str) -> list[ParsedTechnologyDetection]:
    results: list[ParsedTechnologyDetection] = [
        ParsedTechnologyDetection(
            canonical_name="Docker Compose",
            raw_name="Docker Compose",
            category="infrastructure",
            entity_type="technology",
            usage_basis="configured_infrastructure",
            purpose=f"Multi-service orchestration defined in {path}",
            source_path=path,
        )
    ]
    for raw_line in content.splitlines():
        m = re.match(r"^\s*image:\s*['\"]?([^\s'\"]+)['\"]?", raw_line)
        if m:
            image_spec = m.group(1)
            image_name, _, tag = image_spec.partition(":")
            base_short = image_name.split("/")[-1]
            canon, cat, etype = canonicalize_technology_name(
                base_short, default_category="infrastructure"
            )
            results.append(
                ParsedTechnologyDetection(
                    canonical_name=canon,
                    raw_name=image_spec,
                    category=cat,
                    entity_type=etype,
                    version=tag or None,
                    usage_basis="configured_infrastructure",
                    purpose=f"Service image declared in {path}",
                    source_path=path,
                    metadata={"compose_image": image_spec},
                )
            )
    return results


def _parse_pubspec_yaml(path: str, content: str) -> list[ParsedTechnologyDetection]:
    results: list[ParsedTechnologyDetection] = [
        ParsedTechnologyDetection(
            canonical_name="Flutter",
            raw_name="Flutter",
            category="mobile",
            entity_type="framework",
            usage_basis="configured_project",
            purpose=f"Flutter application declared in {path}",
            source_path=path,
        )
    ]
    in_deps = False
    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        if not line or line.strip().startswith("#"):
            continue
        if line.startswith("dependencies:") or line.startswith("dev_dependencies:"):
            in_deps = True
            continue
        if in_deps:
            if not line.startswith(" ") and not line.startswith("\t"):
                in_deps = False
                continue
            m = re.match(r"^\s+([a-zA-Z0-9_\-]+)\s*:\s*([^#\n\r]*)$", line)
            if m:
                pkg = m.group(1).strip()
                ver = m.group(2).strip().strip('"\'') or None
                if pkg in ("sdk", "git", "path", "flutter"):
                    continue
                canon, cat, etype = canonicalize_technology_name(pkg, default_category="mobile")
                results.append(
                    ParsedTechnologyDetection(
                        canonical_name=canon,
                        raw_name=pkg,
                        category=cat,
                        entity_type=etype,
                        version=ver,
                        usage_basis="declared_dependency",
                        purpose=f"Declared dependency in {path}",
                        source_path=path,
                        metadata={"manifest_section": "pubspec.dependencies"},
                    )
                )
    return results


def parse_manifest_evidence(
    filename_or_path: str,
    content: str,
) -> list[ParsedTechnologyDetection]:
    """Deterministically parse supported technical manifests into canonical tech detections."""
    if not filename_or_path or not content:
        return []
    clean_path = (
        filename_or_path.split(":", 1)[1].strip()
        if (":" in filename_or_path and not filename_or_path.startswith("http"))
        else filename_or_path
    )
    norm = clean_path.replace("\\", "/").strip()
    basename = norm.split("/")[-1].lower()

    if basename == "package.json":
        return _parse_package_json(norm, content)
    if basename == "requirements.txt":
        return _parse_requirements_txt(norm, content)
    if basename == "pyproject.toml":
        return _parse_pyproject_toml(norm, content)
    if basename == "dockerfile" or basename.startswith("dockerfile."):
        return _parse_dockerfile(norm, content)
    if basename in {"compose.yaml", "compose.yml", "docker-compose.yml", "docker-compose.yaml"}:
        return _parse_compose_yaml(norm, content)
    if basename == "pubspec.yaml":
        return _parse_pubspec_yaml(norm, content)
    return []


_TEXT_SKIP_ALIASES: frozenset[str] = frozenset({"next", "fitz", "chroma"})
_CASE_SENSITIVE_ALIASES: frozenset[str] = frozenset({"react"})
_COMPILED_TECH_PATTERNS: list[tuple[str, str, str, str, re.Pattern[str]]] = [
    (
        alias,
        canon,
        cat,
        etype,
        re.compile(
            rf"(?<![A-Za-z0-9_.\-/]){re.escape(alias)}(?![A-Za-z0-9_.\-/])",
            0 if alias in _CASE_SENSITIVE_ALIASES else re.IGNORECASE,
        ),
    )
    for alias, (canon, cat, etype) in sorted(_TECH_ALIASES.items(), key=lambda kv: -len(kv[0]))
    if alias not in _TEXT_SKIP_ALIASES
]


def is_known_technology(raw_name: str | None) -> bool:
    """Return True only when `raw_name` resolves to a known canonical technology entry."""
    if not raw_name:
        return False
    cleaned = re.sub(r"\s+", " ", raw_name.strip()).lower()
    if not cleaned:
        return False
    if cleaned in _TECH_ALIASES:
        return True
    base_only = re.sub(r"\s*\([^)]*\)$", "", cleaned).strip()
    if base_only in _TECH_ALIASES:
        return True
    return any(cleaned.startswith(prefix) for prefix, _c, _e in _KNOWN_PREFIX_CATEGORIES)


_NEG_BEFORE_RE = re.compile(
    r"\b(?:no|not|never|without|prohibit\w*|forbid\w*|neither|nor)\b", re.IGNORECASE
)
_NEG_AFTER_RE = re.compile(
    r"\b(?:not permitted|prohibited|forbidden|excluded|not used)\b", re.IGNORECASE
)
_REACT_TECH_RE = re.compile(r"(?<![A-Za-z0-9_.\-/])React(?:\.js|JS)?(?![A-Za-z0-9_.\-/])")


def _is_match_negated(text: str, start: int, end: int) -> bool:
    """Return True when a matched technology occurrence sits in a negated clause."""
    pre_slice = text[max(0, start - 60) : start]
    for sep in ("\n", ";", ". "):
        idx = pre_slice.rfind(sep)
        if idx != -1:
            pre_slice = pre_slice[idx + len(sep) :]
    if _NEG_BEFORE_RE.search(pre_slice):
        return True

    post_slice = text[end : min(len(text), end + 40)]
    for sep in ("\n", ";", ". "):
        idx = post_slice.find(sep)
        if idx != -1:
            post_slice = post_slice[:idx]
    if _NEG_AFTER_RE.search(post_slice):
        return True
    return False


def extract_known_technologies_from_text(*texts: str | None) -> list[tuple[str, str, str]]:
    """Detect canonical technologies mentioned in text without matching arbitrary non-tech phrases."""
    combined = "\n".join(t for t in texts if isinstance(t, str) and t.strip())
    if not combined:
        return []
    found: dict[str, tuple[str, str, str]] = {}
    for alias, canon, cat, etype, pattern in _COMPILED_TECH_PATTERNS:
        active_pat = _REACT_TECH_RE if alias == "react" else pattern
        matches = list(active_pat.finditer(combined))
        if not matches:
            continue
        if any(not _is_match_negated(combined, m.start(), m.end()) for m in matches):
            found.setdefault(canon, (canon, cat, etype))
    return list(found.values())
