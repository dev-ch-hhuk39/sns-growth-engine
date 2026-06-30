#!/usr/bin/env python3
"""AUTOPOST must remain disabled by default."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "config/auto_approval_rules.json"


def main() -> int:
    rules = json.loads(RULES.read_text(encoding="utf-8"))
    defaults = rules.get("defaults", {})
    checks = [
        ("auto_ready may be enabled", defaults.get("auto_ready_enabled") is True),
        ("auto_post disabled", defaults.get("auto_post_enabled") is False),
        ("daily post cap one", int(defaults.get("daily_post_cap", 0)) == 1),
        ("max posts per run one", int(defaults.get("max_posts_per_run", 0)) == 1),
        ("media posts disabled", defaults.get("allow_media_posts") is False),
        ("third-party media disabled", defaults.get("allow_third_party_media") is False),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
