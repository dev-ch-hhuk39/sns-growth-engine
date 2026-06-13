"""
collect_source_account_posts.py - source_account_collector CLI（Phase 7.B）

手動JSON/CSVからソースアカウントの投稿を収集し、reference_postsに変換する。
実API/Scraping禁止。dry-run default。

使い方:
  python scripts/collect_source_account_posts.py \
    --account-id night_scout --source-platform x \
    --input-json tests/fixtures/sample_source_account_posts.json \
    --top-n 5 --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_V2_ROOT, ".env"))
except ImportError:
    pass

from reference.source_account_collector import collect_from_json, collect_from_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="source_account_collector CLI")
    parser.add_argument("--account-id", default="night_scout")
    parser.add_argument("--source-platform", default="x", choices=["x", "threads", "tiktok", "youtube_shorts"])
    parser.add_argument("--source-handle", default="")
    parser.add_argument("--input-json", default="")
    parser.add_argument("--input-csv", default="")
    parser.add_argument("--min-engagement-rate", type=float, default=0.0)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--test-write", action="store_true")
    parser.add_argument("--output-json", action="store_true")
    args = parser.parse_args()

    account_id = args.account_id
    source_platform = args.source_platform
    source_handle = args.source_handle or f"{account_id}_source"

    print(f"\n=== collect_source_account_posts: {account_id} / {source_platform} ===")
    print(f"  source_handle      : {source_handle}")
    print(f"  min_engagement_rate: {args.min_engagement_rate}")
    print(f"  top_n              : {args.top_n}")
    print(f"  dry_run            : {args.dry_run}")

    result: dict | None = None

    if args.input_json:
        path = args.input_json
        if not os.path.isabs(path):
            path = os.path.join(_V2_ROOT, path)
        if not os.path.isfile(path):
            print(f"  [ERROR] input_json が見つかりません: {path}")
            sys.exit(1)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        result = collect_from_json(
            data,
            account_id=account_id,
            source_platform=source_platform,
            source_handle=source_handle,
            min_engagement_rate=args.min_engagement_rate,
            top_n=args.top_n,
        )
    elif args.input_csv:
        path = args.input_csv
        if not os.path.isabs(path):
            path = os.path.join(_V2_ROOT, path)
        if not os.path.isfile(path):
            print(f"  [ERROR] input_csv が見つかりません: {path}")
            sys.exit(1)
        with open(path, encoding="utf-8") as f:
            csv_text = f.read()
        result = collect_from_csv(
            csv_text,
            account_id=account_id,
            source_platform=source_platform,
            source_handle=source_handle,
            min_engagement_rate=args.min_engagement_rate,
            top_n=args.top_n,
        )
    else:
        print("  [WARN] --input-json または --input-csv を指定してください。サンプルデータで実行します。")
        sample = [
            {"id": "001", "text": "サンプル投稿1", "likes": 120, "views": 3000, "reposts": 20, "replies": 5},
            {"id": "002", "text": "サンプル投稿2", "likes": 50, "views": 1000, "reposts": 8, "replies": 2},
        ]
        result = collect_from_json(
            sample,
            account_id=account_id,
            source_platform=source_platform,
            source_handle=source_handle,
            min_engagement_rate=args.min_engagement_rate,
            top_n=args.top_n,
        )

    if result:
        print(f"\n--- 収集結果 ---")
        print(f"  total_collected  : {result['total_collected']}")
        print(f"  selected_count   : {result['selected_count']}")
        avgs = result.get("account_averages", {})
        print(f"  avg_likes        : {avgs.get('avg_likes', 0):.1f}")
        print(f"  avg_views        : {avgs.get('avg_views', 0):.1f}")
        print(f"  avg_er           : {avgs.get('avg_er', 0):.4f}")
        print(f"\n  TOP投稿:")
        for p in result["reference_posts"][:5]:
            buzz = "★BUZZ" if p.get("buzz") else ""
            print(f"    [{p['reference_post_id']}] er={p['engagement_rate']:.4f} {buzz}")
            print(f"      rights={p['rights_status']} status={p['status']}")
            text_preview = p["post_text"][:40].replace("\n", " ")
            print(f"      {text_preview}...")

        if args.test_write:
            print(f"\n--- test-write ---")
            if args.use_sheets:
                try:
                    from config_loader import get_config, get_config_partial
                    from sheets_client import make_client
                    try:
                        cfg = get_config()
                    except ValueError:
                        cfg = get_config_partial()
                    sheets = make_client(cfg, dry_run=False)
                    for p in result["reference_posts"]:
                        sheets.append_row("reference_posts", p)
                    print(f"  [OK] {len(result['reference_posts'])} 件 Sheets書き込み完了")
                except Exception as e:
                    print(f"  [WARN] Sheets書き込みエラー: {e}")
            else:
                print(f"  [MockSheets] {len(result['reference_posts'])} 件のreference_postsを保存（mock）")

        if args.output_json:
            print(f"\n--- JSON出力 ---")
            print(json.dumps(result, ensure_ascii=False, indent=2))

    print(f"\n[DONE] collect_source_account_posts 完了")
    print(f"  実API なし / Scraping なし / 実投稿なし")


if __name__ == "__main__":
    main()
