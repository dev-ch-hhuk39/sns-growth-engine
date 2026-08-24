#!/usr/bin/env python3
"""Plan/apply safe reference-source collection.

Only fetch_enabled=true sources are eligible. X remains skipped by default;
the one explicitly approved bounded read-only source requires --include-x.
This script does not download media.
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

from media.rights_policy import THIRD_PARTY_REFERENCE_ONLY  # noqa: E402


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
        "gallery_dl": "installed" if shutil.which("gallery-dl") else "not_installed",
        "agent_reach": "installed" if shutil.which("agent-reach") else "optional_not_installed",
        "cli_anything": "installed" if shutil.which("cli-anything") else "optional_not_installed",
        "threads_cli_public": "installed" if shutil.which("th") else "not_installed",
        "threads_logged_out_graphql": "wired",
        "threads_public_screen": "wired_final_fallback",
        "x_fetch": "bounded_read_only_with_explicit_include_x",
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


def is_individual_post_url(url: str, platform: str) -> bool:
    low = str(url).lower()
    if platform == "threads":
        return "/post/" in low
    if platform == "x":
        return "/status/" in low
    return False


def discover_threads_post_urls(account_url: str, *, limit: int) -> dict[str, Any]:
    """Bounded public account-page discovery; never stores the account page as a post."""
    req = urllib.request.Request(account_url, headers={"User-Agent": "Mozilla/5.0 (compatible; sns-growth-engine/2.0)"})
    try:
        with urllib.request.urlopen(req, timeout=PUBLIC_TIMEOUT_SECONDS) as res:
            body = res.read(2_000_000).decode("utf-8", errors="replace")
    except Exception as exc:
        return {"status": "FALLBACK_REQUIRED", "urls": [], "reason": type(exc).__name__}
    urls = []
    for match in re.findall(r'https?://(?:www\.)?threads\.com/@[^\s"\\]+/post/[A-Za-z0-9_-]+', body):
        clean = match.split("?")[0].rstrip("/\\")
        if clean not in urls:
            urls.append(clean)
    return {"status": "DISCOVERED" if urls else "FALLBACK_REQUIRED", "urls": urls[:max(1, limit)], "reason": "" if urls else "browser_export_or_manual_json_required"}


def fetch_threads_account_posts(src: dict[str, Any], *, limit: int) -> dict[str, Any]:
    """Use the shared three-stage public Threads router without media download."""
    try:
        from acquisition.factory import build_router

        routed = build_router().route("threads.profile_posts", src, limit=min(5, limit))
        rows = [
            {
                "post_url": post.canonical_post_url,
                "external_post_id": post.external_post_id,
                "text": post.original_post_text,
                "published_at": post.published_at,
                "media_urls": [item.original_media_url for item in post.media_items],
                "media_order": [item.media_index for item in post.media_items],
            }
            for post in routed.posts
        ]
        return {
            "status": "FETCHED",
            "rows": rows,
            "reason": "",
            "backend": routed.backend_name,
            "fallback_used": routed.fallback_used,
        }
    except Exception as exc:
        return {
            "status": "DEFERRED",
            "rows": [],
            "reason": str(exc).replace("\n", " ")[:240],
            "backend": "",
            "fallback_used": False,
        }


def plan_x_fetch_adapter(src: dict[str, Any], *, include_x: bool) -> dict[str, Any]:
    return {
        "source_id": src.get("source_id", ""),
        "platform": "x",
        "adapter": "gallery-dl",
        "status": "BLOCKED" if not include_x else "READY_FOR_BOUNDED_READ_ONLY_FETCH",
        "reason": "--include-x is required; unavailable gallery-dl falls back to browser export/manual JSON",
        "installed": shutil.which("gallery-dl") is not None,
    }


def fetch_x_account_posts(src: dict[str, Any], *, limit: int) -> dict[str, Any]:
    """Route X discovery through the shared acquisition router.

    Keeping this legacy reference collector on the router prevents the direct
    media and reference-text paths from drifting into separate X implementations.
    The route has no scraping fallback: recovery remains browser export/manual
    JSON when the bounded gallery-dl adapter is unavailable.
    """
    if not is_true(src.get("x_read_only")):
        return {"status": "BLOCKED", "rows": [], "reason": "x_read_only_not_approved"}
    try:
        from acquisition.factory import build_router

        routed = build_router().route("x.profile_posts", src, limit=limit)
        posts = routed.posts
        rows = [
            {
                "post_url": post.canonical_post_url,
                "external_post_id": post.external_post_id,
                "text": post.original_post_text,
                "published_at": post.published_at,
                "media_urls": [item.original_media_url for item in post.media_items],
            }
            for post in posts
        ]
        return {
            "status": "FETCHED",
            "rows": rows[:limit],
            "reason": "",
            "backend": routed.backend_name,
            "fallback_used": routed.fallback_used,
        }
    except Exception:
        return {"status": "FALLBACK_REQUIRED", "rows": [], "reason": "browser_export_or_manual_json_required"}


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
    external_post_id = str(fetched.get("external_post_id", "")).strip()
    digest_input = external_post_id or url
    digest = hashlib.sha1(digest_input.encode("utf-8")).hexdigest()[:12] if digest_input else datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    media_urls = list(fetched.get("media_urls") or [])
    if not media_urls and fetched.get("thumbnail_url"):
        media_urls = [fetched["thumbnail_url"]]
    return {
        "post_id": external_post_id or f"sap_{digest}",
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
        "external_post_id": external_post_id,
        "published_at": str(fetched.get("published_at", "")),
        "media_order": json.dumps(list(range(len(media_urls))), ensure_ascii=False),
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


def source_post_bundle(row: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Preserve one fetched post and its ordered media under one parent id."""
    canonical_url = str(row.get("post_url", "")).split("?")[0].rstrip("/")
    external_id = str(row.get("external_post_id") or row.get("post_id") or "")
    source_id = str(row.get("source_id", ""))
    parent_id = f"sp_{source_id}_{external_id or hashlib.sha1(canonical_url.encode()).hexdigest()[:12]}"
    urls = json.loads(str(row.get("media_urls") or "[]"))
    parent = {
        "source_post_id": parent_id, "source_id": source_id, "source_account_id": source_id,
        "target_account_id": str(row.get("account_id", "")).split(",")[0],
        "platform": row.get("source_platform", ""), "canonical_post_url": canonical_url,
        "external_post_id": external_id, "original_post_text": row.get("post_text", ""),
        "published_at": row.get("published_at", ""), "discovered_at": row.get("collected_at", now_iso()),
        "media_count": str(len(urls)), "media_type": "mixed_carousel" if len(urls) > 1 else ("image_or_video" if urls else ""),
        "author_handle": row.get("source_handle", ""), "media_items_json": row.get("media_urls", "[]"),
        "rights_status": THIRD_PARTY_REFERENCE_ONLY, "permission_status": "unknown",
        "permission_scope": "", "direct_media_reuse_allowed": "false", "collection_status": "COLLECTED",
        "processing_status": "REFERENCE_ONLY", "content_hash": hashlib.sha256(str(row.get("post_text", "")).encode()).hexdigest(),
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    children = [{
        "source_post_media_id": f"spm_{parent_id}_{index}", "source_post_id": parent_id,
        "media_index": str(index), "original_media_url": media_url, "canonical_post_url": canonical_url,
        "acquisition_method": "reference_metadata_only", "media_type": "unknown", "rights_status": THIRD_PARTY_REFERENCE_ONLY,
        "permission_status": "unknown", "reuse_status": "REFERENCE_ONLY", "created_at": now_iso(), "updated_at": now_iso(),
    } for index, media_url in enumerate(urls) if str(media_url).startswith("http")]
    return parent, children


def load_manual_export(path: str, *, platform: str) -> tuple[list[dict[str, Any]], str]:
    """Load a bounded browser/manual export without accepting profile URLs.

    The file is deliberately opt-in.  It may contain a JSON list, or an object
    with ``posts``/``items``. Each item must carry an individual post URL.
    """
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        return [], f"manual_json_invalid:{type(exc).__name__}"
    items = payload if isinstance(payload, list) else payload.get("posts", payload.get("items", [])) if isinstance(payload, dict) else []
    if not isinstance(items, list):
        return [], "manual_json_posts_list_required"
    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        post_url = str(item.get("post_url") or item.get("url") or "").split("?")[0].rstrip("/")
        if not is_individual_post_url(post_url, platform):
            continue
        rows.append({
            "post_url": post_url,
            "external_post_id": str(item.get("external_post_id") or item.get("post_id") or ""),
            "text": str(item.get("text") or item.get("post_text") or ""),
            "published_at": str(item.get("published_at") or item.get("created_at") or ""),
            "media_urls": list(item.get("media_urls") or []),
        })
    return rows, ""


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


def _append_source_post_bundles(client: Any, rows: list[dict[str, Any]]) -> dict[str, int]:
    """Append only missing source-post parents and their own ordered children."""
    parents = [source_post_bundle(row)[0] for row in rows if is_individual_post_url(str(row.get("post_url", "")), str(row.get("source_platform", "")))]
    children = [child for row in rows for child in source_post_bundle(row)[1] if is_individual_post_url(str(row.get("post_url", "")), str(row.get("source_platform", "")))]
    post_ws = client._ws("source_posts")
    media_ws = client._ws("source_post_media")
    post_headers, media_headers = post_ws.row_values(1), media_ws.row_values(1)
    known_posts = {str(item.get("canonical_post_url", "")) for item in post_ws.get_all_records()}
    known_media = {str(item.get("source_post_media_id", "")) for item in media_ws.get_all_records()}
    new_parents = [row for row in parents if str(row["canonical_post_url"]) not in known_posts]
    new_children = [row for row in children if str(row["source_post_media_id"]) not in known_media]
    if new_parents:
        post_ws.append_rows([[str(row.get(header, "")) for header in post_headers] for row in new_parents], value_input_option="USER_ENTERED")
    if new_children:
        media_ws.append_rows([[str(row.get(header, "")) for header in media_headers] for row in new_children], value_input_option="USER_ENTERED")
    return {"source_posts_appended": len(new_parents), "source_post_media_appended": len(new_children)}


def main() -> int:
    parser = argparse.ArgumentParser(description="collect reference source posts safely")
    parser.add_argument("--platform", default="all", choices=["threads", "x", "youtube", "tiktok", "all"])
    from accounts.managed_accounts import account_choices
    parser.add_argument("--account-id", default="all", choices=account_choices(include_all=True))
    parser.add_argument("--include-x", action="store_true")
    parser.add_argument("--source-id", action="append", default=[])
    parser.add_argument("--source-url", action="append", default=[], help="Ephemeral Threads source URL for small dry-run/approved tests")
    parser.add_argument("--manual-json", default="", help="bounded browser/manual JSON fallback; individual post URLs only")
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
    manual_rows: list[dict[str, Any]] = []
    if args.manual_json:
        manual_platform = args.platform if args.platform in {"x", "threads"} else "threads"
        manual_rows, manual_reason = load_manual_export(args.manual_json, platform=manual_platform)
        if manual_reason:
            skipped.append({"source_id": "manual_json", "url": args.manual_json, "reason": manual_reason})
    for src in selected:
        url = src.get("url") or src.get("source_url") or src.get("canonical_url") or ""
        src_platform = str(src.get("source_platform", "")).lower()
        if src_platform == "x":
            x_adapter_plans.append(plan_x_fetch_adapter(src, include_x=args.include_x))
            # Account pages are discovery roots only. The real adapter accepts
            # only individual /status/ URLs (or browser/manual export) and
            # never turns a profile into a source post.
            if args.include_x and args.fetch_real:
                outcome = fetch_x_account_posts(src, limit=args.limit)
                for item in outcome["rows"]:
                    rows.append(normalize_source({**src, "source_url": item["post_url"]}, {"ok": True, **item, "author_handle": str(src.get("source_handle", "")), "error": ""}))
                if outcome["status"] != "FETCHED":
                    skipped.append({"source_id": src.get("source_id", ""), "url": url, "reason": outcome["reason"]})
            else:
                skipped.append({"source_id": src.get("source_id", ""), "url": url, "reason": "x_individual_post_or_browser_export_required"})
            continue
        elif src_platform == "threads" and not is_individual_post_url(url, "threads"):
            outcome = (
                fetch_threads_account_posts(src, limit=args.limit)
                if args.fetch_real
                else {"status": "PLAN_ONLY", "rows": [], "reason": "fetch_real_required", "backend": ""}
            )
            for item in outcome["rows"]:
                fetched = {
                    "ok": True,
                    "text": item["text"],
                    "author_handle": item["author_handle"],
                    "published_at": item["published_at"],
                    "media_urls": item["media_urls"],
                    "error": "",
                }
                rows.append(normalize_source({**src, "source_url": item["post_url"]}, {**fetched, "external_post_id": item["external_post_id"]}))
                archive_payloads.append(redact_raw({"post_url": item["post_url"], "backend": item.get("backend", "")}))
            if outcome["status"] != "FETCHED":
                skipped.append({"source_id": src.get("source_id", ""), "url": url, "reason": outcome["reason"]})
            continue
        else:
            fetched = fetch_threads_post(url) if args.fetch_real and src_platform == "threads" else {}
        rows.append(normalize_source(src, fetched))
        if fetched:
            archive_payloads.append(fetched.get("raw", {}))
    for item in manual_rows:
        source = next((src for src in selected if str(src.get("source_platform", "")).lower() == args.platform), {"source_id": "manual_import", "source_platform": args.platform, "target_account_ids": [args.account_id]})
        rows.append(normalize_source({**source, "source_url": item["post_url"]}, {"ok": True, **item, "author_handle": str(source.get("source_handle", ""))}))
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
        "manual_import_count": len(manual_rows),
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
    bundles = _append_source_post_bundles(client, rows)
    print(json.dumps({"status": "APPLIED", "source_account_posts_appended": appended, **bundles}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
