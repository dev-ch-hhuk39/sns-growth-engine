#!/usr/bin/env python3
"""
generate_weekly_report.py - Weekly Report Generator CLI（Phase 10）

posted_results から週次レポートを生成し、改善提案候補を作る。
自動反映なし。WAITING_REVIEW / PLANNED 止まり。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from src.learning.weekly_report_builder import build_weekly_report, build_markdown_report

JST = timezone(timedelta(hours=9))


def main():
    parser = argparse.ArgumentParser(description="Weekly Report Generator")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--platform")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--posted-results-json",
                        help="posted_results の JSON ファイルパス")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args()

    print(f"[generate_weekly_report] account={args.account_id} days={args.days}")

    posted_results: list[dict] = []
    if args.posted_results_json and os.path.isfile(args.posted_results_json):
        with open(args.posted_results_json, encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                posted_results = data
            else:
                posted_results = data.get("posted_results", [])
    elif args.mock:
        # モックデータ
        now_jst = datetime.now(JST)
        posted_results = [
            {
                "post_id": f"mock_{i:03d}",
                "account_id": args.account_id,
                "platform": args.platform or "threads",
                "posted_at": (now_jst - timedelta(days=i % 7)).isoformat(),
                "content_type": ["text_post", "image_post", "thread_series"][i % 3],
                "generation_type": ["reference_based", "original_hypothesis", "video_clip_reference"][i % 3],
                "generation_mode": ["reference_based_text", "original_hypothesis"][i % 2],
                "source_platform": ["youtube", "x", "tiktok"][i % 3],
                "has_media": i % 2 == 0,
                "has_video": i % 3 == 0,
                "hook_style": ["question", "number", "statement"][i % 3],
                "likes": (i + 1) * 50,
                "impressions": (i + 1) * 800,
                "engagement_rate": 0.03 + i * 0.005,
            }
            for i in range(12)
        ]

    report = build_weekly_report(
        account_id=args.account_id,
        posted_results=posted_results,
        queue_items=[],
        learning_rules=[],
        suggestions=[],
        category_scores=[],
    )

    print(f"[OK] レポート生成完了: {report.get('summary', {}).get('recent_post_count', 0)}件")

    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"[OK] JSON保存: {args.output_json}")

    if args.output_md:
        md_content = build_markdown_report(report)
        with open(args.output_md, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"[OK] Markdown保存: {args.output_md}")

    if not args.output_json and not args.output_md:
        md = build_markdown_report(report)
        print("\n" + md[:1000] + "...")

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
