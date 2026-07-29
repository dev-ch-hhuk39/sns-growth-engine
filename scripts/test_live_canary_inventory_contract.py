#!/usr/bin/env python3
from build_live_canary_inventory import build_inventory

datasets={key: [] for key in ("queue", "source_posts", "source_post_media", "media_permissions", "source_videos", "video_clip_candidates", "media_assets")}
datasets["queue"]=[
    {"account_id":"night_scout","canary_id":"canary_fresh_night_scout_original_text_x","queue_id":"q_text","status":"READY","generation_mode":"original_text","public_post_text":"読者が役立つ自然な投稿です。","validator_status":"PASS","account_fit_status":"PASS","internal_leak_status":"PASS"},
    {"account_id":"night_scout","canary_id":"canary_fresh_night_scout_generated_clip_x","queue_id":"q_clip","status":"WAITING_REVIEW","media_type":"generated_clip","clip_candidate_id":"clip_system_owned_night_scout_run_generated_clip","public_post_text":"読者が役立つ自然な投稿です。","account_fit_status":"PASS","validator_status":"PASS","internal_leak_status":"PASS","publisher_media_type":"VIDEO"},
]
datasets["source_videos"]=[{"source_video_id":"video_system_owned_night_scout_run_generated_clip","source_id":"system_owned_night_scout_run_generated_clip"}]
datasets["video_clip_candidates"]=[{"clip_id":"clip_system_owned_night_scout_run_generated_clip","clip_candidate_id":"clip_system_owned_night_scout_run_generated_clip","account_id":"night_scout","source_platform":"system_generated_owned","source_video_id":"video_system_owned_night_scout_run_generated_clip","rights_status":"owned","public_post_text":"読者が役立つ自然な投稿です。","start_seconds":"0","end_seconds":"8"}]
datasets["media_permissions"]=[{"source_id":"system_owned_night_scout_run_generated_clip","account_id":"night_scout","rights_status":"owned","permission_status":"approved","evidence_reference":"run","allow_clip_repost":True,"revoked":False}]
datasets["media_assets"]=[{"media_id":"clip_asset","video_clip_id":"clip_system_owned_night_scout_run_generated_clip","storage_url":"https://example.invalid/clip.mp4","local_path":"/tmp/clip.mp4"}]
result=build_inventory(datasets)
assert result["total_canaries"] == 12
row=next(item for item in result["canaries"] if item["canary_type"] == "original_text" and item["account_id"] == "night_scout")
assert row["status"] == "READY_FOR_HUMAN_CANARY"
clip=next(item for item in result["canaries"] if item["canary_type"] == "generated_clip" and item["account_id"] == "night_scout")
assert clip["status"] == "READY_FOR_HUMAN_CANARY"
assert result["would_post"] is False

# The newest fresh queue, not sheet row order, must choose its own linked asset.
selection_data={key: [] for key in datasets}
selection_data["queue"]=[
    {"account_id":"night_scout","canary_id":"canary_fresh_old_image","queue_id":"q_old","status":"WAITING_REVIEW","content_type":"direct_image","source_post_id":"old_parent","media_asset_id":"old_asset","media_url":"https://example.invalid/old.png","public_post_text":"古い候補です。","created_at":"2026-07-01T00:00:00+00:00"},
    {"account_id":"night_scout","canary_id":"canary_fresh_new_image","queue_id":"q_new","status":"WAITING_REVIEW","content_type":"direct_image","source_post_id":"new_parent","media_asset_id":"new_asset","media_url":"https://example.invalid/new.png","public_post_text":"新しい候補です。","created_at":"2026-07-29T00:00:00+00:00"},
]
selection_data["source_posts"]=[
    {"source_post_id":"old_parent","source_id":"old_source","target_account_id":"night_scout"},
    {"source_post_id":"new_parent","source_id":"new_source","target_account_id":"night_scout"},
]
selection_data["media_permissions"]=[
    {"source_id":"old_source","account_id":"night_scout","rights_status":"owned","permission_status":"approved","evidence_reference":"old","allow_original_repost":True,"revoked":False},
    {"source_id":"new_source","account_id":"night_scout","rights_status":"owned","permission_status":"approved","evidence_reference":"new","allow_original_repost":True,"revoked":False},
]
selection_data["media_assets"]=[
    {"media_id":"old_asset","storage_url":"https://example.invalid/old.png"},
    {"media_id":"new_asset","storage_url":"https://example.invalid/new.png"},
]
selected=build_inventory(selection_data)
direct_image=next(item for item in selected["candidates"] if item["account_id"] == "night_scout" and item["canary_type"] == "direct_image")
assert direct_image["canary_id"] == "canary_fresh_new_image"
assert direct_image["media_asset_id"] == "new_asset"
assert direct_image["queue_id"] == "q_new"
print("PASS test_live_canary_inventory_contract.py")
