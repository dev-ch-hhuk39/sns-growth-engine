"""Media asset planning and safety checks for Phase 13 production paths."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

JST = timezone(timedelta(hours=9))


def _now_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S+09:00")


def _new_asset_id() -> str:
    return f"ma_{str(uuid.uuid4())[:8]}"


def check_source_media_policy(source: dict[str, Any], action: str) -> dict[str, Any]:
    """Return an allow/block decision for download/cut/upload/use actions."""
    reasons: list[str] = []
    warnings: list[str] = []
    status = "OK"

    source_id = source.get("source_id", "")
    candidate_status = source.get("candidate_status", "candidate")
    rights_policy = source.get("rights_policy", "unknown")
    reuse_policy = source.get("reuse_policy", "reference_only")
    media_policy = source.get("media_policy", "do_not_download")
    subject_policy = source.get("subject_policy", {}) or {}
    rules = subject_policy.get("rules", []) if isinstance(subject_policy, dict) else []

    if candidate_status != "approved" and action in {"download", "cut", "upload"}:
        reasons.append(f"candidate_status={candidate_status}: approved以外は{action}不可")
    if rights_policy == "unknown":
        warnings.append("rights_policy=unknown: WAITING_REVIEW必須")
        if action in {"download", "cut", "upload", "post"}:
            reasons.append("rights_policy=unknown: media利用はWAITING_REVIEW")
    if reuse_policy == "no_reuse":
        reasons.append("reuse_policy=no_reuse: media利用不可")
    if media_policy == "do_not_download" and action in {"download", "cut", "upload"}:
        reasons.append("media_policy=do_not_download: download禁止")
    if media_policy == "plan_only" and action in {"download", "cut", "upload", "post"}:
        reasons.append("media_policy=plan_only: 保存/投稿利用不可")
    if "analysis_only_if_male_scout" in rules and source.get("analysis_only"):
        reasons.append("analysis_only source: clip/download/upload/post不可")

    if reasons:
        status = "BLOCKED"
    elif warnings:
        status = "WAITING_REVIEW"

    return {
        "source_id": source_id,
        "action": action,
        "allowed": not reasons,
        "status": status,
        "blocked_reasons": reasons,
        "warnings": warnings,
        "rights_policy": rights_policy,
        "reuse_policy": reuse_policy,
        "media_policy": media_policy,
        "candidate_status": candidate_status,
    }


def build_media_asset(
    *,
    account_id: str,
    source_id: str,
    raw_item_id: str,
    media_type: str,
    external_url: str = "",
    local_path: str = "",
    cloudinary_url: str = "",
    status: str = "WAITING_REVIEW",
    rights_policy: str = "unknown",
    reuse_policy: str = "reference_only",
    media_policy: str = "plan_only",
    clip_execution_id: str = "",
) -> dict[str, Any]:
    return {
        "media_asset_id": _new_asset_id(),
        "account_id": account_id,
        "source_id": source_id,
        "raw_item_id": raw_item_id,
        "media_type": media_type,
        "external_url": external_url,
        "local_path": local_path,
        "cloudinary_url": cloudinary_url,
        "status": status,
        "rights_policy": rights_policy,
        "reuse_policy": reuse_policy,
        "media_policy": media_policy,
        "clip_execution_id": clip_execution_id,
        "created_at": _now_jst(),
    }


def collect_media_assets_from_raw_items(
    raw_source_items: list[dict[str, Any]],
    sources_by_id: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Convert raw_source_items.image_urls/video_urls into media_assets records."""
    sources_by_id = sources_by_id or {}
    assets: list[dict[str, Any]] = []

    for item in raw_source_items:
        source_id = item.get("source_id", "")
        source = sources_by_id.get(source_id, {})
        account_id = item.get("target_account_id") or item.get("account_id") or ""
        status = "WAITING_REVIEW" if source.get("rights_policy", "unknown") == "unknown" else "PLANNED"
        for url in item.get("image_urls", []) or []:
            assets.append(build_media_asset(
                account_id=account_id,
                source_id=source_id,
                raw_item_id=item.get("raw_item_id", ""),
                media_type="image",
                external_url=url,
                status=status,
                rights_policy=source.get("rights_policy", item.get("rights_status", "unknown")),
                reuse_policy=source.get("reuse_policy", item.get("reuse_policy", "reference_only")),
                media_policy=source.get("media_policy", "plan_only"),
            ))
        for url in item.get("video_urls", []) or []:
            assets.append(build_media_asset(
                account_id=account_id,
                source_id=source_id,
                raw_item_id=item.get("raw_item_id", ""),
                media_type="video",
                external_url=url,
                status=status,
                rights_policy=source.get("rights_policy", item.get("rights_status", "unknown")),
                reuse_policy=source.get("reuse_policy", item.get("reuse_policy", "reference_only")),
                media_policy=source.get("media_policy", "plan_only"),
            ))

    return assets


def preflight_media_assets(
    assets: list[dict[str, Any]],
    sources_by_id: dict[str, dict[str, Any]] | None = None,
    *,
    action: str = "post",
) -> dict[str, Any]:
    sources_by_id = sources_by_id or {}
    results = []
    blocked: list[str] = []
    warnings: list[str] = []

    for asset in assets:
        source = sources_by_id.get(asset.get("source_id", ""), {})
        decision = check_source_media_policy(source, action=action) if source else {
            "allowed": False,
            "status": "WAITING_REVIEW",
            "blocked_reasons": ["source registry entry not found"],
            "warnings": [],
        }
        if not decision["allowed"]:
            blocked.extend(decision["blocked_reasons"])
        warnings.extend(decision.get("warnings", []))
        results.append({"media_asset_id": asset.get("media_asset_id"), **decision})

    return {
        "status": "BLOCKED" if blocked else ("WAITING_REVIEW" if warnings else "PASS"),
        "asset_count": len(assets),
        "blocked_reasons": blocked,
        "warnings": warnings,
        "results": results,
        "created_at": _now_jst(),
    }


def build_media_queue_candidate(
    account_id: str,
    platform: str,
    text: str,
    media_assets: list[dict[str, Any]],
) -> dict[str, Any]:
    status = "WAITING_REVIEW" if account_id == "beauty_account" or media_assets else "DRAFT"
    return {
        "queue_id": f"q_media_{str(uuid.uuid4())[:8]}",
        "account_id": account_id,
        "platform": platform,
        "text": text,
        "media_asset_ids": [a.get("media_asset_id") for a in media_assets],
        "status": status,
        "created_at": _now_jst(),
    }
