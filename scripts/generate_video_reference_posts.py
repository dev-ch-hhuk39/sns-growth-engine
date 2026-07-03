#!/usr/bin/env python3
"""Generate multiple text-only post ideas from video references.

Default is PLAN_ONLY. It uses transcript/clip metadata as reference analysis,
never downloads/cuts/uploads/reposts third-party video.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from public_post_quality import final_public_post_validator, generate_reader_facing_post  # noqa: E402

PATTERNS = [
    "フック抽出ポスト",
    "学び・ノウハウ要約ポスト",
    "失敗パターン指摘ポスト",
    "成功パターン分析ポスト",
    "チェックリスト型ポスト",
    "マネージャー目線ポスト",
    "夜職女性向け置き換えポスト",
    "TikTok LIVE配信者向け置き換えポスト",
    "画像カード用短文",
    "ショート台本"
]


def build_video_posts(video: dict[str, Any], account_id: str, limit: int = 3) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    created = datetime.now(timezone.utc).isoformat()
    for i, pattern in enumerate(PATTERNS[: max(1, min(limit, 10))], 1):
        output = generate_reader_facing_post(account_id, index=i)
        body = str(output["public_post_text"])
        validation = final_public_post_validator(body, account_id)
        if validation["status"] != "PASS":
            continue
        rows.append({
            "draft_id": f"video_ref_{account_id}_{i:02d}",
            "account_id": account_id,
            "platform": "threads",
            "text": body,
            "status": "WAITING_REVIEW",
            "source_video_url": video.get("video_url", ""),
            "generation_mode": "video_reference_multi_post",
            "media_strategy": "none",
            "rights_status": "reference_only",
            "can_reuse_media": "false",
            "created_at": created,
            "analysis_status": "stored_separately_not_public",
            "template_pattern": pattern,
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="generate text-only ideas from video references")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--account-id", default="all", choices=["all", "night_scout", "liver_manager", "beauty_account"])
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()
    if args.account_id == "beauty_account":
        print(json.dumps({"status": "BLOCKED", "reason": "beauty_account is not enabled"}, ensure_ascii=False))
        return 1
    accounts = ["night_scout", "liver_manager"] if args.account_id == "all" else [args.account_id]
    videos = [{"title": "sample video reference", "video_url": "reference_only://sample"}]
    rows = []
    for account in accounts:
        rows.extend(build_video_posts(videos[0], account, args.limit))
    print(json.dumps({
        "status": "PLAN_ONLY",
        "account_id": args.account_id,
        "generated_count": len(rows),
        "candidate_status": "WAITING_REVIEW",
        "reference_only": True,
        "download": False,
        "cut": False,
        "upload": False,
        "repost": False,
        "rows": rows,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
