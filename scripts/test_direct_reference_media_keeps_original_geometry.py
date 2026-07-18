#!/usr/bin/env python3
"""Direct approved originals are not rejected by generated-clip geometry."""
from media_post_validator import validate_media_post
from test_media_post_validator_requires_approved_rights import GOOD_TEXT


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
    })
    checks = [
        ("approved original media permits supported landscape geometry", direct["status"] == "PASS"),
        ("generated clip keeps strict duration guard", "duration_out_of_range" in generated["blocked_reasons"]),
        ("generated clip keeps strict aspect guard", "aspect_ratio_not_9_16" in generated["blocked_reasons"]),
    ]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    failed = [name for name, ok in checks if not ok]
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
