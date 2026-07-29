#!/usr/bin/env python3
from build_live_canary_inventory import build_inventory

datasets={key: [] for key in ("queue", "source_posts", "source_post_media", "media_permissions", "source_videos", "video_clip_candidates", "media_assets")}
datasets["queue"]=[{"account_id":"night_scout","status":"READY","generation_mode":"original_text","public_post_text":"読者が役立つ自然な投稿です。","validator_status":"PASS","account_fit_status":"PASS"}]
datasets["source_videos"]=[{"source_video_id":"video_system_owned_night_scout_run_generated_clip","source_id":"system_owned_night_scout_run_generated_clip"}]
datasets["video_clip_candidates"]=[{"clip_id":"clip_system_owned_night_scout_run_generated_clip","clip_candidate_id":"clip_system_owned_night_scout_run_generated_clip","account_id":"night_scout","source_platform":"system_generated_owned","source_video_id":"video_system_owned_night_scout_run_generated_clip","rights_status":"owned","public_post_text":"読者が役立つ自然な投稿です。","start_seconds":"0","end_seconds":"8"}]
datasets["media_permissions"]=[{"source_id":"system_owned_night_scout_run_generated_clip","account_id":"night_scout","rights_status":"owned","permission_status":"approved","evidence_reference":"run","allow_clip_repost":True,"revoked":False}]
datasets["media_assets"]=[{"media_id":"clip_asset","video_clip_id":"clip_system_owned_night_scout_run_generated_clip","storage_url":"https://example.invalid/clip.mp4","local_path":"/tmp/clip.mp4"}]
result=build_inventory(datasets)
assert result["total_canaries"] == 12
row=next(item for item in result["canaries"] if item["canary_id"] == "canary_night_scout_original_text")
assert row["status"] == "READY_FOR_HUMAN_CANARY"
clip=next(item for item in result["canaries"] if item["canary_id"] == "canary_night_scout_generated_clip")
assert clip["status"] == "READY_FOR_HUMAN_CANARY"
assert result["would_post"] is False
print("PASS test_live_canary_inventory_contract.py")
