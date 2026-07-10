#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from discover_approved_source_videos import build_discovery_plan

plan = build_discovery_plan("liver_manager", apply=True, confirm_discovery=True, existing_source_videos=[])
checks = [
    ("not blocked when confirmed", plan["status"] != "BLOCKED"),
    ("apply save planned", plan["would_save_source_videos"] is True),
    ("new videos available", plan["new_video_count"] > 0),
    ("dedupe keys present", "video_id" in plan["dedupe_keys"] and "canonical_video_url" in plan["dedupe_keys"]),
    ("approved sources only", all(s["source_id"].startswith("src_lm_") for s in plan["selected_sources"])),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
