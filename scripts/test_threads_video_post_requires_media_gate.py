#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from publishers.threads_publisher import ThreadsPublisher
from test_media_post_validator_requires_approved_rights import GOOD_TEXT

def main() -> int:
    result = ThreadsPublisher().publish(GOOD_TEXT, account={"account_id": "liver_manager"}, derivative={}, queue_item={"queue_id": "q", "platform": "threads"}, dry_run=False, media_url="https://cdn.example/v.mp4")
    ok = result.success is False and "ALLOW_MEDIA_POSTS" in result.message
    print(f"  {'PASS' if ok else 'FAIL'} Threads video post requires media gate")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
