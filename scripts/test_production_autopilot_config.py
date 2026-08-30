#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
cfg = json.loads((ROOT / "config/production_autopilot.json").read_text(encoding="utf-8"))
auto = json.loads((ROOT / "config/autonomous_mode.json").read_text(encoding="utf-8"))
media = json.loads((ROOT / "config/media_growth_engine.json").read_text(encoding="utf-8"))
managed = json.loads((ROOT / "config/managed_accounts.json").read_text(encoding="utf-8"))["accounts"]

checks = [
    ("production autopilot enabled", cfg["production_autopilot_enabled"] is True),
    ("text public posting enabled", cfg["text_only_public_posting_enabled"] is True and auto["auto_post_enabled"] is True),
    ("account schedules enabled", cfg["account_scheduled_posting_enabled"] is True),
    ("metrics aftercare enabled", cfg["metrics_aftercare_enabled"] is True),
    ("bounded media discovery persists inventory", media["source_video_discovery_apply_enabled"] is True and media["auto_save_discovered_videos"] is True),
    ("clip candidate save active", media["auto_save_clip_candidates"] is True),
    ("approved media public posting active", cfg["media_public_posting_enabled"] is True and media["media_public_post_auto_enabled"] is True),
    ("x remains off", cfg["x_posting_enabled"] is False and "x" in auto["blocked_platforms_for_post"]),
    ("generic autonomous loop remains text-only", auto["allow_media_posts"] is False and auto["allow_video_download"] is False),
    ("beauty production uses strict autonomous review",
     cfg["beauty_posting_enabled"] is True
     and "beauty_account" in auto["allowed_accounts"]
     and managed["beauty_account"].get("review_policy") == "autonomous_strict_beauty"),
    ("learning rules not auto applied", cfg["learning_rules_auto_apply_enabled"] is False),
]

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
