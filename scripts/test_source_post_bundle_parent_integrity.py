#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.models import SourceMediaItem, SourcePostBundle, validate_source_post


def bundle(media_parent: str) -> SourcePostBundle:
    return SourcePostBundle(
        source_post_id="sp_1",
        source_id="source_1",
        target_account_id="night_scout",
        platform="threads",
        profile_url="https://www.threads.com/@example",
        canonical_post_url="https://www.threads.com/@example/post/abc",
        external_post_id="abc",
        original_post_text="店選びでは条件だけでなく続けやすさも確認する。",
        published_at="",
        media_items=(SourceMediaItem(
            source_post_media_id="spm_1",
            source_post_id=media_parent,
            media_index=0,
            media_type="image",
            canonical_post_url="https://www.threads.com/@example/post/abc",
            original_media_url="https://cdn.example/image.jpg",
            resolver_backend="fixture",
        ),),
    )


good = validate_source_post(bundle("sp_1"))
bad = validate_source_post(bundle("sp_other"))
checks = [
    ("same-post media bundle passes", "cross_post_media_link" not in good),
    ("cross-post media bundle is blocked", "cross_post_media_link" in bad),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
failed = [name for name, ok in checks if not ok]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
