#!/usr/bin/env python3
"""Test media_assets planning from raw_source_items."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from media.media_asset_store import collect_media_assets_from_raw_items
from storage.pipeline_store import PipelineStore


def main() -> int:
    raw = [{
        "raw_item_id": "raw_001",
        "source_id": "src_test",
        "target_account_id": "night_scout",
        "image_urls": ["https://example.com/a.jpg"],
        "video_urls": ["https://example.com/a.mp4"],
    }]
    sources = {"src_test": {"source_id": "src_test", "rights_policy": "unknown", "reuse_policy": "reference_only", "media_policy": "plan_only"}}
    assets = collect_media_assets_from_raw_items(raw, sources)
    store = PipelineStore(output_dir="output/test_pipeline_runs")
    dry_path = store.save("test_run", "media_assets", assets, dry_run=True)
    checks = [
        ("asset_count=2", len(assets) == 2),
        ("has external_url", all(a.get("external_url") for a in assets)),
        ("dry_run no save path", dry_path.startswith("[DRY_RUN]")),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
