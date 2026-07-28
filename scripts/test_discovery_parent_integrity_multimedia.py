#!/usr/bin/env python3
"""Discovery accepts only individual posts and preserves every media parent/order."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location("discovery", ROOT / "scripts" / "discover_approved_source_posts.py")
assert spec and spec.loader
module = module_from_spec(spec)
spec.loader.exec_module(module)

assert not module.is_individual_post_url("youtube", "https://youtube.com/channel/UC123")
assert not module.is_individual_post_url("tiktok", "https://www.tiktok.com/@creator")
assert not module.is_individual_post_url("threads", "https://www.threads.net/@creator")
assert module.is_individual_post_url("youtube", "https://youtube.com/watch?v=abcdefghijk")
assert module.is_individual_post_url("tiktok", "https://www.tiktok.com/@creator/video/123")
assert module.is_individual_post_url("threads", "https://www.threads.net/@creator/post/abc")

for account_id in ("night_scout", "liver_manager"):
    source = {"source_id": f"src_{account_id}", "target_account_id": account_id, "source_platform": "threads"}
    item = {"external_post_id": "post1", "canonical_post_url": "https://www.threads.net/@creator/post/abc", "original_post_text": "safe", "media_items": [
        {"url": "https://cdn.example/one.jpg", "media_type": "image"},
        {"url": "https://cdn.example/two.mp4", "media_type": "video", "duration_seconds": "14"},
        {"url": "https://cdn.example/three.jpg", "media_type": "image"},
    ]}
    post = module.source_post_row(source, item)
    media = module.source_post_media_rows(post)
    assert post["media_count"] == "3"
    assert [row["media_index"] for row in media] == ["0", "1", "2"]
    assert all(row["source_post_id"] == post["source_post_id"] for row in media)
    assert all(row["canonical_post_url"] == post["canonical_post_url"] for row in media)

print("PASS test_discovery_parent_integrity_multimedia.py")
