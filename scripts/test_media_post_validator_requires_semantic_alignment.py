#!/usr/bin/env python3
from media_post_validator import validate_media_post
from test_media_post_validator_requires_approved_rights import GOOD_TEXT

TEXT = GOOD_TEXT
base = {
    "rights_status": "approved_creator_clip",
    "permission_status": "approved",
    "media_url": "https://cdn.example/clip.mp4",
    "media_asset_id": "asset_1",
    "platform": "threads",
    "account_id": "liver_manager",
    "media_type": "video",
    "duration_seconds": 20,
    "aspect_ratio": "9:16",
    "public_post_text": TEXT,
}
blocked = validate_media_post(base)
passed = validate_media_post({**base, "alignment_status": "PASS", "final_alignment_score": 0.9, "main_claim_coverage": 1, "unsupported_claim_count": 0, "source_copy_similarity": 0.3, "recent_post_similarity": 0.2})
checks = [
    ("missing semantic evidence is blocked", blocked["status"] == "BLOCKED"),
    ("fully aligned media plan passes", passed["status"] == "PASS"),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
failed = [name for name, ok in checks if not ok]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
