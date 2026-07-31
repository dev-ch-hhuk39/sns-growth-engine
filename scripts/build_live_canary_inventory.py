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
    return (
        str(row.get("canary_id", "")).startswith("canary_fresh_")
        and str(row.get("status", "")).upper() not in {"LEGACY_INVALID_CANARY", "QUARANTINED", "SUPERSEDED_QUALITY"}
        and str(row.get("excluded_from_activation", "")).strip().lower() not in {"1", "true", "yes"}
        and str(row.get("repost_prohibited", "")).strip().lower() not in {"1", "true", "yes"}
    )


def _queue_content_type(row: dict[str, Any]) -> str:
    """Prefer the canonical content type; retain only the legacy fallback."""
    return str(row.get("content_type") or row.get("media_type") or "").strip().lower()


def _quality_fields(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "batch_id", "batch_diversity_status", "batch_similarity_score",
        "hook_similarity_score", "closing_similarity_score", "structure_variant", "structure_similarity_score",
        "shared_sentence_count", "shared_sentences", "shared_closing_detected",
        "shared_hook_detected", "compared_candidate_ids",
        "structure_compared_candidate_ids", "diversity_blocked_reasons",
        "primary_topic", "supporting_topics", "topic_confidence",
        "primary_topic_evidence_score", "primary_topic_direct_confidence", "topic_coherence_status",
        "topic_coherence_score", "off_topic_sentence_count", "off_topic_sentences",
        "hook_topic", "closing_topic", "visual_topic",
        "hook_topic_match", "closing_topic_match", "visual_topic_match",
        "topic_blocked_reasons", "quality_gate_version",
        "generation_attempt", "generation_rule_version",
        "feature_schema_version", "hook_text", "body_text", "closing_text",
        "cta_intent", "key_claims_json", "post_design_json", "visual_plan_json",
        "media_primary_topic", "visual_cta_match", "visual_plan_version",
        "visual_plan_attempt", "visual_text_hash", "claim_support_json", "alignment_blocked_reasons",
    )
    return {key: row.get(key, "") for key in keys}




def _canonical_queue_kind(row: dict[str, Any]) -> str:
    generation_mode = str(row.get("generation_mode", "")).strip().lower()
    if generation_mode in {"original_hypothesis", "original_text", "autonomous_original"}:
        return "original_text"
    if generation_mode in {"reference_based", "reference_text", "manual_reference"}:
        return "reference_text"
    return _queue_content_type(row)


def _latest_complete_first_wave_batch(queue: list[dict[str, Any]]) -> str:
    required = {(account, kind) for account in ACCOUNTS for kind in ("original_text", "direct_image")}
    grouped: dict[str, set[tuple[str, str]]] = {}
    newest: dict[str, str] = {}
    for row in queue:
        if not _fresh(row):
            continue
        batch = str(row.get("batch_id", "")).strip()
        account = str(row.get("account_id", "")).strip()
        kind = _canonical_queue_kind(row)
        if not batch or (account, kind) not in required:
            continue
        grouped.setdefault(batch, set()).add((account, kind))
        newest[batch] = max(newest.get(batch, ""), str(row.get("created_at", "")))
    complete = [batch for batch, keys in grouped.items() if keys == required]
    return max(complete, key=lambda batch: (newest.get(batch, ""), batch), default="")

def _permission(permissions: list[dict[str, Any]], source_id: str, account_id: str, operation: str) -> dict[str, Any] | None:
    return next((item for item in permissions if str(item.get("source_id", "")) == source_id and is_active_permission(item, account_id=account_id, operation=operation)), None)


def build_inventory(
    datasets: dict[str, list[dict[str, Any]]],
    *,
    wave: str = "all_12",
    batch_id: str = "",
) -> dict[str, Any]:
    if wave not in {"all_12", "first_wave"}:
        raise ValueError("unsupported_wave")
    candidates: list[dict[str, Any]] = []
    queue = datasets["queue"]; posts = datasets["source_posts"]; media = datasets["source_post_media"]
    selected_batch_id = (
        batch_id
        or (
            _latest_complete_first_wave_batch(queue)
            if wave == "first_wave"
            else ""
        )
    )
    permissions = datasets["media_permissions"]; clips = datasets["video_clip_candidates"]; assets = datasets["media_assets"]
    source_videos = {str(row.get("source_video_id", "")): row for row in datasets["source_videos"]}
    for account_id in ACCOUNTS:
        account_queue = sorted(
            (
                row for row in queue
                if str(row.get("account_id", "")) == account_id
                and _fresh(row)
                and (
                    not selected_batch_id
                    or str(row.get("batch_id", "")) == selected_batch_id
                )
            ),
            key=lambda row: str(row.get("created_at", "")),
            reverse=True,
        )
        original = next((row for row in account_queue if str(row.get("generation_mode", "")) in {"original_hypothesis", "original_text", "autonomous_original"} and _public_text(row)), None)
        reference = next((row for row in account_queue if str(row.get("generation_mode", "")) in {"reference_based", "reference_text", "manual_reference"} and _public_text(row)), None)
        text_selections = (("original_text", original),) if wave == "first_wave" else (("original_text", original), ("reference_text", reference))
        for kind, selected in text_selections:
            if selected:
                candidates.append({"account_id": account_id, "canary_type": kind, "canary_id": selected.get("canary_id", ""), "public_post_text": _public_text(selected), "persona_validator_status": selected.get("account_fit_status", "PASS"), "final_public_post_validator_status": selected.get("validator_status", "PASS"), "internal_leak_status": selected.get("internal_leak_status", ""), "queue_id": selected.get("queue_id", ""), "content_hash": selected.get("content_hash", ""), "recent_post_similarity": selected.get("recent_post_similarity", ""), **_quality_fields(selected)})
        account_posts = {str(row.get("source_post_id", "")): row for row in posts if str(row.get("target_account_id") or row.get("account_id") or "") == account_id}
        media_by_parent = {}
        for item in media:
            media_by_parent.setdefault(str(item.get("source_post_id", "")), []).append(item)
        assets_by_id = {str(row.get("media_id") or row.get("media_asset_id") or ""): row for row in assets}
        # Queue selection is authoritative.  It preserves the fresh batch and
        # avoids letting an older source-media row win merely by sheet order.
        direct_kinds = ("direct_image",) if wave == "first_wave" else ("direct_image", "direct_video")
        for kind in direct_kinds:
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
            candidates.append({"account_id": account_id, "canary_type": kind, "canary_id": matching_queue.get("canary_id", ""), "queue_id": matching_queue.get("queue_id", ""), "source_id": source_id, "rights_status": perm.get("rights_status", ""), "permission_status": perm.get("permission_status", ""), "permission_evidence": perm.get("evidence_reference", ""), "public_post_text": _public_text(matching_queue), "persona_validator_status": matching_queue.get("account_fit_status", ""), "final_public_post_validator_status": matching_queue.get("validator_status", ""), "internal_leak_status": matching_queue.get("internal_leak_status", ""), "publisher_media_type": matching_queue.get("publisher_media_type", ""), "source_post_id": parent.get("source_post_id", ""), "media_asset_id": asset_id, "media_url": url, "content_hash": matching_queue.get("content_hash", ""), "recent_post_similarity": matching_queue.get("recent_post_similarity", ""), "alignment_status": matching_queue.get("alignment_status", ""), "final_alignment_score": matching_queue.get("final_alignment_score", ""), "main_claim_coverage": matching_queue.get("main_claim_coverage", ""), "unsupported_claim_count": matching_queue.get("unsupported_claim_count", ""), "source_copy_similarity": matching_queue.get("source_copy_similarity", ""), "duration_seconds": matching_queue.get("duration_seconds") or asset.get("duration_seconds") or asset.get("duration", ""), "aspect_ratio": matching_queue.get("aspect_ratio") or asset.get("aspect_ratio", ""), **_quality_fields(matching_queue)})
        matching_queue = next((row for row in account_queue if _queue_content_type(row) == "direct_carousel"), {}) if wave != "first_wave" else {}
        parent_id = str(matching_queue.get("source_post_id", "")); parent = account_posts.get(parent_id)
        bundle = sorted(media_by_parent.get(parent_id, []), key=lambda item: int(item.get("media_index") or 0))
        if wave != "first_wave" and matching_queue and parent and len(bundle) >= 2:
            perm = _permission(permissions, str(parent.get("source_id", "")), account_id, "direct")
            urls = [str(item.get("storage_url") or assets_by_id.get(str(item.get("media_asset_id", "")), {}).get("storage_url") or "") for item in bundle]
            if perm and all(urls):
                candidates.append({"account_id": account_id, "canary_type": "direct_carousel", "canary_id": matching_queue.get("canary_id", ""), "queue_id": matching_queue.get("queue_id", ""), "source_id": parent.get("source_id", ""), "rights_status": perm.get("rights_status", ""), "permission_status": perm.get("permission_status", ""), "permission_evidence": perm.get("evidence_reference", ""), "public_post_text": _public_text(matching_queue), "persona_validator_status": matching_queue.get("account_fit_status", ""), "final_public_post_validator_status": matching_queue.get("validator_status", ""), "internal_leak_status": matching_queue.get("internal_leak_status", ""), "publisher_media_type": matching_queue.get("publisher_media_type", ""), "source_post_id": parent_id, "media_asset_ids": [item.get("media_asset_id") or item.get("source_post_media_id", "") for item in bundle], "media_order": [item.get("media_index", "") for item in bundle], "content_hash": matching_queue.get("content_hash", ""), "recent_post_similarity": matching_queue.get("recent_post_similarity", ""), "alignment_status": matching_queue.get("alignment_status", ""), "final_alignment_score": matching_queue.get("final_alignment_score", ""), "main_claim_coverage": matching_queue.get("main_claim_coverage", ""), "unsupported_claim_count": matching_queue.get("unsupported_claim_count", ""), "source_copy_similarity": matching_queue.get("source_copy_similarity", ""), "media_urls": urls, **_quality_fields(matching_queue)})
        account_clips = sorted(
            (clip for clip in clips if wave != "first_wave" and str(clip.get("account_id", "")) == account_id),
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
            candidates.append({"account_id": account_id, "canary_type": "generated_clip", "canary_id": matching_queue.get("canary_id", ""), "queue_id": matching_queue.get("queue_id", ""), "source_id": source_id, "rights_status": perm.get("rights_status", ""), "permission_status": perm.get("permission_status", ""), "permission_evidence": perm.get("evidence_reference", ""), "public_post_text": _public_text(matching_queue), "persona_validator_status": matching_queue.get("account_fit_status", ""), "final_public_post_validator_status": matching_queue.get("validator_status", ""), "internal_leak_status": matching_queue.get("internal_leak_status", ""), "publisher_media_type": matching_queue.get("publisher_media_type", ""), "source_video_id": clip.get("source_video_id", ""), "clip_candidate_id": clip.get("clip_candidate_id", ""), "local_path": asset.get("local_path", "ready"), "start_seconds": clip.get("start_seconds", ""), "end_seconds": clip.get("end_seconds", ""), "content_hash": matching_queue.get("content_hash", ""), "recent_post_similarity": matching_queue.get("recent_post_similarity", ""), "alignment_status": matching_queue.get("alignment_status", ""), "final_alignment_score": matching_queue.get("final_alignment_score", ""), "main_claim_coverage": matching_queue.get("main_claim_coverage", ""), "unsupported_claim_count": matching_queue.get("unsupported_claim_count", ""), "source_copy_similarity": matching_queue.get("source_copy_similarity", ""), "media_asset_id": asset.get("media_id") or asset.get("media_asset_id", ""), "media_url": asset.get("storage_url", ""), "duration_seconds": matching_queue.get("duration_seconds") or clip.get("duration_seconds") or asset.get("duration_seconds") or asset.get("duration", ""), "aspect_ratio": matching_queue.get("aspect_ratio") or clip.get("aspect_ratio") or asset.get("aspect_ratio", ""), **_quality_fields(matching_queue)})
            break
    plan = build_plan(candidates, wave=wave)
    return {
        **plan,
        "status": "LIVE_INVENTORY_PLAN",
        "selected_batch_id": selected_batch_id,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "would_write": False,
        "would_post": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--wave", choices=["all_12", "first_wave"], default="all_12")
    parser.add_argument("--batch-id", default="")
    args = parser.parse_args(); data, source = _rows(args.use_sheets); result = build_inventory(data, wave=args.wave, batch_id=args.batch_id); result["sheets_status"] = source
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"); result["output_path"] = str(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
