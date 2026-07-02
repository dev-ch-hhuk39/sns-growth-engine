#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    cfg = json.loads((ROOT / "config/autonomous_mode.json").read_text(encoding="utf-8"))
    checks = [
        ("config exists", bool(cfg)),
        ("autonomous enabled", cfg.get("autonomous_mode_enabled") is True),
        ("auto source fetch enabled", cfg.get("auto_source_fetch_enabled") is True),
        ("auto ready enabled", cfg.get("auto_ready_enabled") is True),
        ("auto post enabled", cfg.get("auto_post_enabled") is True),
        ("human review disabled", cfg.get("human_review_required") is False),
        ("threads only post", cfg.get("allowed_platforms_for_post") == ["threads"]),
        ("x blocked post", "x" in cfg.get("blocked_platforms_for_post", [])),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
