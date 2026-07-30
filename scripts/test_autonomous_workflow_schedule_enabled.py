#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    night = (ROOT / ".github/workflows/autonomous-growth-loop-night-scout.yml").read_text(encoding="utf-8")
    liver = (ROOT / ".github/workflows/autonomous-growth-loop-liver-manager.yml").read_text(encoding="utf-8")
    checks = [
        ("night schedule block enabled", "schedule:" in night),
        ("liver schedule block enabled", "schedule:" in liver),
        ("workflow_dispatch still exists", "workflow_dispatch:" in night and "workflow_dispatch:" in liver),
        ("scheduled apply is activation gated", all(value in night and value in liver for value in ["Resolve autonomous execution mode", "scheduled_publish_enabled", "production_publish_activation_approved", "RUN_AUTONOMOUS_APPLY"])),
        ("apply step uses resolved gate", "if: env.RUN_AUTONOMOUS_APPLY == 'true'" in night and "if: env.RUN_AUTONOMOUS_APPLY == 'true'" in liver),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
