#!/usr/bin/env python3
"""Preflight media assets without downloading, cutting, uploading, or posting."""
from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from media.media_asset_store import collect_media_assets_from_raw_items, preflight_media_assets


def _load_sources() -> list[dict]:
    path = os.path.join(_ROOT, "config", "source_accounts", "production_sources.example.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("sources", [])


def _mock_items(account_id: str) -> list[dict]:
    return [{
        "raw_item_id": "mock_raw_media_001",
        "source_id": f"mock_{account_id}_source",
        "target_account_id": account_id,
        "image_urls": ["https://example.com/mock-image.jpg"],
        "video_urls": ["https://example.com/mock-video.mp4"],
        "rights_status": "unknown",
        "reuse_policy": "reference_only",
    }]


def main() -> int:
    parser = argparse.ArgumentParser(description="media asset preflight")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--input-json", default="")
    args = parser.parse_args()

    sources = _load_sources()
    account_sources = [s for s in sources if args.account_id in s.get("target_account_ids", [])]
    source_map = {s["source_id"]: s for s in account_sources}

    if args.input_json:
        with open(args.input_json, encoding="utf-8") as f:
            raw_items = json.load(f).get("raw_source_items", [])
    else:
        raw_items = _mock_items(args.account_id) if args.mock else []
        if account_sources and raw_items:
            raw_items[0]["source_id"] = account_sources[0]["source_id"]

    assets = collect_media_assets_from_raw_items(raw_items, source_map)
    result = preflight_media_assets(assets, source_map, action="post")
    print(f"[preflight_media_assets] account={args.account_id} dry_run={args.dry_run}")
    print(f"  sources={len(account_sources)} assets={len(assets)} status={result['status']}")
    for reason in result.get("blocked_reasons", [])[:5]:
        print(f"  [BLOCKED] {reason}")
    for warning in result.get("warnings", [])[:5]:
        print(f"  [WARN] {warning}")
    print("  実download/cut/upload/postは実行していません")
    return 0 if result["status"] in {"PASS", "WAITING_REVIEW", "BLOCKED"} else 1


if __name__ == "__main__":
    sys.exit(main())
