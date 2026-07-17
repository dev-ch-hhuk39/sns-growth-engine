#!/usr/bin/env python3
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "src"))
from acquisition.models import NormalizedMediaItem, NormalizedSourcePost, validate_source_post

media = NormalizedMediaItem("m1", "p1", 0, "image", "https://www.threads.com/@a/post/x", "https://cdn.example/a.jpg", "test")
post = NormalizedSourcePost("p1", "s1", "night_scout", "threads", "https://www.threads.com/@a", "https://www.threads.com/@a/post/x", "x", "safe", "", media_items=(media,))
bad = NormalizedSourcePost("p1", "s1", "night_scout", "threads", "https://www.threads.com/@a", "https://www.threads.com/@a/post/x", "x", "safe", "", media_items=(NormalizedMediaItem("m2", "other", 0, "image", "https://www.threads.com/@a/post/x", "https://cdn.example/a.jpg", "test"),))
checks = {"valid parent accepted": not validate_source_post(post), "cross post media rejected": "cross_post_media_link" in validate_source_post(bad)}
for name, ok in checks.items(): print(f"{'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
