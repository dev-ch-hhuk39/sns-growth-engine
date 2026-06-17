#!/usr/bin/env python3
"""Plan media downloads; real downloads require --download --confirm-download."""
from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from media.media_downloader import plan_media_downloads


def _load_sources(account_id: str) -> list[dict]:
    path = os.path.join(_ROOT, "config", "source_accounts", "production_sources.example.json")
    with open(path, encoding="utf-8") as f:
        return [s for s in json.load(f).get("sources", []) if account_id in s.get("target_account_ids", [])]


def main() -> int:
    parser = argparse.ArgumentParser(description="download media assets")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--confirm-download", action="store_true")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()

    sources = _load_sources(args.account_id)[:args.limit]
    pairs = [(s, s.get("source_url", "")) for s in sources if s.get("source_url")]
    if args.mock and not pairs:
        pairs = [({
            "source_id": f"mock_{args.account_id}",
            "candidate_status": "candidate",
            "rights_policy": "unknown",
            "reuse_policy": "reference_only",
            "media_policy": "plan_only",
        }, "https://example.com/mock-video.mp4")]

    result = plan_media_downloads(
        pairs,
        download=args.download,
        confirm_download=args.confirm_download,
        dry_run=args.dry_run,
    )
    print(f"[download_media_assets] account={args.account_id} status={result['status']}")
    print(f"  dry_run={args.dry_run} download={args.download} confirm_download={args.confirm_download}")
    for reason in result.get("blocked_reasons", [])[:8]:
        print(f"  [BLOCKED] {reason}")
    print("  実downloadは実行していません")
    if args.download and not args.confirm_download:
        return 1
    return 0 if result["status"] in {"DRY_RUN", "BLOCKED", "READY"} else 1


if __name__ == "__main__":
    sys.exit(main())
