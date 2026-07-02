#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    workflow = (ROOT / ".github/workflows/autonomous-growth-loop.yml").read_text(encoding="utf-8")
    docs = (ROOT / "docs/autonomous-mode-runbook.md").read_text(encoding="utf-8")
    checks = [
        ("workflow_dispatch exists", "workflow_dispatch:" in workflow),
        ("confirm input exists", "confirm_autonomous:" in workflow),
        ("account choices exist", 'night_scout' in workflow and 'liver_manager' in workflow and 'all' in workflow),
        ("ui dispatch documented", "Run workflow" in docs and "confirm_autonomous" in docs and "account_id" in docs),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
