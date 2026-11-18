"""Real-time live monitor for Ollama knowledge extractions and grounding validation."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

# Enable ANSI escape codes on Windows 10/11 terminals
if sys.platform == "win32":
    import ctypes
    kernel32 = ctypes.windll.kernel32
    kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
BLUE = "\033[94m"


def get_ollama_ps() -> list[dict]:
    """Query local Ollama /api/ps for currently loaded models."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/ps", timeout=1.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("models", [])
    except Exception:
        return []


def format_size(num_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} TB"


def format_ts(iso_ts: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00")).astimezone()
        return dt.strftime("%H:%M:%S")
    except Exception:
        return iso_ts[:19]


def print_event(entry: dict) -> None:
    ev_type = entry.get("event", "")
    ts = format_ts(entry.get("timestamp", ""))
    batch = entry.get("batch_number", "?")
    title = entry.get("evidence_title", "unknown")
    chunks = entry.get("chunks_in_batch", "?")
    model = entry.get("model", "ollama")

    if ev_type == "batch_started":
        print(
            f"{DIM}[{ts}]{RESET} {YELLOW}⏳ STARTING{RESET} {BOLD}{model}{RESET} "
            f"on {CYAN}'{title}'{RESET} (batch {batch}, {chunks} chunks)..."
        )
    elif ev_type == "batch_completed":
        dur_s = (entry.get("duration_ms") or 0) / 1000.0
        cand = entry.get("candidates_count", 0)
        acc_count = entry.get("accepted_count", 0)
        rej_count = entry.get("rejected_count", 0)
        print(
            f"{DIM}[{ts}]{RESET} {GREEN}✅ COMPLETED{RESET} Batch {batch} on {CYAN}'{title}'{RESET} "
            f"in {BOLD}{dur_s:.1f}s{RESET} | Candidates: {cand} -> "
            f"{GREEN}{acc_count} ACCEPTED{RESET}, {RED}{rej_count} REJECTED{RESET}"
        )
        for acc in entry.get("accepted", []):
            cat = acc.get("category", "unknown")
            it_title = acc.get("title", "")
            conf = acc.get("confidence_score", 0.0)
            print(f"   {GREEN}● ACCEPTED{RESET} {MAGENTA}[{cat}]{RESET} {BOLD}{it_title}{RESET} {DIM}(conf={conf:.2f}){RESET}")
            for ex in acc.get("excerpts", []):
                clean_ex = ex.replace("\n", " ").strip()
                if len(clean_ex) > 160:
                    clean_ex = clean_ex[:157] + "..."
                print(f"     {DIM}Quote: \"{clean_ex}\"{RESET}")
        for rej in entry.get("rejected", []):
            cat = rej.get("category", "unknown")
            it_title = rej.get("title", "")
            reason = rej.get("reason", "unknown")
            print(f"   {RED}✕ REJECTED{RESET} {MAGENTA}[{cat}]{RESET} {it_title} -> {RED}{reason}{RESET}")
        print()
    elif ev_type == "batch_failed":
        err = entry.get("error", "unknown error")
        print(
            f"{DIM}[{ts}]{RESET} {RED}❌ FAILED{RESET} Batch {batch} on {CYAN}'{title}'{RESET}: {RED}{err}{RESET}\n"
        )


def print_ollama_status_banner() -> None:
    models = get_ollama_ps()
    if not models:
        print(f"{DIM}[Ollama Status] Idle (no models loaded in VRAM){RESET}")
        return
    parts = []
    for m in models:
        name = m.get("name", "unknown")
        vram = format_size(m.get("size_vram", 0))
        total = format_size(m.get("size", 0))
        parts.append(f"{BOLD}{CYAN}{name}{RESET} (VRAM: {vram} / Total: {total})")
    print(f"{BLUE}[Ollama Active]{RESET} " + ", ".join(parts))


def main() -> None:
    parser = argparse.ArgumentParser(description="Live monitor for Ollama knowledge extractions.")
    parser.add_argument("--history", type=int, default=15, help="Show last N events on startup (default: 15)")
    parser.add_argument("--clear", action="store_true", help="Clear existing extraction log before tailing")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    jsonl_path = repo_root / "logs" / "ollama_extractions.jsonl"
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    if args.clear and jsonl_path.exists():
        jsonl_path.write_text("", encoding="utf-8")
        txt_path = repo_root / "logs" / "ollama_extractions.log"
        if txt_path.exists():
            txt_path.write_text("", encoding="utf-8")
        print(f"{YELLOW}Cleared existing Ollama extraction logs.{RESET}")

    print(f"{BOLD}{CYAN}=== THE HANDOVER — LIVE OLLAMA EXTRACTION MONITOR ==={RESET}")
    print(f"{DIM}Tailing: {jsonl_path}{RESET}")
    print_ollama_status_banner()
    print("-" * 72)

    last_pos = 0
    if jsonl_path.exists():
        lines = jsonl_path.read_text(encoding="utf-8").splitlines()
        if args.history > 0 and lines:
            for line in lines[-args.history:]:
                line = line.strip()
                if not line:
                    continue
                try:
                    print_event(json.loads(line))
                except Exception:
                    pass
        last_pos = jsonl_path.stat().st_size

    last_status_check = time.time()
    try:
        while True:
            if jsonl_path.exists():
                current_size = jsonl_path.stat().st_size
                if current_size < last_pos:
                    # File was truncated/cleared
                    last_pos = 0
                if current_size > last_pos:
                    with open(jsonl_path, "r", encoding="utf-8") as f:
                        f.seek(last_pos)
                        new_data = f.read()
                        last_pos = f.tell()
                    for line in new_data.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            print_event(json.loads(line))
                        except Exception:
                            pass

            now = time.time()
            if now - last_status_check >= 15.0:
                last_status_check = now
                models = get_ollama_ps()
                if models:
                    print_ollama_status_banner()

            time.sleep(0.5)
    except KeyboardInterrupt:
        print(f"\n{DIM}Monitor stopped.{RESET}")


if __name__ == "__main__":
    main()
