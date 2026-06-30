#!/usr/bin/env python3
"""Validate the real-post worker is capped to one post in autopilot."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "scripts/process_threads_queue.py"
AUTOPILOT = ROOT / "scripts/run_autopilot_loop.py"


def main() -> int:
    proc = subprocess.run(
        [sys.executable, str(WORKER), "--account-id", "night_scout", "--max-posts", "3", "--dry-run"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    src = AUTOPILOT.read_text(encoding="utf-8")
    checks = [
        ("worker rejects max_posts > 2 before Sheets", proc.returncode == 1 and "--max-posts is capped at 2" in proc.stdout),
        ("autopilot real path caps to 1", "str(min(args.max_posts, 1))" in src),
        ("autopilot dry path remains dry-run", "--dry-run" in src and "process_threads_queue.py" in src),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
