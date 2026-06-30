#!/usr/bin/env python3
"""Scheduled autopilot workflow must never perform a real post."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/autopilot-auto-ready.yml"


def main() -> int:
    content = WORKFLOW.read_text(encoding="utf-8")
    checks = [
        ("workflow exists", WORKFLOW.exists()),
        ("has schedule", "schedule:" in content and "0 */6 * * *" in content),
        ("runs autopilot apply", "scripts/run_autopilot_loop.py" in content and "--apply" in content and "--confirm-run" in content),
        ("auto ready only", "--auto-ready" in content),
        ("skip real post", "--skip-real-post" in content),
        ("no confirm real post", "--confirm-real-post" not in content),
        ("posting env false", 'PUBLISH_ENABLED: "false"' in content and 'ALLOW_REAL_THREADS_POST: "false"' in content),
        ("no process worker real command", "process_threads_queue.py" not in content),
        ("no beauty option", "beauty_account" not in content),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
