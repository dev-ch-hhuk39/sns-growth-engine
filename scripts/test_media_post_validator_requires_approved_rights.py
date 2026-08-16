#!/usr/bin/env python3
from media_post_validator import validate_media_post

GOOD_TEXT = (
    "コメントが止まると、話題を増やさなきゃって焦るよね。\n\n"
    "でも『今日どうだった？』より、二択の方が初見さんも返しやすい。\n\n"
    "私なら冒頭10分で使う二択を一つだけ用意するかな。"
    "全部変えなくて大丈夫。次の配信で一つだけ試してみてね。"
)

def main() -> int:
    result = validate_media_post({"rights_status": "third_party_reference_only", "permission_status": "approved", "media_url": "https://cdn.example/v.mp4", "media_asset_id": "m", "platform": "threads", "account_id": "liver_manager", "media_type": "video", "duration_seconds": 20, "aspect_ratio": "9:16", "public_post_text": GOOD_TEXT})
    ok = result["status"] == "BLOCKED" and "rights_status_not_approved" in result["blocked_reasons"]
    print(f"  {'PASS' if ok else 'FAIL'} media validator requires approved rights")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
