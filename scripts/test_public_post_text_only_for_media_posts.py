#!/usr/bin/env python3
from media_growth_schemas import build_media_post_queue_item

def main() -> int:
    q = build_media_post_queue_item({"clip_candidate_id": "c", "public_post_text": "公開文", "internal_analysis": "内部", "public_post_validator_status": "PASS"})
    ok = q["text"] == "公開文" and "internal_analysis" not in q
    print(f"  {'PASS' if ok else 'FAIL'} public_post_text only for media posts")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
