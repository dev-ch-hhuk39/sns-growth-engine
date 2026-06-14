#!/usr/bin/env python3
"""
run_source_to_post_pipeline.py - Source-to-Post Pipeline CLI（Phase 11）

指定sourceから取得 → buzz抽出 → 投稿生成 → preflight → publish plan → PDCA候補

使い方:
  python scripts/run_source_to_post_pipeline.py --account-id night_scout --platform x --mock --dry-run
  python scripts/run_source_to_post_pipeline.py --account-id liver_manager --platform threads --source-platform youtube --mock --dry-run
  python scripts/run_source_to_post_pipeline.py --account-id beauty_account --platform threads --source-platform youtube --mock --dry-run

安全方針:
  --mock / --dry-run がない場合は confirm が必要
  beauty_account は WAITING_REVIEW / BLOCKED 維持
  実投稿なし / 実downloadなし
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from src.orchestrators.source_to_post_orchestrator import run_pipeline


def main():
    parser = argparse.ArgumentParser(description="Source-to-Post Pipeline")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--source-id")
    parser.add_argument("--source-platform")
    parser.add_argument("--generation-mode")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-fetch", action="store_true")
    parser.add_argument("--confirm-download", action="store_true")
    parser.add_argument("--confirm-post", action="store_true")
    parser.add_argument("--max-source-items", type=int, default=10)
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--output")
    args = parser.parse_args()

    print(f"[run_source_to_post_pipeline]")
    print(f"  account={args.account_id} platform={args.platform}")
    print(f"  mock={args.mock} dry_run={args.dry_run}")
    print(f"  confirm_fetch={args.confirm_fetch} confirm_post={args.confirm_post}")

    if args.account_id == "beauty_account":
        print("  [INFO] beauty_account: 結果はWAITING_REVIEW/BLOCKEDになります")

    result = run_pipeline(
        account_id=args.account_id,
        platform=args.platform,
        source_id=args.source_id,
        source_platform=args.source_platform,
        generation_mode=args.generation_mode,
        mock=args.mock,
        dry_run=args.dry_run,
        confirm_fetch=args.confirm_fetch,
        confirm_download=args.confirm_download,
        confirm_post=args.confirm_post,
        max_source_items=args.max_source_items,
        top_n=args.top_n,
    )

    status = result.get("status", "UNKNOWN")
    blocked = result.get("blocked_reasons", [])

    print(f"\n=== パイプライン結果 ===")
    print(f"  run_id: {result['run_id']}")
    print(f"  status: {status}")
    if blocked:
        print(f"  BLOCKED理由:")
        for r in blocked:
            print(f"    - {r}")

    summary = result.get("summary", {})
    print(f"\n  取得件数: {summary.get('fetched_items', 0)}")
    print(f"  buzz top: {summary.get('top_buzz_items', 0)}")
    print(f"  reference_posts: {summary.get('reference_posts', 0)}")
    print(f"  draft_count: {summary.get('draft_count', 0)}")
    print(f"  preflight: {summary.get('preflight_status', 'UNKNOWN')}")
    print(f"  publish_blocked: {summary.get('publish_blocked', True)}")

    safety = result.get("safety", {})
    print(f"\n  安全確認:")
    print(f"    real_fetch={safety.get('real_fetch', False)}")
    print(f"    real_download={safety.get('real_download', False)}")
    print(f"    real_post={safety.get('real_post', False)}")
    print(f"    no_real_post={safety.get('no_real_post', True)}")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n[OK] 結果を保存: {args.output}")

    return 0 if status in ("OK", "WAITING_REVIEW", "BLOCKED") else 1


if __name__ == "__main__":
    sys.exit(main() or 0)
