#!/usr/bin/env python3
from media_post_validator import validate_media_post

def main() -> int:
    result = validate_media_post({"rights_status": "approved_creator_clip", "permission_status": "approved", "media_url": "u", "media_asset_id": "m", "platform": "threads", "account_id": "liver_manager", "media_type": "video", "duration_seconds": 20, "aspect_ratio": "9:16", "public_post_text": "今回の切り口は source_url です"})
    ok = result["status"] == "BLOCKED" and "public_post_validator_blocked" in result["blocked_reasons"]
    print(f"  {'PASS' if ok else 'FAIL'} media validator requires public post validator pass")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
