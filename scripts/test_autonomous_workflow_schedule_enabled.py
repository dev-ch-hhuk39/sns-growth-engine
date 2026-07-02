#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    text = (ROOT / ".github/workflows/autonomous-growth-loop.yml").read_text(encoding="utf-8")
    checks = [
        ("schedule block enabled", "schedule:" in text),
        ("schedule not commented", "# schedule:" not in text),
        ("workflow_dispatch still exists", "workflow_dispatch:" in text),
        ("schedule apply gated", "github.event_name == 'schedule' || github.event.inputs.confirm_autonomous == 'true'" in text),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
