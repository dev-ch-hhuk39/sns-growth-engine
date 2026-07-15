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
        ("night direct and clip slots are explicit", {s["post_type"] for s in night} >= {"direct_reference_media", "generated_clip_media"}),
        ("liver direct and clip slots are explicit", {s["post_type"] for s in liver} >= {"direct_reference_media", "generated_clip_media"}),
        ("media cap permits both formal media slots", media.get("media_daily_post_cap") == 2),
        ("each account has unique cron slots", len({s["cron_utc"] for s in night}) == 5 and len({s["cron_utc"] for s in liver}) == 5),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
