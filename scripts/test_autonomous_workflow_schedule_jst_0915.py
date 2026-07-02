#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    text = (ROOT / ".github/workflows/autonomous-growth-loop.yml").read_text(encoding="utf-8")
    docs = (ROOT / "docs/autonomous-mode-runbook.md").read_text(encoding="utf-8")
    checks = [
        ("cron is jst 0915", 'cron: "15 0 * * *"' in text),
        ("jst comment exists", "JST 09:15 daily" in text),
        ("docs mention jst 0915", "JST 09:15" in docs),
        ("docs mention daily", "daily" in docs.lower() or "毎日" in docs),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
