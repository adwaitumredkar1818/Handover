"""Real-time live audit logging for Ollama extraction and grounding validation."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_LOG_LOCK = threading.Lock()

def _get_log_dir() -> Path:
    """Resolve repository logs directory cleanly."""
    # backend/app/services/ollama_live_log.py -> parents[3] is repo root
    repo_root = Path(__file__).resolve().parents[3]
    logs_dir = repo_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def record_ollama_batch_started(
    *,
    model_name: str,
    batch_num: int,
    chunks_count: int,
    evidence_id: str,
    evidence_title: str,
    project_id: str,
) -> None:
    """Record batch start event for real-time monitoring."""
    entry = {
        "event": "batch_started",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model_name,
        "batch_number": batch_num,
        "chunks_in_batch": chunks_count,
        "evidence_id": evidence_id,
        "evidence_title": evidence_title,
        "project_id": project_id,
    }
    _append_event(entry)


def record_ollama_batch_completed(
    *,
    model_name: str,
    batch_num: int,
    chunks_count: int,
    evidence_id: str,
    evidence_title: str,
    project_id: str,
    duration_ms: float,
    candidates_count: int,
    accepted_items: list[Any],
    rejected_items: list[dict[str, Any]],
) -> None:
    """Record batch completed event with detailed extracted and rejected candidates."""
    accepted_payload = []
    for it in accepted_items:
        cat_str = it.category.value if hasattr(it.category, "value") else str(it.category)
        excerpts = [
            link.supporting_excerpt for link in getattr(it, "evidence_links", [])
            if getattr(link, "supporting_excerpt", None)
        ]
        accepted_payload.append({
            "category": cat_str,
            "title": it.title,
            "summary": getattr(it, "structured_summary", "") or getattr(it, "summary", ""),
            "confidence_score": float((getattr(it, "confidence_metadata", None) or {}).get("confidence_score", 0.75)),
            "excerpts": excerpts,
        })

    entry = {
        "event": "batch_completed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model_name,
        "batch_number": batch_num,
        "chunks_in_batch": chunks_count,
        "evidence_id": evidence_id,
        "evidence_title": evidence_title,
        "project_id": project_id,
        "duration_ms": duration_ms,
        "candidates_count": candidates_count,
        "accepted_count": len(accepted_payload),
        "rejected_count": len(rejected_items),
        "accepted": accepted_payload,
        "rejected": rejected_items,
    }
    _append_event(entry)


def record_ollama_batch_failed(
    *,
    model_name: str,
    batch_num: int,
    chunks_count: int,
    evidence_id: str,
    evidence_title: str,
    project_id: str,
    error_message: str,
) -> None:
    """Record batch failure event."""
    entry = {
        "event": "batch_failed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model_name,
        "batch_number": batch_num,
        "chunks_in_batch": chunks_count,
        "evidence_id": evidence_id,
        "evidence_title": evidence_title,
        "project_id": project_id,
        "error": error_message,
    }
    _append_event(entry)


def _append_event(entry: dict[str, Any]) -> None:
    """Thread-safe append of an event line to JSONL and human-readable log."""
    try:
        log_dir = _get_log_dir()
        jsonl_file = log_dir / "ollama_extractions.jsonl"
        txt_file = log_dir / "ollama_extractions.log"

        json_str = json.dumps(entry, default=str)
        with _LOG_LOCK:
            with open(jsonl_file, "a", encoding="utf-8") as f:
                f.write(json_str + "\n")

            # Also write formatted human-readable block
            ts = entry.get("timestamp", "")
            ev_type = entry.get("event", "")
            with open(txt_file, "a", encoding="utf-8") as f:
                if ev_type == "batch_started":
                    f.write(
                        f"[{ts}] STARTING Batch {entry.get('batch_number')} on '{entry.get('evidence_title')}' "
                        f"({entry.get('chunks_in_batch')} chunks) via {entry.get('model')}\n"
                    )
                elif ev_type == "batch_completed":
                    f.write(
                        f"[{ts}] COMPLETED Batch {entry.get('batch_number')} in {entry.get('duration_ms', 0):.0f}ms: "
                        f"{entry.get('candidates_count')} candidates -> {entry.get('accepted_count')} ACCEPTED, "
                        f"{entry.get('rejected_count')} REJECTED\n"
                    )
                    for acc in entry.get("accepted", []):
                        f.write(f"   [ACCEPTED] [{acc.get('category')}] {acc.get('title')} (conf={acc.get('confidence_score')})\n")
                        for ex in acc.get("excerpts", []):
                            f.write(f"      Quote: \"{ex}\"\n")
                    for rej in entry.get("rejected", []):
                        f.write(f"   [REJECTED] [{rej.get('category')}] {rej.get('title')} -> {rej.get('reason')}\n")
                    f.write("\n")
                elif ev_type == "batch_failed":
                    f.write(f"[{ts}] FAILED Batch {entry.get('batch_number')}: {entry.get('error')}\n\n")
    except Exception as exc:
        logger.debug("Failed writing ollama live extraction log: %s", exc)
