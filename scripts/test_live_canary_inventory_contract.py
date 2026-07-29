#!/usr/bin/env python3
from build_live_canary_inventory import build_inventory

datasets={key: [] for key in ("queue", "source_posts", "source_post_media", "media_permissions", "source_videos", "video_clip_candidates", "media_assets")}
datasets["queue"]=[{"account_id":"night_scout","status":"READY","generation_mode":"original_text","public_post_text":"読者が役立つ自然な投稿です。","validator_status":"PASS","account_fit_status":"PASS"}]
result=build_inventory(datasets)
assert result["total_canaries"] == 12
row=next(item for item in result["canaries"] if item["canary_id"] == "canary_night_scout_original_text")
assert row["status"] == "READY_FOR_HUMAN_CANARY"
assert result["would_post"] is False
print("PASS test_live_canary_inventory_contract.py")
