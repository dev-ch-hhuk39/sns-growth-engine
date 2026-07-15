#!/usr/bin/env python3
"""Source-level permission policy for direct reuse and generated clips."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY_FILE = ROOT / "config" / "media_source_usage_modes.json"

DIRECT_SCOPE = {
    "download_original_media",
    "store_in_cloudinary",
    "repost_original_media",
    "generate_new_caption",
}
CLIP_SCOPE = {
    "download_video",
    "transcribe",
    "analyse",
    "cut",
    "store_in_cloudinary",
    "repost_clip",
    "generate_new_caption",
}
APPROVED_RIGHTS = {"owned", "licensed", "approved_creator_clip"}
VALID_MODES = {"text_reference_only", "direct_media_reuse", "clip_source", "direct_and_clip", "blocked"}


def load_policy() -> dict[str, Any]:
    return json.loads(POLICY_FILE.read_text(encoding="utf-8"))


def media_usage_mode(source: dict[str, Any]) -> str:
    explicit = str(source.get("media_usage_mode", "")).strip()
    if explicit in VALID_MODES:
        return explicit
    mapped = str(load_policy().get("source_modes", {}).get(str(source.get("source_id", "")), ""))
    return mapped if mapped in VALID_MODES else "text_reference_only"


def normalized_scope(source: dict[str, Any]) -> set[str]:
    aliases = {
        "download": "download_video",
        "analyze": "analyse",
        "upload": "store_in_cloudinary",
        "repost_to_threads": "repost_clip",
        "use_for_post_text": "generate_new_caption",
    }
    values = source.get("permission_scope", [])
    if isinstance(values, str):
        values = [item.strip() for item in values.split("|") if item.strip()]
    return {aliases.get(str(item).strip(), str(item).strip()) for item in values}


def decision(source: dict[str, Any], action: str) -> dict[str, Any]:
    mode = media_usage_mode(source)
    rights = str(source.get("rights_status", "")).lower()
    approved = str(source.get("permission_status", "")).lower() == "approved"
    scope = normalized_scope(source)
    if action == "direct_media":
        required = DIRECT_SCOPE
        allowed_mode = mode in {"direct_media_reuse", "direct_and_clip"}
    elif action == "clip":
        required = CLIP_SCOPE
        allowed_mode = mode in {"clip_source", "direct_and_clip"}
    else:
        return {"allowed": False, "mode": mode, "missing_scope": [], "reason": "unknown_media_action"}
    missing = sorted(required - scope)
    allowed = rights in APPROVED_RIGHTS and approved and allowed_mode and not missing
    if allowed:
        reason = "PASS"
    elif rights not in APPROVED_RIGHTS or not approved:
        reason = "permission_or_rights_not_approved"
    elif not allowed_mode:
        reason = f"media_usage_mode={mode} does not allow {action}"
    else:
        reason = "missing_permission_scope"
    return {"allowed": allowed, "mode": mode, "missing_scope": missing, "reason": reason}
