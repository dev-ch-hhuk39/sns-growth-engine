#!/usr/bin/env python3
"""
generate_original_hypothesis_posts.py - Original Hypothesis Post Generator CLI（Phase 10）

参考投稿なしで仮説ベースの投稿案を生成する。
beauty_account は WAITING_REVIEW 固定。実投稿なし。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from src.generation.original_hypothesis_generator import OriginalHypothesisGenerator


def main():
    parser = argparse.ArgumentParser(description="Original Hypothesis Post Generator")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--post-type", default="text_post",
                        choices=["text_post", "image_post", "thread_series"])
    parser.add_argument("--topic", default="")
    parser.add_argument("--hypothesis", default="")
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()

    print(f"[generate_original_hypothesis_posts]")
    print(f"  account={args.account_id} platform={args.platform} type={args.post_type}")
    print(f"  mock={args.mock} dry_run={args.dry_run}")

    if args.account_id == "beauty_account":
        print("  [INFO] beauty_account: 結果はWAITING_REVIEW固定")

    gen = OriginalHypothesisGenerator()
    result = gen.generate(
        account_id=args.account_id,
        platform=args.platform,
        post_type=args.post_type,
        topic=args.topic,
        hypothesis=args.hypothesis,
        count=args.count,
        mock=args.mock,
        dry_run=args.dry_run,
    )

    print(f"\n=== 生成結果 ===")
    print(f"  job_id: {result['job_id']}")
    print(f"  status: {result['status']}")
    print(f"  draft_count: {result['draft_count']}")
    print(f"  is_beauty: {result['is_beauty']}")

    safety = result.get("safety_check", {})
    if safety:
        print(f"  safety_check: passed={safety.get('passed')}")

    for i, draft in enumerate(result.get("drafts", [])[:3]):
        print(f"\n  draft #{i+1}:")
        if "text" in draft:
            print(f"    text: {draft['text'][:80]}...")
        elif "thread_posts" in draft:
            print(f"    thread_posts: {draft['post_count']}件")
        print(f"    status: {draft['status']}")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n[OK] 保存: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
