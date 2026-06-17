#!/usr/bin/env python3
"""Test media preflight blocks unapproved/unknown rights media."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from media.media_asset_store import build_media_asset, preflight_media_assets


def main() -> int:
    source = {
        "source_id": "src_test",
        "candidate_status": "candidate",
        "rights_policy": "unknown",
        "reuse_policy": "reference_only",
        "media_policy": "plan_only",
    }
    asset = build_media_asset(
        account_id="night_scout",
        source_id="src_test",
        raw_item_id="raw_001",
        media_type="video",
        external_url="https://example.com/a.mp4",
    )
    result = preflight_media_assets([asset], {"src_test": source}, action="post")
    checks = [
        ("preflight BLOCKED", result["status"] == "BLOCKED"),
        ("blocked_reasonsあり", bool(result["blocked_reasons"])),
        ("asset_count=1", result["asset_count"] == 1),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
