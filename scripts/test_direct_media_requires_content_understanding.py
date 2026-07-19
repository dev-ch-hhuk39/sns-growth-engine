#!/usr/bin/env python3
import run_direct_reference_media_pipeline as pipeline


source = {
    "source_id": "src_1",
    "target_account_id": "night_scout",
    "rights_status": "approved_creator_clip",
    "permission_status": "approved",
    "media_usage_mode": "direct_media_reuse",
}
post = {
    "source_post_id": "post_1",
    "source_id": "src_1",
    "target_account_id": "night_scout",
    "platform": "threads",
    "rights_status": "approved_creator_clip",
    "permission_status": "approved",
}
media = {
    "source_post_media_id": "spm_1",
    "source_post_id": "post_1",
    "media_index": "0",
    "media_type": "image",
    "original_media_url": "https://example.com/image.jpg",
    "cloudinary_status": "UPLOADED",
    "storage_url": "https://res.cloudinary.com/demo/image/upload/a.jpg",
    "media_asset_id": "asset_1",
}
asset = {
    "media_id": "asset_1",
    "reference_post_id": "post_1",
    "original_media_url": media["original_media_url"],
    "storage_url": media["storage_url"],
    "media_type": "image",
}
permission = {
    "source_id": "src_1",
    "allow_download": "true",
    "allow_cloudinary_storage": "true",
    "allow_original_repost": "true",
    "allow_new_caption": "true",
    "usage_mode": "direct_media_reuse",
    "revoked": "false",
}
records = {
    "source_accounts": [source],
    "reference_sources": [],
    "source_posts": [post],
    "source_post_media": [media],
    "media_assets": [asset],
    "media_permissions": [permission],
    "posted_results": [],
    "queue": [],
    "source_media_understanding": [],
}
original = pipeline._records
try:
    pipeline._records = lambda _client, logical: records.get(logical, [])
    blocked, reasons = pipeline.select_direct_candidates(object(), "night_scout")
    records["source_media_understanding"] = [{
        "understanding_id": "smu_spm_1",
        "source_post_media_id": "spm_1",
        "status": "PASS",
        "visual_summary": "店選びの判断基準が書かれた画像",
    }]
    allowed, _ = pipeline.select_direct_candidates(object(), "night_scout")
finally:
    pipeline._records = original

checks = [
    ("missing understanding is blocked", not blocked and any("media_content_understanding_missing" in reason for reason in reasons)),
    ("understood media remains eligible", len(allowed) == 1),
    ("understanding stays attached to exact media", allowed[0][1]["carousel_media"][0]["media_understanding"]["understanding_id"] == "smu_spm_1"),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
