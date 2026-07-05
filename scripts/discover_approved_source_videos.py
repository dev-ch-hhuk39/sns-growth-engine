#!/usr/bin/env python3
"""Discover video candidates from approved source channels/accounts.

This is a dry-run first planner. It does not download media, cut clips,
upload assets, post to Threads, or perform unbounded account scraping.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from media.rights_policy import rights_allows_media_use  # noqa: E402
from media_growth_schemas import (  # noqa: E402
    SOURCE_VIDEO_FIELDS,
    build_source_video,
    canonicalize_video_url,
    is_duplicate_source_video,
)

SOURCES_FILE = ROOT / "config/source_accounts/default_sources.json"
CONFIG_FILE = ROOT / "config/media_growth_engine.json"
LOCAL_SOURCE_VIDEOS_FILE = ROOT / "output/source_videos/source_videos.json"


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


def load_sources() -> list[dict[str, Any]]:
    return json.loads(SOURCES_FILE.read_text(encoding="utf-8"))["sources"]


def load_existing_source_videos(path: str = "") -> list[dict[str, Any]]:
    candidate = Path(path) if path else LOCAL_SOURCE_VIDEOS_FILE
    if not candidate.exists():
        return []
    return json.loads(candidate.read_text(encoding="utf-8"))


def permission_ok(source: dict[str, Any]) -> bool:
    return (
        source.get("permission_status") == "approved"
        and bool(source.get("permission_evidence_type"))
        and bool(source.get("permission_evidence_note"))
    )


def select_discovery_sources(account_id: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    allowed_ids = set(config.get("allowed_source_ids", []))
    allowed_types = set(config.get("allowed_source_types_for_discovery", ["channel", "account"]))
    rows = []
    for source in load_sources():
        targets = source.get("target_account_ids") or [source.get("target_account_id")]
        if account_id != "all" and account_id not in targets:
            continue
        if source.get("source_id") not in allowed_ids:
            continue
        if source.get("source_type") not in allowed_types:
            continue
        rows.append(source)
    return rows


def build_source_video_candidates(source: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    """Return bounded planned candidates without network fetch."""
    scan_limit = int(config.get("max_videos_per_source_scan", 50))
    per_source_limit = int(config.get("max_new_videos_per_source_per_run", 10))
    planned_count = min(scan_limit, per_source_limit)
    videos = []
    for index in range(1, planned_count + 1):
        videos.append(build_source_video(source, index=index))
    return videos


def _source_discovery_status(source: dict[str, Any]) -> str:
    platform = source.get("source_platform")
    if platform == "youtube":
        return "YOUTUBE_CHANNEL_DISCOVERY_PLAN"
    if platform == "tiktok":
        return "TIKTOK_ACCOUNT_LIMITED_MANUAL_SAFE_PLAN"
    return "DISCOVERY_PLAN"


def build_discovery_plan(
    account_id: str,
    *,
    apply: bool = False,
    confirm_discovery: bool = False,
    existing_source_videos: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    config = load_config()
    existing = existing_source_videos if existing_source_videos is not None else load_existing_source_videos()
    selected = select_discovery_sources(account_id, config)
    blocked: list[str] = []
    if not config.get("source_video_discovery_enabled"):
        blocked.append("source_video_discovery_disabled")
    if apply and not confirm_discovery:
        blocked.append("--apply requires --confirm-discovery")
    if apply and not config.get("source_video_discovery_apply_enabled"):
        blocked.append("source_video_discovery_apply_disabled")

    max_total = int(config.get("max_total_new_videos_per_run", 20))
    source_results = []
    new_videos: list[dict[str, Any]] = []
    duplicate_count = 0
    skipped_count = 0
    discovered_count = 0

    for source in selected:
        source_blocked: list[str] = []
        rights = str(source.get("rights_status", ""))
        if not rights_allows_media_use(rights):
            source_blocked.append("rights_status_not_media_approved")
        if not permission_ok(source):
            source_blocked.append("permission_evidence_missing")

        candidates = [] if source_blocked else build_source_video_candidates(source, config)
        discovered_count += len(candidates)
        source_new = []
        source_duplicates = 0
        for candidate in candidates:
            if is_duplicate_source_video(candidate, existing + new_videos):
                duplicate_count += 1
                source_duplicates += 1
                continue
            if len(new_videos) >= max_total:
                skipped_count += 1
                continue
            source_new.append(candidate)
            new_videos.append(candidate)

        source_results.append({
            "source_id": source.get("source_id"),
            "platform": source.get("source_platform"),
            "source_type": source.get("source_type"),
            "source_url": canonicalize_video_url(source.get("source_url", ""), source.get("source_platform", "")),
            "rights_status": rights,
            "permission_status": source.get("permission_status", ""),
            "discovery_status": _source_discovery_status(source),
            "scan_limit": int(config.get("max_videos_per_source_scan", 50)),
            "new_limit": int(config.get("max_new_videos_per_source_per_run", 10)),
            "discovered_video_count": len(candidates),
            "new_video_count": len(source_new),
            "duplicate_video_count": source_duplicates,
            "blocked_reasons": source_blocked,
        })

    plan = {
        "status": "BLOCKED" if blocked else "PLAN_ONLY",
        "account_id": account_id,
        "selected_sources": [
            {"source_id": s.get("source_id"), "platform": s.get("source_platform"), "source_type": s.get("source_type")}
            for s in selected
        ],
        "discovery_enabled": bool(config.get("source_video_discovery_enabled")),
        "source_video_discovery_apply_enabled": bool(config.get("source_video_discovery_apply_enabled")),
        "limits": {
            "max_videos_per_source_scan": int(config.get("max_videos_per_source_scan", 50)),
            "max_new_videos_per_source_per_run": int(config.get("max_new_videos_per_source_per_run", 10)),
            "max_total_new_videos_per_run": max_total,
        },
        "dedupe_keys": config.get("dedupe_keys", []),
        "source_videos_schema": SOURCE_VIDEO_FIELDS,
        "adapter_status": {
            "yt_dlp": "installed" if importlib.util.find_spec("yt_dlp") else "not_installed",
            "network_fetch": "not_invoked",
            "tiktok_account_expansion": "limited_manual_safe",
        },
        "source_results": source_results,
        "discovered_video_count": discovered_count,
        "new_video_count": len(new_videos),
        "duplicate_video_count": duplicate_count,
        "skipped_video_count": skipped_count,
        "new_videos_preview": new_videos[:5],
        "would_save_source_videos": bool(apply and confirm_discovery and not blocked),
        "blocked_reasons": blocked,
    }
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description="discover approved source videos")
    parser.add_argument("--account-id", default="liver_manager")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-discovery", action="store_true")
    parser.add_argument("--existing-source-videos-json", default="")
    args = parser.parse_args()

    existing = load_existing_source_videos(args.existing_source_videos_json) if args.existing_source_videos_json else None
    plan = build_discovery_plan(
        args.account_id,
        apply=args.apply,
        confirm_discovery=args.confirm_discovery,
        existing_source_videos=existing,
    )
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 1 if plan["status"] == "BLOCKED" and args.apply else 0


if __name__ == "__main__":
    raise SystemExit(main())
