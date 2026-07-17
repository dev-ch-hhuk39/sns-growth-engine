#!/usr/bin/env python3
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "src"))
from acquisition.threads_public import extract_profile_post_urls, parse_public_post_html

source = {"source_id": "src", "target_account_id": "night_scout", "source_url": "https://www.threads.com/@sample"}
profile = '<a href="/@sample/post/abc123">one</a><a href="/@sample/post/abc123">again</a>'
page = '<meta property="og:description" content="reader-facing source text"><meta property="og:image" content="https://cdn.example/one.jpg"><meta property="og:image" content="https://cdn.example/two.jpg">'
urls = extract_profile_post_urls(profile, source["source_url"], limit=5)
post = parse_public_post_html(source, urls[0], page)
checks = {"deduped profile post link": len(urls) == 1, "carousel images retained": post.media_count == 2,
          "same source post parent": all(item.source_post_id == post.source_post_id for item in post.media_items), "media order stable": [item.media_index for item in post.media_items] == [0, 1]}
for name, ok in checks.items(): print(f"{'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
