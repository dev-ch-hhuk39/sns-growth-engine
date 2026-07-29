#!/usr/bin/env python3
from final_production_contracts import canary_source_integrity_report, is_individual_source_post_url

assert is_individual_source_post_url("youtube", "https://www.youtube.com/watch?v=8Xmkojfw90Q")
assert is_individual_source_post_url("tiktok", "https://www.tiktok.com/@user5597696107300/video/7662652624092597522")
assert not is_individual_source_post_url("youtube", "https://www.youtube.com/channel/UCh7IsMrygg8X4hEJe8mUcQw")
datasets = {
    "source_posts": [{"source_post_id": "sp", "source_id": "src", "platform": "youtube", "canonical_post_url": "https://www.youtube.com/watch?v=8Xmkojfw90Q"}],
    "source_post_media": [{"source_post_media_id": "m", "source_post_id": "sp", "canonical_post_url": "https://www.youtube.com/watch?v=8Xmkojfw90Q", "original_media_url": "https://origin.example/video.mp4", "storage_url": "https://res.cloudinary.com/demo/video/upload/x.mp4", "media_index": "0"}],
    "media_assets": [{"media_id": "m", "source_post_id": "sp", "storage_url": "https://res.cloudinary.com/demo/video/upload/x.mp4"}],
}
candidates = [{"account_id": "night_scout", "canary_type": "direct_video", "source_post_id": "sp", "media_asset_id": "m", "media_url": "https://res.cloudinary.com/demo/video/upload/x.mp4", "rights_status": "owned", "permission_status": "approved", "permission_evidence": "system_generated:run"}]
assert canary_source_integrity_report(datasets, candidates)["status"] == "PASS"
datasets["source_posts"][0]["canonical_post_url"] = "https://www.youtube.com/channel/UCh7IsMrygg8X4hEJe8mUcQw"
assert canary_source_integrity_report(datasets, candidates)["status"] == "FAIL"
print("PASS test_canary_source_integrity.py")
