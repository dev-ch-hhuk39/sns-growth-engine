#!/usr/bin/env python3
"""Build a read-only twelve-format canary inventory from live Sheets evidence."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_bounded_media_canary_plan import build_plan
from final_production_contracts import ACCOUNTS, APPROVED_RIGHTS, is_active_permission


def _rows(use_sheets: bool) -> tuple[dict[str, list[dict[str, Any]]], str]:
    empty = {key: [] for key in ("queue", "source_posts", "source_post_media", "media_permissions", "source_videos", "video_clip_candidates", "media_assets")}
    if not use_sheets:
        return empty, "use_sheets_required"
    try:
        sys.path.insert(0, str(ROOT / "src"))
        from config_loader import get_config
        from sheets_client import SheetsClient
        cfg = get_config(); client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=True)
        return {key: [dict(row) for row in client._ws(key).get_all_records()] for key in empty}, "READ_OK"
    except Exception as exc:
        return empty, type(exc).__name__


def _public_text(row: dict[str, Any]) -> str:
    return str(row.get("public_post_text") or row.get("text") or "").strip()


def _fresh(row: dict[str, Any]) -> bool:
    return str(row.get("canary_id", "")).startswith("canary_fresh_") and str(row.get("status", "")).upper() not in {"LEGACY_INVALID_CANARY", "QUARANTINED"}


def _queue_content_type(row: dict[str, Any]) -> str:
    """Prefer the canonical content type; retain only the legacy fallback."""
    return str(row.get("content_type") or row.get("media_type") or "").strip().lower()


def _permission(permissions: list[dict[str, Any]], source_id: str, account_id: str, operation: str) -> dict[str, Any] | None:
    return next((item for item in permissions if str(item.get("source_id", "")) == source_id and is_active_permission(item, account_id=account_id, operation=operation)), None)


def build_inventory(datasets: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    queue = datasets["queue"]; posts = datasets["source_posts"]; media = datasets["source_post_media"]
    permissions = datasets["media_permissions"]; clips = datasets["video_clip_candidates"]; assets = datasets["media_assets"]
    source_videos = {str(row.get("source_video_id", "")): row for row in datasets["source_videos"]}
    for account_id in ACCOUNTS:
        account_queue = sorted((row for row in queue if str(row.get("account_id", "")) == account_id and _fresh(row)), key=lambda row: str(row.get("created_at", "")), reverse=True)
        original = next((row for row in account_queue if str(row.get("generation_mode", "")) in {"original_hypothesis", "original_text", "autonomous_original"} and _public_text(row)), None)
        reference = next((row for row in account_queue if str(row.get("generation_mode", "")) in {"reference_based", "reference_text", "manual_reference"} and _public_text(row)), None)
        for kind, selected in (("original_text", original), ("reference_text", reference)):
            if selected:
                candidates.append({"account_id": account_id, "canary_type": kind, "canary_id": selected.get("canary_id", ""), "public_post_text": _public_text(selected), "persona_validator_status": selected.get("account_fit_status", "PASS"), "final_public_post_validator_status": selected.get("validator_status", "PASS"), "internal_leak_status": selected.get("internal_leak_status", ""), "queue_id": selected.get("queue_id", "")})
        account_posts = {str(row.get("source_post_id", "")): row for row in posts if str(row.get("target_account_id") or row.get("account_id") or "") == account_id}
        media_by_parent = {}
        for item in media:
            media_by_parent.setdefault(str(item.get("source_post_id", "")), []).append(item)
        assets_by_id = {str(row.get("media_id") or row.get("media_asset_id") or ""): row for row in assets}
        # Queue selection is authoritative.  It preserves the fresh batch and
        # avoids letting an older source-media row win merely by sheet order.
        for kind in ("direct_image", "direct_video"):
            matching_queue = next((row for row in account_queue if _queue_content_type(row) == kind), {})
            parent = account_posts.get(str(matching_queue.get("source_post_id", "")))
            if not matching_queue or not parent:
                continue
            source_id = str(parent.get("source_id", "")); perm = _permission(permissions, source_id, account_id, "direct")
            asset_id = str(matching_queue.get("media_asset_id", ""))
            asset = assets_by_id.get(asset_id, {})
            child = next((row for row in media_by_parent.get(str(parent.get("source_post_id", "")), []) if str(row.get("media_asset_id", "")) == asset_id), {})
            url = str(matching_queue.get("media_url") or asset.get("storage_url") or child.get("storage_url") or "")
            if not perm or not asset_id or not url:
                continue
            candidates.append({"account_id": account_id, "canary_type": kind, "canary_id": matching_queue.get("canary_id", ""), "queue_id": matching_queue.get("queue_id", ""), "source_id": source_id, "rights_status": perm.get("rights_status", ""), "permission_status": perm.get("permission_status", ""), "permission_evidence": perm.get("evidence_reference", ""), "public_post_text": _public_text(matching_queue), "persona_validator_status": matching_queue.get("account_fit_status", ""), "final_public_post_validator_status": matching_queue.get("validator_status", ""), "internal_leak_status": matching_queue.get("internal_leak_status", ""), "publisher_media_type": matching_queue.get("publisher_media_type", ""), "source_post_id": parent.get("source_post_id", ""), "media_asset_id": asset_id, "media_url": url})
        matching_queue = next((row for row in account_queue if _queue_content_type(row) == "direct_carousel"), {})
        parent_id = str(matching_queue.get("source_post_id", "")); parent = account_posts.get(parent_id)
        bundle = sorted(media_by_parent.get(parent_id, []), key=lambda item: int(item.get("media_index") or 0))
        if matching_queue and parent and len(bundle) >= 2:
            perm = _permission(permissions, str(parent.get("source_id", "")), account_id, "direct")
            urls = [str(item.get("storage_url") or assets_by_id.get(str(item.get("media_asset_id", "")), {}).get("storage_url") or "") for item in bundle]
            if perm and all(urls):
                candidates.append({"account_id": account_id, "canary_type": "direct_carousel", "canary_id": matching_queue.get("canary_id", ""), "queue_id": matching_queue.get("queue_id", ""), "source_id": parent.get("source_id", ""), "rights_status": perm.get("rights_status", ""), "permission_status": perm.get("permission_status", ""), "permission_evidence": perm.get("evidence_reference", ""), "public_post_text": _public_text(matching_queue), "persona_validator_status": matching_queue.get("account_fit_status", ""), "final_public_post_validator_status": matching_queue.get("validator_status", ""), "internal_leak_status": matching_queue.get("internal_leak_status", ""), "publisher_media_type": matching_queue.get("publisher_media_type", ""), "source_post_id": parent_id, "media_asset_ids": [item.get("media_asset_id") or item.get("source_post_media_id", "") for item in bundle], "media_order": [item.get("media_index", "") for item in bundle]})
        account_clips = sorted(
            (clip for clip in clips if str(clip.get("account_id", "")) == account_id),
            key=lambda clip: str(clip.get("source_platform", "")) != "system_generated_owned",
        )
        for clip in account_clips:
            if str(clip.get("rights_status", "")).lower() not in APPROVED_RIGHTS:
                continue
            source_video = source_videos.get(str(clip.get("source_video_id", "")), {})
            source_id = str(clip.get("source_id") or source_video.get("source_id") or "")
            if not source_id and str(clip.get("source_platform", "")) == "system_generated_owned":
                source_id = str(clip.get("clip_id", "")).removeprefix("clip_")
            perm = _permission(permissions, source_id, account_id, "clip")
            asset = next((a for a in assets if str(a.get("clip_candidate_id") or a.get("video_clip_id") or "") == str(clip.get("clip_candidate_id", ""))), {})
            if not perm or not str(asset.get("storage_url", "")):
                continue
            matching_queue = next((q for q in account_queue if str(q.get("clip_candidate_id", "")) == str(clip.get("clip_candidate_id", "")) and _queue_content_type(q) == "generated_clip"), {})
            if not matching_queue:
                continue
            candidates.append({"account_id": account_id, "canary_type": "generated_clip", "canary_id": matching_queue.get("canary_id", ""), "queue_id": matching_queue.get("queue_id", ""), "source_id": source_id, "rights_status": perm.get("rights_status", ""), "permission_status": perm.get("permission_status", ""), "permission_evidence": perm.get("evidence_reference", ""), "public_post_text": _public_text(matching_queue), "persona_validator_status": matching_queue.get("account_fit_status", ""), "final_public_post_validator_status": matching_queue.get("validator_status", ""), "internal_leak_status": matching_queue.get("internal_leak_status", ""), "publisher_media_type": matching_queue.get("publisher_media_type", ""), "source_video_id": clip.get("source_video_id", ""), "clip_candidate_id": clip.get("clip_candidate_id", ""), "local_path": asset.get("local_path", "ready"), "start_seconds": clip.get("start_seconds", ""), "end_seconds": clip.get("end_seconds", "")})
            break
    plan = build_plan(candidates)
    return {**plan, "status": "LIVE_INVENTORY_PLAN", "candidate_count": len(candidates), "candidates": candidates, "would_write": False, "would_post": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(); data, source = _rows(args.use_sheets); result = build_inventory(data); result["sheets_status"] = source
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"); result["output_path"] = str(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
