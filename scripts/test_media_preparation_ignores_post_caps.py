#!/usr/bin/env python3
"""Preparing an asset must not consume or be blocked by a posting cap."""
from __future__ import annotations

import os

import run_media_production_pipeline as production


def main() -> int:
    text = (
        "配信を始めたばかりの時は、話題を増やすより初見の人が入りやすい空気を整える方が大切。"
        "入室へのお礼と今話している内容を伝えるだけでも、コメントのきっかけは作りやすくなる。"
    )
    rows = {
        "source_videos": [{
            "source_video_id": "sv_1",
            "account_id": "liver_manager",
            "platform": "youtube",
            "canonical_video_url": "https://www.youtube.com/watch?v=abcdefghijk",
            "rights_status": "approved_creator_clip",
            "permission_status": "approved",
        }],
        "video_clip_candidates": [{
            "clip_candidate_id": "clip_1",
            "clip_id": "clip_1",
            "source_video_id": "sv_1",
            "account_id": "liver_manager",
            "clip_status": "READY",
            "transcript_grounded": "true",
            "public_post_text": text,
            "clip_score": 95,
        }],
        "media_assets": [],
        "posted_results": [],
    }
    original_records = production._records
    original_today_posts = production._today_posts
    old_env = {name: os.environ.get(name) for name in production.PREPARE_REQUIRED_ENV}
    try:
        production._records = lambda _client, logical: rows[logical]
        production._today_posts = lambda _rows, _account: [
            {"status": "POSTED", "media_used": "true"},
            {"status": "POSTED", "media_used": "true"},
            {"status": "POSTED", "media_used": "false"},
            {"status": "POSTED", "media_used": "false"},
            {"status": "POSTED", "media_used": "false"},
        ]
        for name in production.PREPARE_REQUIRED_ENV:
            os.environ[name] = "true"
        prepare_plan = production.build_plan(
            apply=True,
            confirm=True,
            client=object(),
            account_id="liver_manager",
            prepare_only=True,
        )
        post_plan = production.build_plan(
            apply=True,
            confirm=True,
            client=object(),
            account_id="liver_manager",
            prepare_only=False,
        )
    finally:
        production._records = original_records
        production._today_posts = original_today_posts
        for name, value in old_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    checks = [
        ("prepare plan remains actionable", prepare_plan["status"] == "PLAN_ONLY"),
        ("prepare plan ignores daily cap", "daily_post_cap_reached" not in prepare_plan["blocked_reasons"]),
        ("prepare plan ignores media cap", "media_daily_post_cap_reached" not in prepare_plan["blocked_reasons"]),
        ("prepare plan can download", prepare_plan["would_download"] is True),
        ("normal posting still enforces daily cap", "daily_post_cap_reached" in post_plan["blocked_reasons"]),
        ("normal posting still enforces media cap", "media_daily_post_cap_reached" in post_plan["blocked_reasons"]),
    ]
    for name, passed in checks:
        print(f"  {'PASS' if passed else 'FAIL'} {name}")
    failed = [name for name, passed in checks if not passed]
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
