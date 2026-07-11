#!/usr/bin/env python3
"""Dry-run first Media Growth Engine for approved liver_manager video sources."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from media.rights_policy import rights_allows_media_use  # noqa: E402
from discover_approved_source_videos import build_discovery_plan, load_existing_source_videos  # noqa: E402
from config_loader import get_config  # noqa: E402
from media_growth_schemas import (  # noqa: E402
    build_clip_candidate_for_video,
    build_media_pdca_records,
    build_media_post_queue_item,
    build_transcript_row,
    clip_count_for_video,
    clips_overlap,
    extract_video_id,
)
from public_post_quality import final_public_post_validator, generate_reader_facing_post, public_preview  # noqa: E402
from sheets_client import TAB_DEFINITIONS, SheetsClient  # noqa: E402

SOURCES_FILE = ROOT / "config/source_accounts/default_sources.json"
CONFIG_FILE = ROOT / "config/media_growth_engine.json"


def load_sources() -> list[dict[str, Any]]:
    return json.loads(SOURCES_FILE.read_text(encoding="utf-8"))["sources"]


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


def load_source_videos_from_sheets() -> tuple[SheetsClient, list[dict[str, Any]]]:
    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    client._ensure_tab("source_videos", TAB_DEFINITIONS["source_videos"])
    client._ensure_tab("video_clip_candidates", TAB_DEFINITIONS["video_clip_candidates"])
    return client, [dict(r) for r in client._ws("source_videos").get_all_records()]


def _clip_row_for_sheets(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "clip_id": row.get("clip_id") or row.get("clip_candidate_id", ""),
        "reference_post_id": row.get("source_video_id", ""),
        "transcript_id": f"tr_{row.get('source_video_id', '')}",
        "source_platform": row.get("platform", ""),
        "source_video_url": row.get("canonical_video_url") or row.get("source_video_url", ""),
        "start_time": row.get("start_time", row.get("start_seconds", "")),
        "end_time": row.get("end_time", row.get("end_seconds", "")),
        "clip_title": row.get("title", ""),
        "hook": row.get("hook_text", ""),
        "why_it_works": row.get("reason", ""),
        "target_persona": row.get("target_audience", ""),
        "threads_post_angle": row.get("expected_post_angle", ""),
        "reuse_status": "approved_creator_clip",
        "media_reuse_risk": "low",
        "imitation_risk": "low",
        "confidence_score": row.get("clip_score", ""),
        "source_video_id": row.get("source_video_id", ""),
        "video_id": row.get("video_id", ""),
        "canonical_video_url": row.get("canonical_video_url", ""),
        "clip_candidate_id": row.get("clip_candidate_id", ""),
        "duplicate_clip_key": row.get("duplicate_clip_key", ""),
        "reviewer_status": row.get("reviewer_status", ""),
        "public_post_text": row.get("public_post_text", ""),
        "public_post_validator_status": row.get("public_post_validator_status", ""),
        "start_seconds": row.get("start_seconds", ""),
        "end_seconds": row.get("end_seconds", ""),
        "aspect_ratio": "9:16",
        "upload_status": row.get("upload_status", "NOT_UPLOADED"),
        "post_status": row.get("post_status", "NOT_POSTED"),
        "notes": "Auto-saved by run_media_growth_engine; production execution remains rights/env gated.",
    }


def append_clip_candidates_to_sheets(client: SheetsClient, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    ws = client._ws("video_clip_candidates")
    headers = ws.row_values(1)
    existing = {str(r.get("clip_id") or r.get("clip_candidate_id", "")) for r in ws.get_all_records()}
    to_add = []
    for row in rows:
        mapped = _clip_row_for_sheets(row)
        clip_id = str(mapped.get("clip_id", ""))
        if clip_id and clip_id not in existing:
            to_add.append(mapped)
            existing.add(clip_id)
    if not to_add:
        return 0
    ws.append_rows(
        [[str(row.get(h, "")) for h in headers] for row in to_add],
        value_input_option="USER_ENTERED",
    )
    return len(to_add)


def is_channel_or_account_url(source: dict[str, Any]) -> bool:
    source_type = str(source.get("source_type", "")).lower()
    url = str(source.get("source_url", ""))
    return source_type in {"channel", "account"} or (source.get("source_platform") == "tiktok" and "/video/" not in url)


def permission_ok(source: dict[str, Any]) -> bool:
    return (
        source.get("permission_status") == "approved"
        and bool(source.get("permission_evidence_type"))
        and bool(source.get("permission_evidence_note"))
        and source.get("permission_approved_by") == "user"
    )


def is_real_discovered_video(row: dict[str, Any]) -> bool:
    if str(row.get("discovery_status", "")).upper() == "PLANNED_ONLY":
        return False
    if "video candidate" in str(row.get("title", "")).lower() or str(row.get("description_preview", "")) == "candidate metadata only":
        return False
    platform = str(row.get("platform", "")).lower()
    video_id = extract_video_id(str(row.get("canonical_video_url", "")), platform)
    if platform == "youtube":
        return len(video_id) == 11
    if platform == "tiktok":
        return bool(video_id and video_id.isdigit())
    return bool(video_id)


def select_sources(account_id: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    allowed_ids = set(config.get("allowed_source_ids", []))
    rows = []
    for source in load_sources():
        targets = source.get("target_account_ids") or [source.get("target_account_id")]
        if account_id not in targets:
            continue
        if source.get("source_id") not in allowed_ids:
            continue
        rows.append(source)
    return rows


def build_media_growth_plan(
    account_id: str,
    *,
    apply: bool = False,
    confirm_media_growth: bool = False,
    existing_source_videos: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    config = load_config()
    selected = select_sources(account_id, config)
    blocked: list[str] = []
    if not config.get("media_growth_engine_enabled"):
        blocked.append("media_growth_engine_disabled")
    if account_id != config.get("target_account_id"):
        blocked.append("account_not_allowed")
    if apply and not confirm_media_growth:
        blocked.append("--apply requires --confirm-media-growth")
    source_results = []
    transcript_rows = []
    clip_candidates = []
    media_post_queue_preview = []
    for source in selected:
        rights = str(source.get("rights_status", ""))
        source_blocked = []
        if not rights_allows_media_use(rights):
            source_blocked.append("rights_status_not_media_approved")
        if not permission_ok(source):
            source_blocked.append("permission_evidence_missing")
        if source.get("source_id") not in config.get("allowed_source_ids", []):
            source_blocked.append("source_not_allowed")
        transcript_status = "PLAN_ONLY"
        if is_channel_or_account_url(source):
            transcript_status = "INDIVIDUAL_VIDEO_URL_REQUIRED"
        transcript_rows.append(build_transcript_row(source, status=transcript_status, title=source.get("source_name", "")))
        source_results.append({
            "source_id": source.get("source_id"),
            "source_url": source.get("source_url"),
            "platform": source.get("source_platform"),
            "rights_check": "PASS" if rights_allows_media_use(rights) else "BLOCKED",
            "permission_evidence": "PASS" if permission_ok(source) else "BLOCKED",
            "metadata_status": "PLAN_ONLY",
            "transcript_status": transcript_status,
            "clip_candidate_count": 0,
            "blocked_reasons": source_blocked,
        })

    existing_source_videos = existing_source_videos if existing_source_videos is not None else load_existing_source_videos()
    discovery_plan = build_discovery_plan(account_id, existing_source_videos=existing_source_videos)
    planned_source_videos = [row for row in existing_source_videos if is_real_discovered_video(row)]
    # Preserve deterministic mock candidates only when no registry was supplied at all.
    if not existing_source_videos:
        planned_source_videos = []
        for result in discovery_plan.get("source_results", []):
            source = next((s for s in selected if s.get("source_id") == result.get("source_id")), None)
            if not source or result.get("blocked_reasons"):
                continue
            from media_growth_schemas import build_source_video  # local import keeps public API stable
            for i in range(1, min(int(config.get("max_new_videos_per_source_per_run", 10)), 3) + 1):
                planned_source_videos.append(build_source_video(source, i))

    source_by_id = {str(s.get("source_id", "")): s for s in selected}
    output = generate_reader_facing_post(account_id, index=1)
    public_text = str(output["public_post_text"])
    validation = final_public_post_validator(public_text, account_id)
    existing_clips: list[dict[str, Any]] = []
    for video_index, source_video in enumerate(planned_source_videos, start=1):
        source = source_by_id.get(str(source_video.get("source_id", "")))
        if not source:
            continue
        duration = float(source_video.get("duration_seconds") or 0)
        if duration < float(config.get("clip_duration_min_seconds", 8)):
            source_video["skip_reason"] = "duration_metadata_required_or_too_short"
            source_video["analysis_status"] = "SKIPPED"
            continue
        count = clip_count_for_video(source_video, config)
        video_candidates = []
        for i in range(1, count + 1):
            clip_output = generate_reader_facing_post(account_id, index=(video_index - 1) * 3 + i)
            clip_public_text = str(clip_output["public_post_text"])
            clip_validation = final_public_post_validator(clip_public_text, account_id)
            cand = build_clip_candidate_for_video(
                source,
                source_video,
                i,
                config=config,
                public_post_text=clip_public_text,
                validator_status=clip_validation["status"],
            )
            if any(clips_overlap(cand, old, config.get("clip_overlap_tolerance_seconds", 2)) for old in existing_clips):
                cand["clip_status"] = "SKIPPED"
                cand["reviewer_status"] = "SKIPPED"
                cand["selected_reason"] = "overlap_blocked"
                continue
            existing_clips.append(cand)
            if (
                config.get("auto_approve_clip_candidates")
                and clip_validation["status"] == "PASS"
                and float(cand.get("clip_score") or 0) >= float(config.get("min_auto_clip_score", 80))
                and cand.get("rights_status") in set(config.get("allowed_rights_statuses", []))
                and cand.get("permission_status") == "approved"
            ):
                cand["reviewer_status"] = "AUTO_APPROVED"
                cand["clip_status"] = "READY"
            video_candidates.append(cand)
            clip_candidates.append(cand)
        source_video["clip_candidate_count"] = len(video_candidates)
        source_video["analysis_status"] = "ANALYZED"
        source_video["discovery_status"] = "CLIP_CANDIDATES_READY" if video_candidates else source_video.get("discovery_status", "DISCOVERED")
    media_post_queue_preview = [build_media_post_queue_item(c) for c in clip_candidates[:3]]
    for result in source_results:
        result["clip_candidate_count"] = sum(1 for c in clip_candidates if c.get("source_id") == result.get("source_id"))
    media_plan = {
        "download_enabled": bool(config.get("download_enabled")),
        "cut_enabled": bool(config.get("cut_enabled")),
        "upload_enabled": bool(config.get("upload_enabled")),
        "video_post_enabled": bool(config.get("video_post_enabled")),
        "cloudinary_upload_enabled": bool(config.get("cloudinary_upload_enabled")),
        "threads_video_post_enabled": bool(config.get("threads_video_post_enabled")),
        "schedule_enabled": bool(config.get("media_schedule_enabled", False)),
        "manual_apply_only": not bool(config.get("media_schedule_enabled", False)),
        "media_public_post_auto_enabled": bool(config.get("media_public_post_auto_enabled", False)),
    }
    pdca_records = build_media_pdca_records(clip_candidates[0]) if clip_candidates else {}
    if validation["status"] != "PASS":
        blocked.append("public_post_validator_blocked")
    return {
        "status": "PLAN_ONLY" if not blocked else "BLOCKED",
        "account_id": account_id,
        "selected_sources": [{"source_id": s.get("source_id"), "source_url": s.get("source_url"), "rights_status": s.get("rights_status")} for s in selected],
        "rights_check": "PASS" if all(r["rights_check"] == "PASS" for r in source_results) else "BLOCKED",
        "permission_evidence": "PASS" if all(r["permission_evidence"] == "PASS" for r in source_results) else "BLOCKED",
        "source_results": source_results,
        "source_videos_source": "existing_source_videos" if existing_source_videos else "discovery_plan",
        "source_video_count": len(planned_source_videos),
        "source_videos_preview": planned_source_videos[:5],
        "video_transcripts_schema": transcript_rows,
        "clip_candidate_count": len(clip_candidates),
        "top_clip_candidates": clip_candidates[:5],
        "media_post_queue_preview": media_post_queue_preview,
        "public_post_preview": public_preview(public_text),
        "final_public_post_validator": validation["status"],
        "media_plan": media_plan,
        "would_download": False,
        "would_cut": False,
        "would_upload": False,
        "would_post_video": False,
        "pdca_plan": pdca_records,
        "blocked_reasons": blocked,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="run media growth engine")
    parser.add_argument("--account-id", default="liver_manager", choices=["liver_manager", "night_scout", "beauty_account"])
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-media-growth", action="store_true")
    parser.add_argument("--use-sheets", action="store_true", help="read source_videos and save clip candidates to Sheets")
    args = parser.parse_args()
    client = None
    existing = None
    if args.use_sheets and (args.apply or args.dry_run):
        client, existing = load_source_videos_from_sheets()
    plan = build_media_growth_plan(
        args.account_id,
        apply=args.apply,
        confirm_media_growth=args.confirm_media_growth,
        existing_source_videos=existing,
    )
    if args.apply and args.confirm_media_growth and args.use_sheets and client and plan["status"] != "BLOCKED":
        added = append_clip_candidates_to_sheets(client, plan.get("top_clip_candidates", []))
        plan["saved_clip_candidate_count"] = added
        plan["clip_candidate_save_status"] = "SAVED" if added else "NO_NEW_ROWS"
    elif args.apply and args.confirm_media_growth and not args.use_sheets and plan["status"] != "BLOCKED":
        plan["clip_candidate_save_status"] = "SKIPPED_USE_SHEETS_REQUIRED"
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 1 if plan["status"] == "BLOCKED" and args.apply else 0


if __name__ == "__main__":
    raise SystemExit(main())
