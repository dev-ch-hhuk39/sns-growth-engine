#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    workflow = (ROOT / ".github/workflows/autonomous-growth-loop.yml").read_text(encoding="utf-8")
    docs = (ROOT / "docs/autonomous-mode-runbook.md").read_text(encoding="utf-8")
    checks = [
        ("schedule commented", "# schedule:" in workflow and '#   - cron: "15 0 * * *"' in workflow),
        ("schedule not active", "\nschedule:" not in workflow),
        ("first apply condition documented", "until one manual `workflow_dispatch` apply succeeds" in docs),
        ("cron documented", 'cron: "15 0 * * *"' in docs),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
