#!/usr/bin/env python3
"""Direct-media proof and schedule share the JST 04:00 business-day cap."""
import json
from datetime import datetime, timezone
from pathlib import Path

from run_direct_reference_media_pipeline import _today_posts

ROOT = Path(__file__).resolve().parents[1]
config = json.loads((ROOT / "config/media_growth_engine.json").read_text(encoding="utf-8"))
now = datetime.now(timezone.utc).isoformat()
rows = [
    {"account_id": "liver_manager", "platform": "threads", "status": "POSTED", "posted_at": now, "generation_mode": "direct_reference_media"},
    {"account_id": "night_scout", "platform": "threads", "status": "POSTED", "posted_at": now, "generation_mode": "direct_reference_media"},
    {"account_id": "liver_manager", "platform": "threads", "status": "FAILED", "posted_at": now, "generation_mode": "direct_reference_media"},
]
today = _today_posts(rows, "liver_manager")
checks = [
    ("only successful target-account rows count", len(today) == 1),
    ("direct media cap is one", config.get("direct_media_daily_post_cap") == 1),
    ("generated/direct combined media cap remains bounded", config.get("media_daily_post_cap") == 2),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
failed = [name for name, ok in checks if not ok]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
