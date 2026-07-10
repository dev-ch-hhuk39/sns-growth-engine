#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from discover_approved_source_videos import build_discovery_plan
from run_media_growth_engine import build_media_growth_plan

discovery = build_discovery_plan("liver_manager", apply=True, confirm_discovery=True, existing_source_videos=[])
plan = build_media_growth_plan(
    "liver_manager",
    apply=True,
    confirm_media_growth=True,
    existing_source_videos=discovery["new_videos"][:3],
)
checks = [
    ("media growth not blocked", plan["status"] != "BLOCKED"),
    ("source videos preferred", plan["source_videos_source"] == "existing_source_videos"),
    ("clip candidates generated", plan["clip_candidate_count"] > 0),
    ("public text valid", plan["final_public_post_validator"] == "PASS"),
    ("no real download", plan["would_download"] is False),
    ("no real cut", plan["would_cut"] is False),
    ("no real upload", plan["would_upload"] is False),
    ("no real video post", plan["would_post_video"] is False),
    ("schedule aftercare enabled", plan["media_plan"]["schedule_enabled"] is True),
    ("public video auto off", plan["media_plan"]["media_public_post_auto_enabled"] is False),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
