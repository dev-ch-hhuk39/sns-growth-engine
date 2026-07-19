#!/usr/bin/env python3
"""Plan/apply safe reference-source collection.

Only fetch_enabled=true sources are eligible. manual_only sources and X sources
are skipped by default. This script does not download media.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import importlib.util
import json
import re
import shutil
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
SOURCES_FILE = ROOT / "config/source_accounts/default_sources.json"
PUBLIC_TIMEOUT_SECONDS = 15

from media.rights_policy import THIRD_PARTY_REFERENCE_ONLY


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_true(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def load_sources_from_file() -> list[dict[str, Any]]:
    data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    return data.get("sources", data if isinstance(data, list) else [])


def redact_raw(raw: dict[str, Any]) -> dict[str, Any]:
    redacted = {}
    for key, value in raw.items():
        if re.search(r"(token|secret|cookie|authorization|password|api[_-]?key)", str(key), re.I):
            redacted[key] = "[REDACTED]"
        else:
            redacted[key] = value
    return redacted


def _meta(pattern: str, text: str) -> str:
    m = re.search(pattern, text, flags=re.I | re.S)
    return html.unescape(m.group(1).strip()) if m else ""


def adapter_status() -> dict[str, str]:
    return {
        "beautifulsoup4": "installed" if importlib.util.find_spec("bs4") else "not_installed",
        "lxml": "installed" if importlib.util.find_spec("lxml") else "not_installed",
        "requests": "installed" if importlib.util.find_spec("requests") else "not_installed",
        "tweepy": "installed" if importlib.util.find_spec("tweepy") else "not_installed",
        "agent_reach": "installed" if shutil.which("agent-reach") else "optional_not_installed",
        "cli_anything": "installed" if shutil.which("cli-anything") else "optional_not_installed",
        "threads_public_og": "wired",
        "x_fetch": "blocked_by_default",
    }


def parse_og_metadata(body: str, url: str) -> dict[str, str]:
    """Parse public OG metadata with BS4/lxml when present, regex fallback otherwise."""
    title = description = image = ""
    parser_used = "regex"
    try:
        from bs4 import BeautifulSoup
        parser = "lxml" if importlib.util.find_spec("lxml") else "html.parser"
        soup = BeautifulSoup(body, parser)
        parser_used = parser

        def content(prop: str) -> str:
            tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
            return html.unescape(str(tag.get("content", "")).strip()) if tag else ""

        title = content("og:title")
        description = content("og:description")
        image = content("og:image")
    except Exception:
        title = _meta(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']*)', body)
        description = _meta(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']*)', body)
        image = _meta(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']*)', body)
    return {
        "og_title": title,
        "og_description": description,
        "og_image": image,
        "author_handle": _meta(r"threads\.com/@([^/\"'?]+)", url),
        "parser": parser_used,
    }


def fetch_threads_post(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; sns-growth-engine/2.0; +dry-run)"})
    try:
        with urllib.request.urlopen(req, timeout=PUBLIC_TIMEOUT_SECONDS) as res:
            body = res.read(2_000_000).decode("utf-8", errors="replace")
        meta = parse_og_metadata(body, url)
        return {
            "ok": True,
            "text": meta["og_description"] or meta["og_title"],
            "author_handle": meta["author_handle"],
            "thumbnail_url": meta["og_image"],
            "raw": redact_raw({"url": url, **meta}),
            "error": "",
        }
    except Exception as exc:
        return {"ok": False, "text": "", "author_handle": "", "thumbnail_url": "", "raw": {"url": url}, "error": f"{type(exc).__name__}: {exc}"}


def plan_x_fetch_adapter(src: dict[str, Any], *, include_x: bool) -> dict[str, Any]:
    return {
        "source_id": src.get("source_id", ""),
        "platform": "x",
        "adapter": "tweepy",
        "status": "BLOCKED" if not include_x else "PLAN_ONLY",
        "reason": "X fetch is disabled by default; no API call is made",
        "installed": importlib.util.find_spec("tweepy") is not None,
    }


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
        # A source can retain its historical manual_url provenance while being
        # explicitly and narrowly enabled for the autonomous Threads collector.
        # Do not make that override implicit: both fetch_enabled and the
        # dedicated reference_autopilot_enabled flag are required.
        elif (is_true(src.get("manual_only", False)) or str(src.get("collection_method", "")).lower() in {"manual_url", "manual_json"}) and not is_true(src.get("reference_autopilot_enabled", False)):
            reason = "manual_only"
        elif src_platform == "x" and not include_x:
            reason = "x_disabled_by_default"
        if reason:
            skipped.append({"source_id": src.get("source_id", ""), "url": src.get("url") or src.get("source_url", ""), "reason": reason})
        else:
            selected.append(src)
    return selected, skipped


def normalize_source(src: dict[str, Any], fetched: dict[str, Any] | None = None) -> dict[str, Any]:
    url = src.get("url") or src.get("source_url") or src.get("canonical_url") or ""
    fetched = fetched or {}
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12] if url else datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    media_urls = [fetched.get("thumbnail_url")] if fetched.get("thumbnail_url") else []
    return {
        "post_id": f"sap_{digest}",
        "source_id": src.get("source_id", ""),
        "account_id": ",".join(src.get("target_account_ids") or [src.get("target_account_id", "")]),
        "source_platform": src.get("source_platform", ""),
        "source_handle": fetched.get("author_handle") or src.get("handle", ""),
        "post_text": fetched.get("text", ""),
        "media_urls": json.dumps(media_urls, ensure_ascii=False),
        "likes": "",
        "reposts": "",
        "replies": "",
        "views": "",
        "bookmarks": "",
        "engagement_rate": "",
        "buzz": "",
        "rights_policy": src.get("rights_policy", "reference_only"),
        "reuse_policy": src.get("reuse_policy", "reference_only"),
        "status": "COLLECTED" if fetched.get("ok") else "UNAVAILABLE",
        "collected_at": now_iso(),
        "post_url": url,
        "use_status": "REFERENCE_ONLY",
        "rights_status": THIRD_PARTY_REFERENCE_ONLY,
        "can_reuse_media": "false",
        "media_download": "false",
        "media_body_saved": "false",
        "media_rights_note": "X/Threads media is third_party_reference_only unless separately approved as approved_creator_clip.",
        "fetch_error": fetched.get("error", ""),
    }


def dedupe_rows(rows: list[dict[str, Any]], existing_urls: set[str] | None = None) -> tuple[list[dict[str, Any]], int]:
    existing = set(existing_urls or set())
    deduped: list[dict[str, Any]] = []
    skipped = 0
    for row in rows:
        key = str(row.get("post_url", "")).strip()
        if key and key in existing:
            skipped += 1
            continue
        deduped.append(row)
        if key:
            existing.add(key)
    return deduped, skipped


def _append_many(client, logical: str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    ws = client._ws(logical)
    headers = ws.row_values(1)
    existing_urls = {str(r.get("post_url", "")).strip() for r in ws.get_all_records()}
    to_append, _ = dedupe_rows(rows, existing_urls)
    if to_append:
        ws.append_rows([["" if row.get(h) is None else str(row.get(h, "")) for h in headers] for row in to_append], value_input_option="USER_ENTERED")
    return len(to_append)


def main() -> int:
    parser = argparse.ArgumentParser(description="collect reference source posts safely")
    parser.add_argument("--platform", default="all", choices=["threads", "x", "youtube", "tiktok", "all"])
    parser.add_argument("--account-id", default="all", choices=["all", "night_scout", "liver_manager", "beauty_account"])
    parser.add_argument("--include-x", action="store_true")
    parser.add_argument("--source-id", action="append", default=[])
    parser.add_argument("--source-url", action="append", default=[], help="Ephemeral Threads source URL for small dry-run/approved tests")
    parser.add_argument("--fetch-real", action="store_true", help="Fetch public Threads page metadata/text")
    parser.add_argument("--show-adapter-status", action="store_true")
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-collect", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()

    if args.account_id == "beauty_account":
        print(json.dumps({"status": "BLOCKED", "reason": "beauty_account collection is disabled"}, ensure_ascii=False))
        return 1
    sources = load_sources_from_file()
    if args.source_id:
        wanted = set(args.source_id)
        sources = [s for s in sources if str(s.get("source_id", "")) in wanted]
    if args.source_url:
        # An explicit URL is a bounded one-off target, not an instruction to
        # combine that target with every enabled registry source.
        sources = []
    for i, url in enumerate(args.source_url, 1):
        sources.append({
            "source_id": f"local_threads_source_{i}",
            "source_platform": "threads",
            "target_account_ids": ["night_scout" if args.account_id == "all" else args.account_id],
            "url": url,
            "fetch_enabled": True,
            "manual_only": False,
        })
    selected, skipped = select_sources(sources, account_id=args.account_id, platform=args.platform, include_x=args.include_x)
    selected = selected[: max(1, args.limit)]
    rows = []
    archive_payloads = []
    x_adapter_plans = []
    for src in selected:
        url = src.get("url") or src.get("source_url") or src.get("canonical_url") or ""
        src_platform = str(src.get("source_platform", "")).lower()
        if src_platform == "x":
            x_adapter_plans.append(plan_x_fetch_adapter(src, include_x=args.include_x))
            fetched = {}
        else:
            fetched = fetch_threads_post(url) if args.fetch_real and src_platform == "threads" else {}
        rows.append(normalize_source(src, fetched))
        if fetched:
            archive_payloads.append(fetched.get("raw", {}))
    rows, duplicate_skipped = dedupe_rows(rows)
    plan = {
        "status": "PLAN_ONLY" if not args.apply else "WILL_APPLY",
        "selected_count": len(selected),
        "deduped_count": len(rows),
        "duplicate_skipped": duplicate_skipped,
        "skipped_count": len(skipped),
        "media_download": False,
        "x_enabled": bool(args.include_x),
        "real_fetch": bool(args.fetch_real),
        "adapter_status": adapter_status(),
        "x_adapter_plans": x_adapter_plans[:10],
        "rows": rows[:10],
        "archive_payloads": archive_payloads[:10],
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
    appended = _append_many(client, "source_account_posts", rows)
    print(json.dumps({"status": "APPLIED", "source_account_posts_appended": appended}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
