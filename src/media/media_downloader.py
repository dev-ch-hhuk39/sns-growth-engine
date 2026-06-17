"""Safe media download planner.

This module does not perform network downloads unless both download and
confirm_download are true and the source policy allows it. The production
audit path uses it as a BLOCKED/plan generator.
"""
from __future__ import annotations

from typing import Any

from .media_asset_store import check_source_media_policy


def plan_media_download(
    source: dict[str, Any],
    media_url: str,
    *,
    download: bool = False,
    confirm_download: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    policy = check_source_media_policy(source, action="download")
    blocked_reasons = list(policy.get("blocked_reasons", []))

    if download and not confirm_download:
        blocked_reasons.append("--download requires --confirm-download")
    if not download:
        blocked_reasons.append("download flag not set: plan only")

    status = "BLOCKED" if blocked_reasons else ("DRY_RUN" if dry_run else "READY")
    return {
        "status": status,
        "source_id": source.get("source_id", ""),
        "media_url": media_url,
        "dry_run": dry_run,
        "download": download,
        "confirm_download": confirm_download,
        "blocked_reasons": blocked_reasons,
        "warnings": policy.get("warnings", []),
        "local_path": "",
    }


def plan_media_downloads(
    source_media_pairs: list[tuple[dict[str, Any], str]],
    *,
    download: bool = False,
    confirm_download: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    plans = [
        plan_media_download(
            source,
            url,
            download=download,
            confirm_download=confirm_download,
            dry_run=dry_run,
        )
        for source, url in source_media_pairs
    ]
    blocked = [r for p in plans for r in p.get("blocked_reasons", [])]
    return {
        "status": "BLOCKED" if blocked else ("DRY_RUN" if dry_run else "READY"),
        "plans": plans,
        "blocked_reasons": blocked,
        "downloaded_count": 0,
    }
