#!/usr/bin/env python3
"""AUTOPOST must stay disabled after the first account pilots."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "config/auto_approval_rules.json"


def main() -> int:
    defaults = json.loads(RULES.read_text(encoding="utf-8")).get("defaults", {})
    checks = [
        ("auto post disabled", defaults.get("auto_post_enabled") is False),
        ("daily post cap one", int(defaults.get("daily_post_cap", 0)) == 1),
        ("cooldown 180", int(defaults.get("cooldown_minutes", 0)) == 180),
        ("max posts one", int(defaults.get("max_posts_per_run", 0)) == 1),
        ("kill switch present", "kill_switch" in defaults),
        ("media posts disabled", defaults.get("allow_media_posts") is False),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
