#!/usr/bin/env python3
from media_post_validator import validate_media_post
from public_post_quality import generate_production_post

def main() -> int:
    common = {
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "media_url": "https://cdn.example/beauty.mp4",
        "media_asset_id": "beauty_media_1",
        "media_type": "video",
        "duration_seconds": 20,
        "aspect_ratio": "9:16",
        "content_type": "approved_source_clip",
        "alignment_status": "PASS",
        "final_alignment_score": 0.91,
        "main_claim_coverage": 1.0,
        "unsupported_claim_count": 0,
        "source_copy_similarity": 0.3,
        "recent_post_similarity": 0.2,
    }
    x = validate_media_post({**common, "platform": "x", "account_id": "liver_manager", "public_post_text": "配信は、初見が入りやすい説明を最初に置くと会話へ参加しやすい。\n\n次の配信では、冒頭の一言だけ変えて反応を見てみてください。"})
    beauty_text = generate_production_post(
        "beauty_account", batch_id="media_validator", content_type="approved_source_clip", attempt=1
    )["public_post_text"]
    beauty = validate_media_post({**common, "platform": "threads", "account_id": "beauty_account", "public_post_text": beauty_text})
    ok = x["status"] == "BLOCKED" and "x_publish_blocked" in x["blocked_reasons"] and beauty["status"] == "PASS"
    print(f"  {'PASS' if ok else 'FAIL'} media validator blocks X and allows gated Beauty media")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
