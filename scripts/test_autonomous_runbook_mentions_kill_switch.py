#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    text = (ROOT / "docs/autonomous-mode-runbook.md").read_text(encoding="utf-8")
    checks = [
        ("kill switch documented", "kill_switch" in text),
        ("stop value documented", "kill_switch=true" in text),
        ("config path documented", "config/autonomous_mode.json" in text),
        ("bad post stop documented", "Stopping Bad Posts" in text),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
