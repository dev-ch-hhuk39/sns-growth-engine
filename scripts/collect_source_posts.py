#!/usr/bin/env python3
"""Plan/apply safe reference-source collection.

Only fetch_enabled=true sources are eligible. manual_only sources and X sources
are skipped by default. This script does not download media.
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
SOURCES_FILE = ROOT / "config/source_accounts/default_sources.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_true(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def load_sources_from_file() -> list[dict[str, Any]]:
    data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    return data.get("sources", data if isinstance(data, list) else [])


def select_sources(sources: list[dict[str, Any]], *, account_id: str, platform: str, include_x: bool = False) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for src in sources:
        targets = src.get("target_account_ids") or [src.get("target_account_id") or src.get("account_id")]
        src_platform = str(src.get("source_platform") or src.get("platform") or "").lower()
        reason = ""
        if account_id != "all" and account_id not in targets:
            reason = "account_not_targeted"
        elif platform != "all" and src_platform != platform:
            reason = "platform_mismatch"
        elif not is_true(src.get("fetch_enabled", False)):
            reason = "fetch_enabled_false"
        elif is_true(src.get("manual_only", False)) or str(src.get("collection_method", "")).lower() in {"manual_url", "manual_json"}:
            reason = "manual_only"
        elif src_platform == "x" and not include_x:
            reason = "x_disabled_by_default"
        if reason:
            skipped.append({"source_id": src.get("source_id", ""), "url": src.get("url") or src.get("source_url", ""), "reason": reason})
        else:
            selected.append(src)
    return selected, skipped


def normalize_source(src: dict[str, Any]) -> dict[str, Any]:
    url = src.get("url") or src.get("source_url") or src.get("canonical_url") or ""
    return {
        "reference_post_id": f"ref_{src.get('source_id', 'source')}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "source_id": src.get("source_id", ""),
        "account_id": ",".join(src.get("target_account_ids") or [src.get("target_account_id", "")]),
        "platform": src.get("source_platform", ""),
        "post_url": url,
        "author_handle": src.get("handle", ""),
        "posted_at": "",
        "text": "",
        "thumbnail_url": "",
        "engagement_json": "{}",
        "raw_json": json.dumps({"url": url, "source_id": src.get("source_id", "")}, ensure_ascii=False),
        "use_status": "REFERENCE_ONLY",
        "can_reuse_media": "false",
        "created_at": now_iso(),
    }


def _append_many(client, logical: str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    ws = client._ws(logical)
    headers = ws.row_values(1)
    ws.append_rows([["" if row.get(h) is None else str(row.get(h, "")) for h in headers] for row in rows], value_input_option="USER_ENTERED")
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="collect reference source posts safely")
    parser.add_argument("--platform", default="all", choices=["threads", "x", "youtube", "tiktok", "all"])
    parser.add_argument("--account-id", default="all", choices=["all", "night_scout", "liver_manager", "beauty_account"])
    parser.add_argument("--include-x", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-collect", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()

    if args.account_id == "beauty_account":
        print(json.dumps({"status": "BLOCKED", "reason": "beauty_account collection is disabled"}, ensure_ascii=False))
        return 1
    sources = load_sources_from_file()
    selected, skipped = select_sources(sources, account_id=args.account_id, platform=args.platform, include_x=args.include_x)
    rows = [normalize_source(src) for src in selected]
    plan = {
        "status": "PLAN_ONLY" if not args.apply else "WILL_APPLY",
        "selected_count": len(selected),
        "skipped_count": len(skipped),
        "media_download": False,
        "x_enabled": bool(args.include_x),
        "rows": rows[:10],
        "skipped": skipped[:20],
    }
    if not args.apply:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    if not args.confirm_collect or not args.use_sheets:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-collect --use-sheets"}, ensure_ascii=False))
        return 1
    from config_loader import get_config
    from sheets_client import SheetsClient
    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    appended = _append_many(client, "reference_posts", rows)
    print(json.dumps({"status": "APPLIED", "reference_posts_appended": appended}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
