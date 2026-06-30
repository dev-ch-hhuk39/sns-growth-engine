#!/usr/bin/env python3
"""Collect video reference metadata without downloading media."""
from __future__ import annotations

import argparse
import html
import json
import re
import urllib.request
from datetime import datetime, timezone
from typing import Any

PUBLIC_TIMEOUT_SECONDS = 15


def _meta(pattern: str, text: str) -> str:
    m = re.search(pattern, text, flags=re.I | re.S)
    return html.unescape(m.group(1).strip()) if m else ""


def fetch_video_metadata(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; sns-growth-engine/2.0; +dry-run)"})
    try:
        with urllib.request.urlopen(req, timeout=PUBLIC_TIMEOUT_SECONDS) as res:
            body = res.read(2_000_000).decode("utf-8", errors="replace")
        return {
            "ok": True,
            "title": _meta(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']*)', body),
            "thumbnail_url": _meta(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']*)', body),
            "author_handle": _meta(r'"ownerChannelName"\s*:\s*"([^"]+)"', body),
            "error": "",
        }
    except Exception as exc:
        return {"ok": False, "title": "", "thumbnail_url": "", "author_handle": "", "error": f"{type(exc).__name__}: {exc}"}


def build_video_reference(url: str, account_id: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    platform = "youtube" if "youtu" in url else "tiktok" if "tiktok" in url else "video"
    metadata = metadata or {}
    return {
        "reference_post_id": f"video_ref_{account_id}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "account_id": account_id,
        "platform": platform,
        "video_url": url,
        "title": metadata.get("title", ""),
        "author_handle": metadata.get("author_handle", ""),
        "thumbnail_url": metadata.get("thumbnail_url", ""),
        "metadata_status": "FETCHED" if metadata.get("ok") else "PLAN_ONLY" if not metadata else "UNAVAILABLE",
        "fetch_error": metadata.get("error", ""),
        "rights_status": "third_party_reference_only",
        "can_download": False,
        "can_cut": False,
        "can_upload": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="collect video references safely")
    parser.add_argument("--url", action="append", default=[])
    parser.add_argument("--fetch-metadata", action="store_true")
    parser.add_argument("--account-id", default="night_scout", choices=["night_scout", "liver_manager", "beauty_account"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-collect", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()
    if args.account_id == "beauty_account":
        print(json.dumps({"status": "BLOCKED", "reason": "beauty_account disabled"}, ensure_ascii=False))
        return 1
    rows = []
    for url in (args.url or ["reference_only://sample"]):
        meta = fetch_video_metadata(url) if args.fetch_metadata and url.startswith("http") else {}
        rows.append(build_video_reference(url, args.account_id, meta))
    if not args.apply:
        print(json.dumps({"status": "PLAN_ONLY", "download": False, "rows": rows}, ensure_ascii=False, indent=2))
        return 0
    if not args.confirm_collect or not args.use_sheets:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-collect --use-sheets"}, ensure_ascii=False))
        return 1
    from config_loader import get_config
    from sheets_client import SheetsClient
    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    ws = client._ws("reference_posts")
    headers = ws.row_values(1)
    ws.append_rows([[str(row.get(h, "")) for h in headers] for row in rows], value_input_option="USER_ENTERED")
    print(json.dumps({"status": "APPLIED", "reference_posts_appended": len(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
