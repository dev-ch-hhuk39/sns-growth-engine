#!/usr/bin/env python3
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.enrichment import extract_threads_comments

source = "配信の入口を整える話"
payload = {
    "post": {"id": "post1", "text": source, "user": {"username": "owner"}},
    "replies": [
        {"id": "reply1", "text": "最初の一言があると入りやすいです", "user": {"username": "viewer1"}, "like_count": 3},
        {"id": "reply1", "text": "最初の一言があると入りやすいです", "user": {"username": "viewer1"}, "like_count": 3},
    ],
}
html = f"<html><script type='application/json'>{json.dumps(payload, ensure_ascii=False)}</script></html>"
rows = extract_threads_comments(html, source, limit=10)
checks = [
    ("source post body is not misclassified as a reply", all(row["text"] != source for row in rows)),
    ("duplicate reply objects are deduplicated", len(rows) == 1),
    ("reply remains linked content only", rows[0]["comment_id"] == "reply1" if rows else False),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
failed = [name for name, ok in checks if not ok]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
