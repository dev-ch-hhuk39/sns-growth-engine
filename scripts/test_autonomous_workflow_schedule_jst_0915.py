#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    night = (ROOT / ".github/workflows/autonomous-growth-loop-night-scout.yml").read_text(encoding="utf-8")
    liver = (ROOT / ".github/workflows/autonomous-growth-loop-liver-manager.yml").read_text(encoding="utf-8")
    docs = (ROOT / "docs/autonomous-mode-runbook.md").read_text(encoding="utf-8")
    checks = [
        ("night fixed UTC slots", all(cron in night for cron in ('cron: "45 4 * * *"', 'cron: "45 6 * * *"', 'cron: "45 15 * * *"'))),
        ("liver fixed UTC slots", all(cron in liver for cron in ('cron: "45 0 * * *"', 'cron: "45 3 * * *"', 'cron: "45 11 * * *"'))),
        ("docs mention account schedules", "night_scout" in docs and "liver_manager" in docs),
        ("docs mention daily", "daily" in docs.lower() or "毎日" in docs),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
