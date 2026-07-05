#!/usr/bin/env python3
from media_growth_schemas import build_media_post_queue_item

def main() -> int:
    q = build_media_post_queue_item({"clip_candidate_id": "c1", "source_video_id": "sv1", "account_id": "liver_manager", "public_post_text": "text", "public_post_validator_status": "PASS"}, "ma1")
    ok = q["clip_candidate_id"] == "c1" and q["source_video_id"] == "sv1" and q["media_required"] == "true"
    print(f"  {'PASS' if ok else 'FAIL'} video post queue includes clip_candidate_id")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
