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


def _permission(permissions: list[dict[str, Any]], source_id: str, account_id: str, operation: str) -> dict[str, Any] | None:
    return next((item for item in permissions if str(item.get("source_id", "")) == source_id and is_active_permission(item, account_id=account_id, operation=operation)), None)


def build_inventory(datasets: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    queue = datasets["queue"]; posts = datasets["source_posts"]; media = datasets["source_post_media"]
    permissions = datasets["media_permissions"]; clips = datasets["video_clip_candidates"]; assets = datasets["media_assets"]
    for account_id in ACCOUNTS:
        account_queue = [row for row in queue if str(row.get("account_id", "")) == account_id and str(row.get("status", "")).upper() in {"READY", "WAITING_REVIEW", "DRAFT"}]
        original = next((row for row in account_queue if str(row.get("generation_mode", "")) in {"original_hypothesis", "original_text", "autonomous_original"} and _public_text(row)), None)
        reference = next((row for row in account_queue if str(row.get("generation_mode", "")) in {"reference_based", "reference_text", "manual_reference"} and _public_text(row)), None)
        for kind, selected in (("original_text", original), ("reference_text", reference)):
            if selected:
                candidates.append({"account_id": account_id, "canary_type": kind, "public_post_text": _public_text(selected), "persona_validator_status": selected.get("account_fit_status", "PASS"), "final_public_post_validator_status": selected.get("validator_status", "PASS"), "queue_id": selected.get("queue_id", "")})
        account_posts = {str(row.get("source_post_id", "")): row for row in posts if str(row.get("target_account_id") or row.get("account_id") or "") == account_id}
        for item in media:
            parent = account_posts.get(str(item.get("source_post_id", "")))
            if not parent:
                continue
            source_id = str(parent.get("source_id", ""))
            perm = _permission(permissions, source_id, account_id, "direct")
            if not perm:
                continue
            media_type = str(item.get("media_type", "")).lower()
            asset = next((a for a in assets if str(a.get("media_id") or a.get("media_asset_id") or "") == str(item.get("media_asset_id") or item.get("source_post_media_id") or "")), {})
            url = str(asset.get("storage_url") or item.get("storage_url") or "")
            if not url:
                continue
            kind = "direct_video" if media_type == "video" else "direct_image"
            if any(c.get("account_id") == account_id and c.get("canary_type") == kind for c in candidates):
                continue
            candidates.append({"account_id": account_id, "canary_type": kind, "source_id": source_id, "rights_status": perm.get("rights_status", ""), "permission_status": perm.get("permission_status", ""), "permission_evidence": perm.get("evidence_reference", ""), "public_post_text": _public_text(next((q for q in account_queue if _public_text(q)), {})), "source_post_id": parent.get("source_post_id", ""), "media_asset_id": asset.get("media_id") or item.get("media_asset_id") or item.get("source_post_media_id", ""), "media_url": url})
        for parent_id, parent in account_posts.items():
            bundle = [item for item in media if str(item.get("source_post_id", "")) == parent_id]
            if len(bundle) < 2 or any(c.get("account_id") == account_id and c.get("canary_type") == "direct_carousel" for c in candidates):
                continue
            perm = _permission(permissions, str(parent.get("source_id", "")), account_id, "direct")
            ordered = sorted(bundle, key=lambda item: int(item.get("media_index") or 0))
            urls = [str(item.get("storage_url") or "") for item in ordered]
            if not perm or not all(urls):
                continue
            candidates.append({"account_id": account_id, "canary_type": "direct_carousel", "source_id": parent.get("source_id", ""), "rights_status": perm.get("rights_status", ""), "permission_status": perm.get("permission_status", ""), "permission_evidence": perm.get("evidence_reference", ""), "public_post_text": _public_text(next((q for q in account_queue if _public_text(q)), {})), "source_post_id": parent_id, "media_asset_ids": [item.get("media_asset_id") or item.get("source_post_media_id", "") for item in ordered], "media_order": [item.get("media_index", "") for item in ordered]})
        for clip in clips:
            if str(clip.get("account_id", "")) != account_id or str(clip.get("rights_status", "")).lower() not in APPROVED_RIGHTS:
                continue
            source_id = str(clip.get("source_id", "")); perm = _permission(permissions, source_id, account_id, "clip")
            asset = next((a for a in assets if str(a.get("clip_candidate_id") or a.get("video_clip_id") or "") == str(clip.get("clip_candidate_id", ""))), {})
            if not perm or not str(asset.get("storage_url", "")):
                continue
            candidates.append({"account_id": account_id, "canary_type": "generated_clip", "source_id": source_id, "rights_status": perm.get("rights_status", ""), "permission_status": perm.get("permission_status", ""), "permission_evidence": perm.get("evidence_reference", ""), "public_post_text": _public_text(clip), "source_video_id": clip.get("source_video_id", ""), "clip_candidate_id": clip.get("clip_candidate_id", ""), "local_path": asset.get("local_path", "ready"), "start_seconds": clip.get("start_seconds", ""), "end_seconds": clip.get("end_seconds", "")})
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
