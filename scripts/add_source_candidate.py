#!/usr/bin/env python3
"""add_source_candidate.py — ソース候補をJSONファイルに追加する (dry_run=True がデフォルト)

使い方:
  python3 scripts/add_source_candidate.py \
    --source-file config/source_accounts/my_sources.json \
    --source-id src_ns_x_new_001 \
    --platform x \
    --url "https://x.com/example_handle" \
    --handle "@example_handle" \
    --target-account night_scout \
    --collection-method agent_reach \
    [--dry-run]  # デフォルト ON

注意:
  - dry_run=True (デフォルト) では実ファイルを変更しない
  - 実書き込みは --no-dry-run を明示的に指定した場合のみ
  - beauty_account の active 化は別途レビュー必須
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

JST = timezone.utc  # 簡易 UTC; 実運用では zoneinfo.ZoneInfo("Asia/Tokyo")

_VALID_PLATFORMS = {"x", "youtube", "tiktok", "note", "article"}
_VALID_COLLECTION_METHODS = {
    "agent_reach", "yt_dlp", "tiktok_to_ytdlp",
    "youtube_transcript", "browser_export", "json_import", "last30days",
}
_VALID_TARGET_ACCOUNTS = {"night_scout", "liver_manager", "beauty_account"}


def _load_sources(path: str) -> dict:
    if not os.path.isfile(path):
        return {"sources": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_sources(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _build_entry(args: argparse.Namespace) -> dict:
    now = datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S+09:00")
    entry: dict = {
        "source_id": args.source_id,
        "source_name": args.name or f"{args.target_account}候補_{args.platform}_{args.source_id[-6:]}",
        "source_platform": args.platform,
        "source_handle": args.handle or "",
        "source_url": args.url,
        "target_account_ids": [args.target_account],
        "collection_method": args.collection_method,
        "candidate_status": "candidate",
        "source_category": args.category or "unknown",
        "use_cases": ["reference_based"],
        "subject_policy": {"require_transform": True},
        "active": False,
        "fetch_enabled": False,
        "allow_network_fetch": False,
        "allow_download": False,
        "rights_policy": "unknown",
        "reuse_policy": "reference_only",
        "media_policy": "plan_only",
        "max_items_per_run": 10,
        "min_likes": 100,
        "language": "ja",
        "region": "JP",
        "target_generation_modes": ["reference_based"],
        "target_platforms": ["x", "threads"],
        "default_post_type": "text_post",
        "pdca_enabled": False,
        "concept_match_score": None,
        "review_notes": args.review_notes or "候補登録。審査前。",
        "created_at": now,
        "updated_at": now,
    }
    if args.target_account == "beauty_account":
        entry["subject_policy"].update({
            "female_subject_required": True,
            "no_male_scout_talking_head_for_clip": True,
            "beauty_medical_risk_review_required": True,
        })
        entry["allow_cut"] = False
        entry["allow_upload"] = False
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description="ソース候補を追加する (dry_run=True がデフォルト)")
    parser.add_argument("--source-file", required=True, help="対象 JSON ファイルパス")
    parser.add_argument("--source-id", required=True, help="source_id (例: src_ns_x_new_001)")
    parser.add_argument("--platform", required=True, choices=sorted(_VALID_PLATFORMS))
    parser.add_argument("--url", required=True, help="ソース URL")
    parser.add_argument("--handle", default="", help="ハンドル名")
    parser.add_argument("--target-account", required=True, choices=sorted(_VALID_TARGET_ACCOUNTS))
    parser.add_argument("--collection-method", required=True, choices=sorted(_VALID_COLLECTION_METHODS))
    parser.add_argument("--name", default="", help="source_name (省略可)")
    parser.add_argument("--category", default="", help="source_category")
    parser.add_argument("--review-notes", default="", help="review_notes")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--no-dry-run", action="store_true", help="実書き込みを許可")
    args = parser.parse_args()

    dry_run = not args.no_dry_run

    data = _load_sources(args.source_file)
    sources = data.get("sources", [])

    existing_ids = {s.get("source_id") for s in sources if "source_id" in s}
    if args.source_id in existing_ids:
        print(f"[ERROR] source_id='{args.source_id}' は既に存在します")
        return 1

    entry = _build_entry(args)

    mode = "DRY_RUN" if dry_run else "WRITE"
    print(f"[{mode}] 追加予定エントリ:")
    print(json.dumps(entry, ensure_ascii=False, indent=2))

    if dry_run:
        print(f"\n[DRY_RUN] 実ファイルは変更されませんでした。--no-dry-run で実行してください。")
        return 0

    sources.append(entry)
    data["sources"] = sources
    _save_sources(args.source_file, data)
    print(f"\n[WRITE] {args.source_file} に追加しました (合計: {len(sources)} 件)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
