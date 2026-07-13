#!/usr/bin/env python3
"""Regression checks for the canonical text/media slot split."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    schedule = json.loads((ROOT / "config/content_schedule.json").read_text())
    media = json.loads((ROOT / "config/media_growth_engine.json").read_text())
    night = schedule["accounts"]["night_scout"]
    liver = schedule["accounts"]["liver_manager"]
    checks = [
        ("subtitle rendering disabled", media.get("subtitle_enabled") is False),
        ("night has five canonical slots", len(night) == 5),
        ("liver has five canonical slots", len(liver) == 5),
        ("night media owns 21:00", any(s["slot_id"] == "ns_2100_media" and s["post_type"] == "approved_clip_candidate" for s in night)),
        ("liver media owns 18:00", any(s["slot_id"] == "lm_1800_media" and s["post_type"] == "approved_clip_candidate" for s in liver)),
        ("each account has unique cron slots", len({s["cron_utc"] for s in night}) == 5 and len({s["cron_utc"] for s in liver}) == 5),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
