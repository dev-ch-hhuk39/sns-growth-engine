"""Pure contracts shared by the final production preparation commands.

Nothing here performs a network request or a Sheets mutation.  The functions
make optional X acquisition, permission gaps, canary evidence and activation
requirements explicit rather than treating an unavailable integration as a
successful post.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ACCOUNTS = ("night_scout", "liver_manager")
CANARY_TYPES = (
    "original_text", "reference_text", "direct_image", "direct_video",
    "direct_carousel", "generated_clip",
)
APPROVED_RIGHTS = {"owned", "licensed", "approved_creator_clip"}


def truthy(value: Any) -> bool:
    return value is True or str(value or "").strip().lower() in {"1", "true", "yes"}


def canary_id(account_id: str, canary_type: str) -> str:
    return f"canary_{account_id}_{canary_type}"


def is_active_permission(row: dict[str, Any], *, account_id: str, operation: str) -> bool:
    if str(row.get("account_id", "")) != account_id:
        return False
    if str(row.get("permission_status", "")).lower() != "approved":
        return False
    if str(row.get("rights_status", "")).lower() not in APPROVED_RIGHTS:
        return False
    if truthy(row.get("revoked")) or not str(row.get("evidence_reference", "")).strip():
        return False
    expires_at = str(row.get("expires_at", "")).strip()
    if expires_at:
        try:
            expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires <= datetime.now(timezone.utc):
                return False
        except ValueError:
            return False
    field = {
        "direct": "allow_original_repost",
        "clip": "allow_clip_repost",
        "download": "allow_download",
        "upload": "allow_cloudinary_storage",
    }.get(operation, "")
    return bool(field and truthy(row.get(field)))


def permission_deficits(
    sources: list[dict[str, Any]], permissions: list[dict[str, Any]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for source in sources:
        targets = source.get("target_account_ids") or [source.get("target_account_id")]
        for account_id in targets:
            if account_id not in ACCOUNTS:
                continue
            source_id = str(source.get("source_id", ""))
            platform = str(source.get("source_platform") or source.get("platform") or "").lower()
            if platform not in {"threads", "youtube", "tiktok", "x"}:
                continue
            direct_ok = any(str(p.get("source_id", "")) == source_id and is_active_permission(p, account_id=account_id, operation="direct") for p in permissions)
            clip_ok = any(str(p.get("source_id", "")) == source_id and is_active_permission(p, account_id=account_id, operation="clip") for p in permissions)
            if not direct_ok:
                rows.append({"account_id": account_id, "source_id": source_id, "requirement": "direct_media_permission", "reason": "active_evidence_bearing_direct_permission_missing"})
            if platform in {"youtube", "tiktok"} and not clip_ok:
                rows.append({"account_id": account_id, "source_id": source_id, "requirement": "generated_clip_permission", "reason": "active_evidence_bearing_clip_permission_missing"})
    return rows


def source_integrity_report(
    parents: list[dict[str, Any]], children: list[dict[str, Any]], *, source_ids: set[str] | None = None,
) -> dict[str, Any]:
    relevant = [row for row in parents if not source_ids or str(row.get("source_id", "")) in source_ids]
    by_id = {str(row.get("source_post_id", "")): row for row in relevant}
    failures: list[dict[str, str]] = []
    for child in children:
        parent_id = str(child.get("source_post_id", ""))
        parent = by_id.get(parent_id)
        if not parent:
            continue
        if str(child.get("canonical_post_url", "")) != str(parent.get("canonical_post_url", "")):
            failures.append({"source_post_id": parent_id, "reason": "child_parent_url_mismatch"})
        try:
            index = int(child.get("media_index", ""))
            if index < 0:
                failures.append({"source_post_id": parent_id, "reason": "negative_media_index"})
        except (TypeError, ValueError):
            failures.append({"source_post_id": parent_id, "reason": "media_index_missing"})
    for parent_id, parent in by_id.items():
        url = str(parent.get("canonical_post_url", ""))
        if "/post/" not in url and "/status/" not in url:
            failures.append({"source_post_id": parent_id, "reason": "parent_not_individual_post"})
    return {
        "status": "NO_EVIDENCE" if not by_id else "PASS" if not failures else "FAIL",
        "parent_count": len(by_id),
        "child_count": sum(1 for row in children if str(row.get("source_post_id", "")) in by_id),
        "failures": failures[:100],
    }


def activation_evidence(
    posted_results: list[dict[str, Any]], metric_jobs: list[dict[str, Any]],
) -> dict[str, Any]:
    expected = {canary_id(account_id, kind) for account_id in ACCOUNTS for kind in CANARY_TYPES}
    verified: set[str] = set()
    for row in posted_results:
        candidate = str(row.get("canary_id", ""))
        if candidate not in expected:
            continue
        if str(row.get("status", "")).upper() != "POSTED":
            continue
        if not str(row.get("post_url", "")).strip() or not str(row.get("external_post_id", "")).strip():
            continue
        if str(row.get("verification_status", "")).upper() not in {"PASS", "VERIFIED", "READ_AFTER_WRITE_PASS"}:
            continue
        verified.add(candidate)
    metrics_by_canary: dict[str, set[int]] = {}
    for row in metric_jobs:
        candidate = str(row.get("canary_id", ""))
        try:
            window = int(row.get("window_hours", 0))
        except (TypeError, ValueError):
            continue
        if candidate and str(row.get("status", "")).upper() not in {"CANCELLED", "FAILED"}:
            metrics_by_canary.setdefault(candidate, set()).add(window)
    missing_posts = sorted(expected - verified)
    missing_metrics = sorted(item for item in expected if {24, 72, 168} - metrics_by_canary.get(item, set()))
    return {
        "status": "READY_FOR_ACTIVATION" if not missing_posts and not missing_metrics else "BLOCKED",
        "expected_canary_count": len(expected),
        "verified_canary_count": len(verified),
        "missing_posted_read_after_write": missing_posts,
        "missing_metric_windows": missing_metrics,
    }


def required_owner_inputs(deficits: list[dict[str, str]]) -> dict[str, Any]:
    needs: list[dict[str, Any]] = []
    for account_id in ACCOUNTS:
        needs.extend([
            {
                "input_id": f"{account_id}_owned_direct_image",
                "account_id": account_id,
                "canary_type": "direct_image",
                "required": ["individual_source_post_url", "image_file_or_https_url", "media_permissions evidence", "Threads repost permission"],
            },
            {
                "input_id": f"{account_id}_owned_direct_video",
                "account_id": account_id,
                "canary_type": "direct_video",
                "required": ["individual_source_post_url", "video_file_or_https_url", "media_permissions evidence", "Threads repost permission"],
            },
            {
                "input_id": f"{account_id}_owned_direct_carousel",
                "account_id": account_id,
                "canary_type": "direct_carousel",
                "required": ["one individual source_post URL", "ordered image/video URLs", "media_permissions evidence", "Threads carousel permission"],
            },
            {
                "input_id": f"{account_id}_owned_generated_clip",
                "account_id": account_id,
                "canary_type": "generated_clip",
                "required": ["individual owned/licensed video URL or local file", "permission evidence", "allowed clip range", "Threads repost permission"],
            },
        ])
    return {
        "schema_version": 1,
        "purpose": "single owner-input bundle for final media canaries; no permission is inferred",
        "permission_deficits": deficits,
        "required_owner_inputs": needs,
    }
