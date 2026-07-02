#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    text = (ROOT / "docs/autonomous-mode-runbook.md").read_text(encoding="utf-8")
    required = [
        "Actions",
        "Autonomous Growth Loop",
        "Run workflow",
        "confirm_autonomous",
        "account_id",
        "posted_results",
        "Dry-run autonomous plan",
        "Apply autonomous Threads loop",
    ]
    checks = [(f"mentions {item}", item in text) for item in required]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
