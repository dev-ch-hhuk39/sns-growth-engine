#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    manual = (ROOT / ".github/workflows/autonomous-growth-loop.yml").read_text(encoding="utf-8")
    night = (ROOT / ".github/workflows/autonomous-growth-loop-night-scout.yml").read_text(encoding="utf-8")
    liver = (ROOT / ".github/workflows/autonomous-growth-loop-liver-manager.yml").read_text(encoding="utf-8")
    docs = (ROOT / "docs/autonomous-mode-runbook.md").read_text(encoding="utf-8")
    checks = [
        ("manual workflow stays dispatch only", "schedule:" not in manual and "workflow_dispatch:" in manual),
        ("account schedules active", "schedule:" in night and "schedule:" in liver),
        ("first apply success documented", "first Actions apply succeeded" in docs or "初回Actions apply成功済み" in docs),
        ("account schedules documented", "night_scout" in docs and "liver_manager" in docs),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
