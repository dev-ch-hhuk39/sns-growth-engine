#!/usr/bin/env python3
from media_post_validator import validate_media_post

GOOD_TEXT = "配信で伸びない人ほど、最初から面白いことを言おうとしすぎる。\n\nでも初心者の配信で大事なのは、面白さより入りやすさ。\n\n入った瞬間に何を話していいかわからない。\nコメントしても拾われるかわからない。\n常連だけで盛り上がっていて入りづらい。\n\nこの状態だと、初見はすぐ抜ける。\n\nまずは、来てくれてありがとう、今この話をしてるよ、気軽にコメントしてねを自然に言えること。\n\n配信は才能より、入りやすい空気を作れるかが大きい。"

def main() -> int:
    result = validate_media_post({"rights_status": "third_party_reference_only", "permission_status": "approved", "media_url": "https://cdn.example/v.mp4", "media_asset_id": "m", "platform": "threads", "account_id": "liver_manager", "media_type": "video", "duration_seconds": 20, "aspect_ratio": "9:16", "public_post_text": GOOD_TEXT})
    ok = result["status"] == "BLOCKED" and "rights_status_not_approved" in result["blocked_reasons"]
    print(f"  {'PASS' if ok else 'FAIL'} media validator requires approved rights")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
