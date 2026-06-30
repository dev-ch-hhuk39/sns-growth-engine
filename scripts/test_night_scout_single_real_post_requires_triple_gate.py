#!/usr/bin/env python3
"""night_scout real post path remains single-post and triple-gated."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "scripts/process_threads_queue.py"


def main() -> int:
    src = WORKER.read_text(encoding="utf-8")
    checks = [
        ("night_scout allowed account", '"night_scout"' in src),
        ("beauty blocked", "BEAUTY_BLOCKED" in src and "beauty_account" in src),
        ("threads only", 'platform != "threads"' in src),
        ("confirm required", "--confirm-real-post required" in src),
        ("publish env required", "PUBLISH_ENABLED" in src),
        ("threads env required", "ALLOW_REAL_THREADS_POST" in src),
        ("max-posts cap present", "--max-posts is capped at 2" in src),
        ("failure no retry", "no immediate retry" in src),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
