#!/usr/bin/env python3
"""Discover bounded posts from owner-approved direct-media sources.

Discovery only records metadata and original URLs.  It never downloads media,
uploads to Cloudinary, or publishes. Threads account discovery intentionally
requires an official/API adapter; YouTube/TikTok use yt-dlp metadata mode when
available and remain bounded to ``--max-posts``.
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]; sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]
from config_loader import get_config
from media_source_policy import decision
from sheets_client import TAB_DEFINITIONS, SheetsClient


def canonical(url: str) -> str:
    return str(url).split("?", 1)[0].rstrip("/")


def discover_ytdlp(source: dict[str, Any], limit: int) -> tuple[list[dict[str, Any]], str]:
    try:
        import yt_dlp
        opts = {"quiet": True, "skip_download": True, "extract_flat": True, "playlistend": limit}
        info = yt_dlp.YoutubeDL(opts).extract_info(str(source.get("source_url", "")), download=False)
    except Exception as exc:
        return [], f"metadata_discovery_failed:{type(exc).__name__}"
    entries = info.get("entries") if isinstance(info, dict) else None
    entries = entries if isinstance(entries, list) else [info]
    result = []
    for item in entries[:limit]:
        if not isinstance(item, dict): continue
        raw_url = str(item.get("webpage_url") or item.get("url") or "")
        if not raw_url.startswith("http"): continue
        video_id = str(item.get("id") or hashlib.sha256(canonical(raw_url).encode()).hexdigest()[:16])
        result.append({"external_post_id": video_id, "canonical_post_url": canonical(raw_url), "original_post_text": str(item.get("description") or ""), "published_at": str(item.get("upload_date") or ""), "media_count": "1", "media_type": "video"})
    return result, "PASS"


def plan_sources(account_id: str) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    data = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text()).get("sources", [])
    selected, blocked = [], []
    for source in data:
        targets = source.get("target_account_ids") or [source.get("target_account_id")]
        if account_id not in targets: continue
        check = decision(source, "direct_media")
        if not check["allowed"]:
            blocked.append({"source_id": str(source.get("source_id", "")), "reason": check["reason"]}); continue
        selected.append(source)
    return selected, blocked


def source_post_row(source: dict[str, Any], item: dict[str, Any]) -> dict[str, str]:
    now = datetime.now(timezone.utc).isoformat(); external = str(item["external_post_id"])
    source_id = str(source["source_id"])
    return {"source_post_id": f"sp_{source_id}_{external}", "source_id": source_id, "source_account_id": source_id,
        "target_account_id": str((source.get("target_account_ids") or [source.get("target_account_id")])[0]),
        "platform": str(source.get("source_platform") or source.get("platform") or "").lower(),
        "canonical_post_url": item["canonical_post_url"], "external_post_id": external,
        "original_post_text": item.get("original_post_text", ""), "published_at": item.get("published_at", ""),
        "discovered_at": now, "media_count": item.get("media_count", "0"), "media_type": item.get("media_type", ""),
        "rights_status": str(source.get("rights_status", "approved_creator_clip")), "permission_status": "approved",
        "permission_scope": "owner_attestation", "attribution_policy": "internal_ledger", "direct_media_reuse_allowed": "true",
        "collection_status": "DISCOVERED", "processing_status": "PENDING", "content_hash": hashlib.sha256(str(item.get("original_post_text", "")).encode()).hexdigest(),
        "retry_count": "0", "last_error": "", "created_at": now, "updated_at": now}


def main() -> int:
    parser = argparse.ArgumentParser(description="bounded discovery for approved direct-media source posts")
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager"])
    parser.add_argument("--max-posts", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true"); parser.add_argument("--apply", action="store_true"); parser.add_argument("--confirm-discovery", action="store_true")
    args = parser.parse_args()
    if args.apply and not args.confirm_discovery:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-discovery"})); return 1
    selected, blocked = plan_sources(args.account_id); previews: list[dict[str, Any]] = []; reasons = []
    for source in selected:
        platform = str(source.get("source_platform") or source.get("platform") or "").lower()
        if platform not in {"youtube", "tiktok"}:
            reasons.append({"source_id": source["source_id"], "reason": "threads_requires_official_discovery_adapter"}); continue
        if not args.apply:
            reasons.append({"source_id": source["source_id"], "reason": "dry_run_network_discovery_not_executed"}); continue
        rows, status = discover_ytdlp(source, max(1, min(args.max_posts, 20)))
        if status != "PASS": reasons.append({"source_id": source["source_id"], "reason": status})
        previews.extend(source_post_row(source, row) for row in rows)
    deduped = {row["canonical_post_url"]: row for row in previews}
    result: dict[str, Any] = {"status": "PLAN_ONLY", "account_id": args.account_id, "selected_source_count": len(selected), "blocked_sources": blocked, "discovery_warnings": reasons, "discovered_post_count": len(deduped), "posts_preview": [{k: row[k] for k in ("source_post_id", "source_id", "platform", "canonical_post_url", "media_type")} for row in list(deduped.values())[:20]], "would_save_source_posts": bool(deduped), "network_fetch": False}
    if not args.apply:
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    result["network_fetch"] = True
    cfg = get_config(); client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False); ws = client._ensure_tab("source_posts", TAB_DEFINITIONS["source_posts"]); headers = ws.row_values(1)
    existing = {str(row.get("canonical_post_url", "")) for row in ws.get_all_records()}; saved = 0
    for row in deduped.values():
        if row["canonical_post_url"] in existing: continue
        ws.append_row([row.get(header, "") for header in headers], value_input_option="USER_ENTERED"); saved += 1
    print(json.dumps({**result, "status": "APPLIED", "saved_source_posts": saved}, ensure_ascii=False, indent=2)); return 0

if __name__ == "__main__": raise SystemExit(main())
