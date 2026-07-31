#!/usr/bin/env python3
from build_live_canary_inventory import build_inventory

MEDIA_EVIDENCE = {
    "feature_schema_version": "post_features_v1",
    "media_primary_topic": "work_conditions",
    "visual_topic": "work_conditions",
    "visual_topic_match": "True",
    "visual_cta_match": "True",
    "visual_plan_version": "visual_plan_v1",
    "visual_text_hash": "visual-hash",
    "claim_support_json": "[{\"verified\": true}]",
}

datasets={key: [] for key in ("queue", "source_posts", "source_post_media", "media_permissions", "source_videos", "video_clip_candidates", "media_assets")}
datasets["queue"]=[
    {"account_id":"night_scout","canary_id":"canary_fresh_night_scout_original_text_x","queue_id":"q_text","status":"READY","generation_mode":"original_text","public_post_text":"読者が役立つ自然な投稿です。","validator_status":"PASS","account_fit_status":"PASS","internal_leak_status":"PASS","batch_id":"fresh_test","batch_diversity_status":"PASS","topic_coherence_status":"PASS","primary_topic":"work_conditions","topic_confidence":"0.75","structure_variant":"0","hook_topic_match":"True","closing_topic_match":"True","shared_hook_detected":"False","shared_closing_detected":"False","quality_gate_version":"generation_quality_v3"},
    {"account_id":"night_scout","canary_id":"canary_fresh_night_scout_approved_source_clip_x","queue_id":"q_clip","status":"WAITING_REVIEW","media_type":"approved_source_clip","clip_candidate_id":"clip_ns_yt_contract_001","public_post_text":"読者が役立つ自然な投稿です。","account_fit_status":"PASS","validator_status":"PASS","internal_leak_status":"PASS","publisher_media_type":"VIDEO","alignment_status":"PASS","final_alignment_score":"1","main_claim_coverage":"1","unsupported_claim_count":"0","source_copy_similarity":"0","recent_post_similarity":"0","batch_id":"fresh_test","batch_diversity_status":"PASS","topic_coherence_status":"PASS","primary_topic":"work_conditions","topic_confidence":"0.75","structure_variant":"0","hook_topic_match":"True","closing_topic_match":"True","shared_hook_detected":"False","shared_closing_detected":"False","quality_gate_version":"generation_quality_v3"},
]
datasets["queue"][1].update(MEDIA_EVIDENCE)
datasets["source_videos"]=[{"source_video_id":"video_ns_yt_contract_001","source_id":"src_ns_yt_contract_001"}]
datasets["video_clip_candidates"]=[{"clip_id":"clip_ns_yt_contract_001","clip_candidate_id":"clip_ns_yt_contract_001","account_id":"night_scout","source_platform":"youtube","source_video_id":"video_ns_yt_contract_001","rights_status":"owned","public_post_text":"読者が役立つ自然な投稿です。","start_seconds":"0","end_seconds":"8"}]
datasets["media_permissions"]=[{"source_id":"src_ns_yt_contract_001","account_id":"night_scout","rights_status":"owned","permission_status":"approved","evidence_reference":"run","allow_clip_repost":True,"revoked":False}]
datasets["media_assets"]=[{"media_id":"clip_asset","video_clip_id":"clip_ns_yt_contract_001","storage_url":"https://example.invalid/clip.mp4","local_path":"/tmp/clip.mp4"}]
result=build_inventory(datasets)
assert result["total_canaries"] == 12
row=next(item for item in result["canaries"] if item["canary_type"] == "original_text" and item["account_id"] == "night_scout")
assert row["status"] == "READY_FOR_HUMAN_CANARY"
clip=next(item for item in result["canaries"] if item["canary_type"] == "approved_source_clip" and item["account_id"] == "night_scout")
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

# An explicit batch id must prevent an older generated clip from winning.
batch_data = {
    key: []
    for key in (
        "queue",
        "source_posts",
        "source_post_media",
        "media_permissions",
        "source_videos",
        "video_clip_candidates",
        "media_assets",
    )
}

batch_data["queue"] = [
    {
        "account_id": "night_scout",
        "canary_id": "canary_fresh_old_approved_source_clip",
        "queue_id": "q_old_approved_source_clip",
        "status": "WAITING_REVIEW",
        "content_type": "approved_source_clip",
        "clip_candidate_id": "clip_old",
        "public_post_text": "Old generated clip.",
        "batch_id": "fresh_old_batch",
        "created_at": "2026-07-31T00:00:00+00:00",
    },
    {
        "account_id": "night_scout",
        "canary_id": "canary_fresh_target_approved_source_clip",
        "queue_id": "q_target_approved_source_clip",
        "status": "WAITING_REVIEW",
        "content_type": "approved_source_clip",
        "clip_candidate_id": "clip_target",
        "public_post_text": "Target generated clip.",
        "batch_id": "fresh_target_batch",
        "created_at": "2026-07-30T00:00:00+00:00",
    },
]

batch_data["source_videos"] = [
    {
        "source_video_id": "video_old",
        "source_id": "source_old",
    },
    {
        "source_video_id": "video_target",
        "source_id": "source_target",
    },
]

batch_data["video_clip_candidates"] = [
    {
        "clip_id": "clip_old",
        "clip_candidate_id": "clip_old",
        "account_id": "night_scout",
        "source_platform": "youtube",
        "source_video_id": "video_old",
        "rights_status": "owned",
        "start_seconds": "0",
        "end_seconds": "8",
    },
    {
        "clip_id": "clip_target",
        "clip_candidate_id": "clip_target",
        "account_id": "night_scout",
        "source_platform": "youtube",
        "source_video_id": "video_target",
        "rights_status": "owned",
        "start_seconds": "0",
        "end_seconds": "8",
    },
]

batch_data["media_permissions"] = [
    {
        "source_id": "source_old",
        "account_id": "night_scout",
        "rights_status": "owned",
        "permission_status": "approved",
        "evidence_reference": "old",
        "allow_clip_repost": True,
        "revoked": False,
    },
    {
        "source_id": "source_target",
        "account_id": "night_scout",
        "rights_status": "owned",
        "permission_status": "approved",
        "evidence_reference": "target",
        "allow_clip_repost": True,
        "revoked": False,
    },
]

batch_data["media_assets"] = [
    {
        "media_id": "asset_old",
        "video_clip_id": "clip_old",
        "storage_url": "https://example.invalid/old.mp4",
        "local_path": "/tmp/old.mp4",
    },
    {
        "media_id": "asset_target",
        "video_clip_id": "clip_target",
        "storage_url": "https://example.invalid/target.mp4",
        "local_path": "/tmp/target.mp4",
    },
]

batch_result = build_inventory(
    batch_data,
    batch_id="fresh_target_batch",
)

selected_clip = next(
    item
    for item in batch_result["candidates"]
    if item["account_id"] == "night_scout"
    and item["canary_type"] == "approved_source_clip"
)

assert selected_clip["canary_id"] == (
    "canary_fresh_target_approved_source_clip"
)
assert selected_clip["queue_id"] == "q_target_approved_source_clip"
assert batch_result["selected_batch_id"] == "fresh_target_batch"

print("PASS test_live_canary_inventory_contract.py")
