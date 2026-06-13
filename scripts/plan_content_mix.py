"""
plan_content_mix.py - content_mix_planner CLI（Phase 7.A）

アカウント・プラットフォームに応じた投稿種別ミックスプランを生成する。
デフォルトは dry-run。実投稿なし。

使い方:
  python scripts/plan_content_mix.py --account-id night_scout --platform x --count 10 --seed 42 --dry-run
  python scripts/plan_content_mix.py --account-id liver_manager --platform threads --count 10 --dry-run
  python scripts/plan_content_mix.py --account-id beauty_account --platform x --count 5 --dry-run

禁止事項:
  - 実SNS投稿
  - READY/POSTED 化
  - beauty_account の実投稿
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

from generation.content_mix_planner import plan_content_mix


def main() -> None:
    parser = argparse.ArgumentParser(description="content_mix_planner CLI")
    parser.add_argument("--account-id", default="night_scout")
    parser.add_argument("--platform", default="x", choices=["x", "threads"])
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--test-write", action="store_true")
    parser.add_argument("--date", default="")
    parser.add_argument("--force-mode", default=None, help="single_post|thread_series|reference_based|video_clip_reference")
    parser.add_argument("--output-json", action="store_true")
    args = parser.parse_args()

    account_id = args.account_id
    platform = args.platform
    count = max(1, args.count)

    print(f"\n=== plan_content_mix: {account_id} / {platform} ===")
    print(f"  count      : {count}")
    print(f"  seed       : {args.seed}")
    print(f"  dry_run    : {args.dry_run}")
    print(f"  use_sheets : {args.use_sheets}")
    print(f"  test_write : {args.test_write}")
    if args.date:
        print(f"  date       : {args.date}")
    if args.force_mode:
        print(f"  force_mode : {args.force_mode}")

    plan = plan_content_mix(
        account_id=account_id,
        platform=platform,
        count=count,
        seed=args.seed,
        force_mode=args.force_mode,
    )

    print(f"\n--- プラン結果 ---")
    print(f"  plan_id         : {plan['plan_id']}")
    print(f"  safety_status   : {plan['safety_status']}")
    for note in plan["safety_notes"]:
        print(f"  [NOTE] {note}")
    print(f"  generated_jobs  : {plan['generated_jobs_count']}")
    print(f"\n  比率設定:")
    for k, v in plan["ratios_config"].items():
        if v > 0:
            print(f"    {k}: {v}")
    print(f"\n  選択結果:")
    for k, v in sorted(plan["ratio_summary"].items(), key=lambda x: -x[1]):
        print(f"    {k}: {v}件")
    print(f"\n  アイテム:")
    for item in plan["items"]:
        print(f"    [{item['plan_item_id']}] {item['content_type']} → {item['status']}")

    if args.test_write and args.use_sheets:
        print("\n--- Sheets test-write (content_mix_plans) ---")
        try:
            from config_loader import get_config, get_config_partial
            from sheets_client import make_client
            try:
                cfg = get_config()
            except ValueError:
                cfg = get_config_partial()
            sheets = make_client(cfg, dry_run=False)
            for item in plan["items"]:
                sheets.append_row("content_mix_plans", item)
            print(f"  [OK] {len(plan['items'])} 件書き込み完了")
        except Exception as e:
            print(f"  [WARN] Sheets書き込みエラー（dry-run継続）: {e}")
    elif args.test_write:
        print("\n--- MockSheets test-write ---")
        print(f"  [MockSheets] {len(plan['items'])} 件のプランアイテムを保存（mock）")

    if args.output_json:
        print(f"\n--- JSON出力 ---")
        print(json.dumps(plan, ensure_ascii=False, indent=2))

    print(f"\n[DONE] plan_content_mix 完了")
    print(f"  実投稿なし / X APIなし / Threads APIなし")


if __name__ == "__main__":
    main()
