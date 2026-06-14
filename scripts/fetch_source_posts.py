#!/usr/bin/env python3
"""
fetch_source_posts.py - Source Posts Fetcher CLI（Phase 9）

指定アカウント/プラットフォームの参考投稿を取得し raw_source_items を出力する。

使い方:
  python scripts/fetch_source_posts.py --account-id night_scout --platform x --mock --dry-run
  python scripts/fetch_source_posts.py --account-id liver_manager --platform youtube --mock --dry-run
  python scripts/fetch_source_posts.py --account-id night_scout --platform x --fetch --confirm-fetch --dry-run

安全方針:
  --fetch なしまたは --confirm-fetch なしなら BLOCKED
  --download なしまたは --confirm-download なしなら download BLOCKED
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# プロジェクトルートをsys.pathへ
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from src.reference.fetchers.fetcher_registry import FetcherRegistry
from src.reference.source_registry import load_sources
from src.reference.buzz_scorer import score_items, filter_top_items


def main():
    parser = argparse.ArgumentParser(description="Source Posts Fetcher")
    parser.add_argument("--account-id", required=True, help="対象アカウントID")
    parser.add_argument("--platform", help="取得プラットフォーム (x/threads/youtube/tiktok)")
    parser.add_argument("--source-id", help="特定のsource_idを指定")
    parser.add_argument("--source-platform", help="source_platform フィルタ")
    parser.add_argument("--collection-method", help="fetch adapter を上書き")
    parser.add_argument("--mock", action="store_true", help="モックデータを返す")
    parser.add_argument("--dry-run", action="store_true", help="ドライラン")
    parser.add_argument("--fetch", action="store_true", help="実取得モードを有効化")
    parser.add_argument("--confirm-fetch", action="store_true", help="実取得の最終確認")
    parser.add_argument("--download", action="store_true", help="downloadモードを有効化")
    parser.add_argument("--confirm-download", action="store_true", help="実downloadの最終確認")
    parser.add_argument("--max-items", type=int, default=10, help="最大取得件数")
    parser.add_argument("--top-n", type=int, default=5, help="buzz top N")
    parser.add_argument("--import-path", help="手動インポートファイルパス")
    parser.add_argument("--output", help="結果を保存するJSONファイルパス")
    parser.add_argument("--quiet", action="store_true", help="サマリーのみ出力")
    args = parser.parse_args()

    # 安全チェック
    confirm_fetch = args.fetch and args.confirm_fetch
    confirm_download = args.download and args.confirm_download

    if args.fetch and not args.confirm_fetch:
        print("[BLOCKED] --fetch を指定しましたが --confirm-fetch がありません。実取得をブロックします。")
        if not args.mock:
            sys.exit(1)

    if args.download and not args.confirm_download:
        print("[BLOCKED] --download を指定しましたが --confirm-download がありません。downloadをブロックします。")

    print(f"[fetch_source_posts] account={args.account_id} platform={args.platform}")
    print(f"  mock={args.mock} dry_run={args.dry_run} confirm_fetch={confirm_fetch}")

    # source 一覧を読み込む
    all_sources = load_sources()
    target_sources = [s for s in all_sources if _matches(s, args)]

    if not target_sources:
        print(f"[WARN] 対象sourceが見つかりませんでした。")
        if args.mock:
            # mock source を作成
            target_sources = [{
                "source_id": f"mock_{args.account_id}_{args.platform or 'any'}",
                "source_platform": args.source_platform or args.platform or "youtube",
                "source_handle": "@mock_handle",
                "source_url": "",
                "collection_method": "manual_json",
                "target_account_ids": [args.account_id],
                "active": True,
                "blocked": False,
                "rights_policy": "reference_only",
                "reuse_policy": "reference_only",
                "media_policy": "do_not_download",
            }]
        else:
            sys.exit(0)

    registry = FetcherRegistry()
    all_items = []
    results = []

    for src in target_sources:
        method = args.collection_method or src.get("collection_method", "manual_json")
        sp = src.get("source_platform", "")
        fetcher = registry.get(method, sp)

        fetch_kwargs = dict(
            target_account_id=args.account_id,
            mock=args.mock,
            dry_run=args.dry_run,
            confirm_fetch=confirm_fetch,
            confirm_download=confirm_download,
            max_items=args.max_items,
        )
        if args.import_path:
            fetch_kwargs["import_path"] = args.import_path

        result = fetcher.fetch(src, **fetch_kwargs)
        results.append(result.to_dict())
        all_items.extend(result.items)

        status_icon = "✓" if result.status == "OK" else "⚠"
        print(f"  {status_icon} [{result.adapter}] {src['source_id']}: {result.status} ({len(result.items)}件) {result.message[:80]}")

    # Buzz scoring
    if all_items:
        scored = score_items(all_items)
        top_items = filter_top_items(scored, top_n=args.top_n)
    else:
        scored = []
        top_items = []

    output_data = {
        "account_id": args.account_id,
        "platform": args.platform,
        "mock": args.mock,
        "dry_run": args.dry_run,
        "confirm_fetch": confirm_fetch,
        "total_fetched": len(all_items),
        "top_buzz_count": len(top_items),
        "fetch_results": results,
        "raw_source_items": [i.to_dict() for i in scored],
        "top_buzz_items": [i.to_dict() for i in top_items],
    }

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        print(f"\n[OK] 結果を保存しました: {args.output}")

    if not args.quiet:
        print(f"\n=== サマリー ===")
        print(f"  取得件数: {len(all_items)}")
        print(f"  buzz top {args.top_n}: {len(top_items)}")
        if top_items:
            print(f"  トップ投稿:")
            for i in top_items[:3]:
                print(f"    - [{i.source_platform}] score={i.buzz_score:.3f} {i.text[:60]}")

    return 0


def _matches(source: dict, args: argparse.Namespace) -> bool:
    if not source.get("active", True):
        return False
    if source.get("blocked", False):
        return False
    if args.account_id not in source.get("target_account_ids", []):
        return False
    if args.source_id and source.get("source_id") != args.source_id:
        return False
    if args.source_platform and source.get("source_platform") != args.source_platform:
        return False
    if args.platform:
        sp = source.get("source_platform", "")
        if sp and sp != args.platform:
            return False
    return True


if __name__ == "__main__":
    sys.exit(main() or 0)
