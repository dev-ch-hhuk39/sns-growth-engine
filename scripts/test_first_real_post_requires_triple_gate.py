#!/usr/bin/env python3
"""Lock the first real Threads post behind the worker triple gate."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/process_threads_queue.py"


def main() -> int:
    src = SCRIPT.read_text(encoding="utf-8")
    checks = [
        ("confirm flag documented", "--confirm-real-post" in src),
        ("publish env required", "PUBLISH_ENABLED" in src),
        ("threads env required", "ALLOW_REAL_THREADS_POST" in src),
        ("confirm checked before env post", "if not confirm_real_post:" in src),
        ("missing gate blocks", '"status": "BLOCKED"' in src and "--confirm-real-post required" in src),
        ("media real post blocked", "SAFETY_STOP_MEDIA" in src),
        ("beauty blocked", "beauty_account" in src and "BEAUTY_BLOCKED" in src),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
