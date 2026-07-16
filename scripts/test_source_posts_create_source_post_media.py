#!/usr/bin/env python3
"""Every discovered media post produces a deterministic ingest handoff row."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location("discover_posts", ROOT / "scripts/discover_approved_source_posts.py")
assert spec and spec.loader
module = module_from_spec(spec)
spec.loader.exec_module(module)

source = {
    "source_id": "src_lm_yt_user_001",
    "target_account_id": "liver_manager",
    "source_platform": "youtube",
}
item = {
    "external_post_id": "abc123def45",
    "canonical_post_url": "https://www.youtube.com/watch?v=abc123def45",
    "original_post_text": "Safe test description",
    "duration_seconds": "31",
    "media_count": "1",
    "media_type": "video",
}
post = module.source_post_row(source, item)
media = module.source_post_media_row(post)

checks = {
    "post canonical URL": post["canonical_post_url"] == item["canonical_post_url"],
    "media links post": media["source_post_id"] == post["source_post_id"],
    "deterministic media id": media["source_post_media_id"] == f"spm_{post['source_post_id']}_0",
    "pending download": media["download_status"] == "PENDING",
    "pending cloudinary": media["cloudinary_status"] == "PENDING",
    "approved reuse": media["reuse_status"] == "APPROVED",
    "canonical ingest URL": media["canonical_post_url"] == post["canonical_post_url"],
}
for name, ok in checks.items():
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {sum(checks.values())} / FAIL: {len(checks) - sum(checks.values())}")
raise SystemExit(0 if all(checks.values()) else 1)
