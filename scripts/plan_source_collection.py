"""
plan_source_collection.py - source collection plan CLI（Phase 8）

source registryから収集計画を作成する。実収集・実API・scraping・download禁止。

使い方:
  python scripts/plan_source_collection.py --account-id night_scout --source-platform x --content-type text_post --top-n 5 --dry-run --mock
  python scripts/plan_source_collection.py --account-id liver_manager --source-platform youtube_shorts --content-type short_video --top-n 5 --dry-run --mock
  python scripts/plan_source_collection.py --account-id beauty_account --source-platform youtube --content-type video_post --top-n 5 --dry-run --mock
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

from reference.source_registry import (
    load_registry,
    build_collection_plan,
    assess_source_rights,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="source collection plan CLI")
    parser.add_argument("--account-id", default="night_scout")
    parser.add_argument("--source-platform", default="", help="platform絞り込み")
    parser.add_argument("--content-type", default="", help="content_type絞り込み")
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--mock", action="store_true", help="モックモード（fixture使用）")
    parser.add_argument("--output-json", action="store_true")
    parser.add_argument("--registry-path", default="")
    args = parser.parse_args()

    account_id = args.account_id

    print(f"\n=== plan_source_collection: {account_id} ===")
    print(f"  platform      : {args.source_platform or 'all'}")
    print(f"  content_type  : {args.content_type or 'all'}")
    print(f"  top_n         : {args.top_n}")
    print(f"  dry_run       : {args.dry_run}")
    print(f"  mock          : {args.mock}")

    if args.mock:
        fixture_path = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_source_registry.json")
        registry_path = fixture_path
        print(f"  [MOCK] fixture: {fixture_path}")
    else:
        registry_path = args.registry_path or None

    sources = load_registry(registry_path)
    print(f"  total sources loaded: {len(sources)}")

    plan = build_collection_plan(
        sources=sources,
        target_account_id=account_id,
        platform=args.source_platform or None,
        content_type=args.content_type or None,
        top_n=args.top_n,
        dry_run=args.dry_run,
    )

    print(f"\n[COLLECTION PLAN] target={account_id}")
    print(f"  selected_sources: {len(plan['selected_sources'])}")
    print(f"  skipped_sources : {len(plan['skipped_sources'])}")

    for s in plan["selected_sources"]:
        review_flag = " [WAITING_REVIEW]" if s.get("review_required") else ""
        print(
            f"  [OK] {s['source_id']} | {s['source_platform']} | "
            f"{s['collection_method']} | top_n={s['top_n']}{review_flag}"
        )

    for s in plan["skipped_sources"]:
        print(f"  [SKIP] {s['source_id']}: {s.get('skip_reason', [])}")

    print(f"\n[RIGHTS SUMMARY] {plan['rights_summary']}")
    print(f"[MEDIA POLICY]   {plan['media_policy_summary']}")
    print(f"\n[NEXT ACTION] {plan['next_action']}")

    if plan["selected_sources"]:
        print("\n  ⚠️  注意: 実収集はしていません。手動JSON/CSV/URL投入が必要です。")
        print("  ⚠️  実API取得・scraping・外部downloadは禁止です。")

    if args.output_json:
        print("\n[JSON OUTPUT]")
        print(json.dumps(plan, ensure_ascii=False, indent=2))

    print(f"\n=== 完了 (dry_run={args.dry_run}) ===")


if __name__ == "__main__":
    main()
