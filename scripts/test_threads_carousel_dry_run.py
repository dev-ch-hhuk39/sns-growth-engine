#!/usr/bin/env python3
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "src"))
from publishers.threads_publisher import ThreadsPublisher

result = ThreadsPublisher().publish(
    "配信を始めたばかりなら、初見が会話に入れる空気を一つずつ作ることが大切です。",
    account={"account_id": "liver_manager"}, derivative={}, queue_item={"queue_id": "carousel-test"}, dry_run=True,
    media_urls=["https://res.cloudinary.com/example/image/upload/a.jpg", "https://res.cloudinary.com/example/image/upload/b.jpg"],
    media_types=["IMAGE", "IMAGE"],
)
ok = result.success and "media_count=2" in result.message
print(f"{'PASS' if ok else 'FAIL'} Threads carousel dry-run")
raise SystemExit(0 if ok else 1)
