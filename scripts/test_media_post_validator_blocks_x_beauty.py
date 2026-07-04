#!/usr/bin/env python3
from media_post_validator import validate_media_post
from test_media_post_validator_requires_approved_rights import GOOD_TEXT

def main() -> int:
    x = validate_media_post({"rights_status": "approved_creator_clip", "permission_status": "approved", "media_url": "u", "media_asset_id": "m", "platform": "x", "account_id": "liver_manager", "media_type": "video", "duration_seconds": 20, "aspect_ratio": "9:16", "public_post_text": GOOD_TEXT})
    b = validate_media_post({"rights_status": "approved_creator_clip", "permission_status": "approved", "media_url": "u", "media_asset_id": "m", "platform": "threads", "account_id": "beauty_account", "media_type": "video", "duration_seconds": 20, "aspect_ratio": "9:16", "public_post_text": GOOD_TEXT})
    ok = x["status"] == "BLOCKED" and b["status"] == "BLOCKED"
    print(f"  {'PASS' if ok else 'FAIL'} media validator blocks x/beauty")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
