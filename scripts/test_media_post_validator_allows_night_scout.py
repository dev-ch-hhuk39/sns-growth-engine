#!/usr/bin/env python3
from media_post_validator import validate_media_post

TEXT = (
    "これからキャバを始める子は、時給だけで店を決めない方がいい。\n\n"
    "客層、ノルマ、出勤のしやすさ、担当へ相談できるか。"
    "条件を並べないと、入ってから続けにくいことって結構ある。\n\n"
    "僕なら、無理なく続けられる店か体入前に見るんだよね。"
)

result = validate_media_post({
    "rights_status": "approved_creator_clip",
    "permission_status": "approved",
    "media_url": "https://cdn.example/night.mp4",
    "media_asset_id": "night_asset",
    "platform": "threads",
    "account_id": "night_scout",
    "media_type": "video",
    "duration_seconds": 20,
    "aspect_ratio": "9:16",
    "public_post_text": TEXT,
    "alignment_status": "PASS",
    "final_alignment_score": 0.91,
    "main_claim_coverage": 1.0,
    "unsupported_claim_count": 0,
    "source_copy_similarity": 0.3,
    "recent_post_similarity": 0.2,
})
ok = result["status"] == "PASS"
print(f"  {'PASS' if ok else 'FAIL'} night_scout approved media post passes validator")
print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
raise SystemExit(0 if ok else 1)
