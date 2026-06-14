#!/usr/bin/env python3
"""
plan_video_reference_posts.py - Video Reference Post Planner CLI（Phase 9）

YouTube/TikTok動画を元に投稿案をプランする。
実download/実cut/実upload禁止。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from src.video.video_understanding import VideoUnderstanding
from src.video.clip_candidate_planner import ClipCandidatePlanner
from src.generation.video_reference_generator import VideoReferenceGenerator


def main():
    parser = argparse.ArgumentParser(description="Video Reference Post Planner")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--source-platform", default="youtube")
    parser.add_argument("--video-url")
    parser.add_argument("--source-id")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()

    print(f"[plan_video_reference_posts] account={args.account_id} platform={args.platform}")
    print(f"  source_platform={args.source_platform} mock={args.mock}")

    if args.account_id == "beauty_account":
        print("  [INFO] beauty_account: WAITING_REVIEW 固定")

    # モックアイテム作成
    item = {
        "source_id": args.source_id or f"src_{args.account_id}",
        "source_platform": args.source_platform,
        "post_url": args.video_url or f"https://youtube.com/watch?v=mock_{args.account_id}",
        "title": f"モック動画タイトル ({args.account_id})",
        "description": "動画の説明文サンプル",
        "transcript": "これはモックtranscriptです。重要なポイントを説明しています。" if args.mock else None,
        "duration_seconds": 180.0,
        "view_count": 15000,
        "like_count": 800,
    }

    vu = VideoUnderstanding()
    understanding = vu.analyze(
        item,
        account_id=args.account_id,
        target_platform=args.platform,
        mock=args.mock,
    )

    cp = ClipCandidatePlanner()
    clip_plan = cp.plan(
        understanding,
        account_id=args.account_id,
        target_platform=args.platform,
        mock=args.mock,
    )

    vg = VideoReferenceGenerator()
    gen_result = vg.generate(
        understanding,
        account_id=args.account_id,
        target_platform=args.platform,
        mock=args.mock,
    )

    print(f"\n=== Video Understanding ===")
    print(f"  status: {understanding['status']}")
    print(f"  has_transcript: {understanding['has_transcript']}")
    print(f"  key_points: {len(understanding.get('key_points', []))}件")
    print(f"  hook_candidates: {len(understanding.get('hook_candidates', []))}件")
    print(f"  clip_candidates: {len(understanding.get('clip_candidates', []))}件")

    print(f"\n=== Clip Plan ===")
    print(f"  status: {clip_plan['status']}")
    print(f"  planned_clips: {clip_plan.get('planned_clips', 0)}")

    print(f"\n=== Generation Result ===")
    print(f"  status: {gen_result['status']}")
    print(f"  draft_count: {gen_result['draft_count']}")

    result = {
        "account_id": args.account_id,
        "platform": args.platform,
        "source_platform": args.source_platform,
        "mock": args.mock,
        "dry_run": args.dry_run,
        "video_understanding": understanding,
        "clip_plan": clip_plan,
        "generation_result": gen_result,
    }

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n[OK] 保存: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
