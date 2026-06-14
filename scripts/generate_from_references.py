#!/usr/bin/env python3
"""
generate_from_references.py - Reference-based Generation CLI（Phase 9）

raw_source_items の上位buzz投稿を元に投稿案を生成する。
実投稿なし。beauty_account は WAITING_REVIEW 固定。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from src.reference.fetchers.base_fetcher import RawSourceItem
from src.reference.buzz_scorer import score_items, filter_top_items
from src.generation.video_reference_generator import VideoReferenceGenerator
from src.video.video_understanding import VideoUnderstanding


def main():
    parser = argparse.ArgumentParser(description="Reference-based Generator")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--source-items-json", help="raw_source_items JSONファイル")
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--generation-mode")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()

    print(f"[generate_from_references] account={args.account_id} platform={args.platform}")

    raw_items: list[RawSourceItem] = []
    if args.source_items_json and os.path.isfile(args.source_items_json):
        with open(args.source_items_json, encoding="utf-8") as f:
            data = json.load(f)
        items_data = data if isinstance(data, list) else data.get("raw_source_items", [])
        raw_items = [RawSourceItem.from_dict(d) for d in items_data]
    elif args.mock:
        sp = "youtube"
        raw_items = [
            RawSourceItem(
                raw_item_id=f"mock_{i:03d}",
                source_id=f"src_{args.account_id}",
                source_platform=sp,
                target_account_id=args.account_id,
                fetch_adapter="mock",
                item_type="video",
                post_url=f"https://youtube.com/mock/{i}",
                title=f"モック動画 #{i+1}",
                text=f"モック参考投稿 #{i+1}",
                like_count=1000 * (i + 1),
                view_count=10000 * (i + 1),
                mock=True,
            )
            for i in range(5)
        ]

    if not raw_items:
        print("[WARN] raw_source_items がありません。--mock または --source-items-json を指定してください。")
        return 0

    scored = score_items(raw_items)
    top = filter_top_items(scored, top_n=args.top_n)
    print(f"[OK] {len(scored)}件中 top {len(top)}件を選択")

    vu = VideoUnderstanding()
    vg = VideoReferenceGenerator()
    all_results = []

    for item in top:
        item_dict = item.to_dict()
        understanding = vu.analyze(
            item_dict,
            account_id=args.account_id,
            target_platform=args.platform,
            mock=args.mock,
        )
        gen_result = vg.generate(
            understanding,
            account_id=args.account_id,
            target_platform=args.platform,
            generation_mode=args.generation_mode or item.recommended_generation_mode or "reference_based_text",
            mock=args.mock,
        )
        all_results.append({
            "source_item": item_dict,
            "understanding": understanding,
            "generation": gen_result,
        })
        print(f"  ✓ {item.title[:50]} → {gen_result['draft_count']}件 draft ({gen_result['status']})")

    output = {
        "account_id": args.account_id,
        "platform": args.platform,
        "mock": args.mock,
        "total_refs": len(top),
        "results": all_results,
    }

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[OK] 保存: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
