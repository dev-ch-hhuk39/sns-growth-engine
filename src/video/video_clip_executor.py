"""Video clip execution planner with strict confirm gates."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from media.media_asset_store import build_media_asset, check_source_media_policy

JST = timezone(timedelta(hours=9))


def _now_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S+09:00")


def build_clip_execution_plan(
    source: dict[str, Any],
    clip_plan: dict[str, Any],
    *,
    cut: bool = False,
    confirm_cut: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    policy = check_source_media_policy(source, action="cut")
    blocked = list(policy.get("blocked_reasons", []))
    if cut and not confirm_cut:
        blocked.append("--cut requires --confirm-cut")
    if not cut:
        blocked.append("cut flag not set: plan only")

    execution_id = f"clip_exec_{str(uuid.uuid4())[:8]}"
    status = "BLOCKED" if blocked else ("DRY_RUN" if dry_run else "READY")
    local_path = "" if status == "BLOCKED" or dry_run else clip_plan.get("output_path", "")

    media_asset = None
    if local_path:
        media_asset = build_media_asset(
            account_id=clip_plan.get("account_id", ""),
            source_id=source.get("source_id", ""),
            raw_item_id=clip_plan.get("raw_item_id", ""),
            media_type="video",
            local_path=local_path,
            status="WAITING_REVIEW",
            rights_policy=source.get("rights_policy", "unknown"),
            reuse_policy=source.get("reuse_policy", "reference_only"),
            media_policy=source.get("media_policy", "plan_only"),
            clip_execution_id=execution_id,
        )

    return {
        "clip_execution_id": execution_id,
        "source_id": source.get("source_id", ""),
        "clip_candidate_id": clip_plan.get("clip_candidate_id", ""),
        "status": status,
        "dry_run": dry_run,
        "cut": cut,
        "confirm_cut": confirm_cut,
        "local_path": local_path,
        "media_asset": media_asset,
        "blocked_reasons": blocked,
        "warnings": policy.get("warnings", []),
        "created_at": _now_jst(),
    }


def build_clip_execution_runs(
    source_clip_pairs: list[tuple[dict[str, Any], dict[str, Any]]],
    *,
    cut: bool = False,
    confirm_cut: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    runs = [
        build_clip_execution_plan(source, clip, cut=cut, confirm_cut=confirm_cut, dry_run=dry_run)
        for source, clip in source_clip_pairs
    ]
    blocked = [r for run in runs for r in run.get("blocked_reasons", [])]
    media_assets = [run["media_asset"] for run in runs if run.get("media_asset")]
    return {
        "status": "BLOCKED" if blocked else ("DRY_RUN" if dry_run else "READY"),
        "clip_execution_runs": runs,
        "media_assets": media_assets,
        "blocked_reasons": blocked,
        "created_at": _now_jst(),
    }
