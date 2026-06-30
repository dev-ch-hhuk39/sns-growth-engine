#!/usr/bin/env python3
"""Seed manual reference posts from the source registry without fetching.

This completes the first production-loop bridge after the source registry is
seeded to Sheets. It creates small REFERENCE_ONLY rows in source_account_posts
from source metadata only. It never fetches a post, downloads media, calls X, or
creates postable queue rows.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_SOURCE_FILE = ROOT / "config/source_accounts/default_sources.json"
ALLOWED_ACCOUNTS = {"night_scout", "liver_manager"}
EXCLUDED_PLATFORMS = {"x", "query"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_targets(source: dict[str, Any]) -> list[str]:
    ids = source.get("target_account_ids")
    if isinstance(ids, list):
        return [str(v) for v in ids]
    one = source.get("target_account_id")
    return [str(one)] if one else []


def _safe_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_")[:80]


def _url(source: dict[str, Any]) -> str:
    return str(source.get("canonical_url") or source.get("source_url") or source.get("post_url") or "").strip()


def _handle(source: dict[str, Any]) -> str:
    return str(
        source.get("source_handle")
        or source.get("author_handle")
        or source.get("handle")
        or source.get("source_name")
        or ""
    ).strip()


def _theme_text(source: dict[str, Any], account_id: str) -> str:
    platform = str(source.get("source_platform", "reference"))
    category = source.get("source_category") or source.get("category") or "reference"
    if isinstance(category, list):
        category = "/".join(str(v) for v in category)
    use_cases = source.get("use_cases") or []
    if isinstance(use_cases, list):
        use_case_text = " / ".join(str(v) for v in use_cases[:3])
    else:
        use_case_text = str(use_cases)

    if account_id == "night_scout":
        angle = "夜職女性の不安・働き方・相談導線に変換できる構成"
        prompt = "キャバ嬢/夜職女性が保存したくなる注意点と、強すぎない相談CTAの参考テーマ。"
    else:
        angle = "ライバー候補者の継続・配信ノウハウ・マネージャー信頼形成に変換できる構成"
        prompt = "TikTok LIVE/Pococha配信者が実務で使える改善ヒントと、自然な相談CTAの参考テーマ。"

    return (
        f"参考テーマ: {platform} / {category}\n"
        f"狙い: {angle}\n"
        f"利用観点: {use_case_text or 'structure_reference / hook_reference'}\n"
        f"生成メモ: {prompt}\n"
        "注意: 元URLの本文・画像・動画はコピーせず、構造と切り口だけを変換して使う。"
    )


def load_sources(source_file: Path) -> list[dict[str, Any]]:
    data = json.loads(source_file.read_text(encoding="utf-8"))
    return data.get("sources", data if isinstance(data, list) else [])


def build_reference_posts(
    sources: list[dict[str, Any]],
    *,
    account_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for source in sources:
        if account_id not in _as_targets(source):
            continue
        platform = str(source.get("source_platform", "")).strip().lower()
        if platform in EXCLUDED_PLATFORMS:
            continue
        if not _url(source):
            continue
        if str(source.get("fetch_enabled", "")).lower() == "true":
            continue
        if "beauty_account" in _as_targets(source):
            continue
        selected.append(source)

    selected.sort(key=lambda s: (
        str(s.get("active", "")).lower() != "true",
        int(str(s.get("priority", "50") or "50")),
        str(s.get("source_id", "")),
    ))

    created_at = now_iso()
    rows: list[dict[str, Any]] = []
    for source in selected[:limit]:
        source_id = str(source.get("source_id", ""))
        platform = str(source.get("source_platform", ""))
        post_id = f"manualref_{_safe_id(source_id)}"
        url = _url(source)
        text = _theme_text(source, account_id)
        rows.append({
            "post_id": post_id,
            "source_id": source_id,
            "account_id": account_id,
            "source_platform": platform,
            "source_handle": _handle(source),
            "post_text": text,
            "media_urls": "",
            "likes": "0",
            "reposts": "0",
            "replies": "0",
            "views": "0",
            "bookmarks": "0",
            "engagement_rate": "0",
            "buzz": "0",
            "rights_policy": "reference_only",
            "reuse_policy": "reference_only",
            "status": "WAITING_SCORE",
            "collected_at": created_at,
            "post_url": url,
            "use_status": "REFERENCE_ONLY",
            "rights_status": "reference_only",
            "can_reuse_media": "false",
        })
    return rows


def _append_source_account_posts(client: Any, rows: list[dict[str, Any]]) -> dict[str, int]:
    ws = client._ws("source_account_posts")
    headers = ws.row_values(1)
    existing_ids = {str(r.get("post_id", "")) for r in ws.get_all_records()}
    added = skipped = 0
    for row in rows:
        if str(row.get("post_id", "")) in existing_ids:
            skipped += 1
            continue
        ws.append_row([str(row.get(h, "")) for h in headers], value_input_option="USER_ENTERED")
        existing_ids.add(str(row.get("post_id", "")))
        added += 1
    return {"added": added, "skipped": skipped}


def main() -> int:
    parser = argparse.ArgumentParser(description="seed manual reference posts from safe source registry rows")
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager", "all"])
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--source-file", default=str(DEFAULT_SOURCE_FILE))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-seed", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    source_file = Path(args.source_file)
    if not source_file.is_absolute():
        source_file = ROOT / source_file
    sources = load_sources(source_file)
    accounts = sorted(ALLOWED_ACCOUNTS if args.account_id == "all" else {args.account_id})
    rows: list[dict[str, Any]] = []
    for account in accounts:
        rows.extend(build_reference_posts(sources, account_id=account, limit=args.limit))

    summary = {
        "status": "PLAN_ONLY",
        "account_id": args.account_id,
        "requested_accounts": accounts,
        "planned_count": len(rows),
        "by_account": {a: sum(1 for r in rows if r["account_id"] == a) for a in accounts},
        "source": str(source_file.relative_to(ROOT)) if str(source_file).startswith(str(ROOT)) else str(source_file),
        "safety": {
            "real_fetch": False,
            "x_fetch": False,
            "media_download": False,
            "auto_post": False,
            "use_status": "REFERENCE_ONLY",
            "can_reuse_media": False,
        },
        "post_ids": [r["post_id"] for r in rows],
    }

    if not args.apply:
        print(json.dumps(summary, ensure_ascii=False, indent=None if args.json else 2))
        return 0
    if not args.confirm_seed:
        print(json.dumps({**summary, "status": "BLOCKED", "reason": "--apply requires --confirm-seed"}, ensure_ascii=False))
        return 1

    from config_loader import get_config
    from sheets_client import SheetsClient

    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    result = _append_source_account_posts(client, rows)
    print(json.dumps({**summary, "status": "SEEDED", **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
