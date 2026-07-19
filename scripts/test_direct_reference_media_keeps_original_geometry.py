#!/usr/bin/env python3
"""Direct approved originals are not rejected by generated-clip geometry."""
from media_post_validator import validate_media_post
from test_media_post_validator_requires_approved_rights import GOOD_TEXT

ALIGNMENT = {
    "alignment_status": "PASS",
    "final_alignment_score": 0.9,
    "main_claim_coverage": 1.0,
    "unsupported_claim_count": 0,
    "source_copy_similarity": 0.25,
    "recent_post_similarity": 0.2,
}


def main() -> int:
    direct = validate_media_post({
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "media_url": "https://res.cloudinary.example/original.mp4",
        "media_asset_id": "asset-direct",
        "platform": "threads",
        "account_id": "liver_manager",
        "media_type": "video",
        "duration_seconds": 96,
        "aspect_ratio": "16:9",
        "media_origin": "direct_reference",
        "public_post_text": GOOD_TEXT,
        **ALIGNMENT,
    })
    generated = validate_media_post({
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "media_url": "https://res.cloudinary.example/clip.mp4",
        "media_asset_id": "asset-clip",
        "platform": "threads",
        "account_id": "liver_manager",
        "media_type": "video",
        "duration_seconds": 96,
        "aspect_ratio": "16:9",
        "media_origin": "generated_clip",
        "public_post_text": GOOD_TEXT,
        **ALIGNMENT,
    })
    unknown_duration = validate_media_post({
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "media_url": "https://res.cloudinary.example/original-without-duration.mp4",
        "media_asset_id": "asset-direct-unknown-duration",
        "platform": "threads",
        "account_id": "liver_manager",
        "media_type": "video",
        "duration_seconds": "",
        "aspect_ratio": "",
        "media_origin": "direct_reference",
        "public_post_text": GOOD_TEXT,
        **ALIGNMENT,
    })
    checks = [
        ("approved original media permits supported landscape geometry", direct["status"] == "PASS"),
        ("generated clip keeps strict duration guard", "duration_out_of_range" in generated["blocked_reasons"]),
        ("generated clip keeps strict aspect guard", "aspect_ratio_not_9_16" in generated["blocked_reasons"]),
        ("approved original may proceed when old metadata lacks duration", unknown_duration["status"] == "PASS"),
    ]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    failed = [name for name, ok in checks if not ok]
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
