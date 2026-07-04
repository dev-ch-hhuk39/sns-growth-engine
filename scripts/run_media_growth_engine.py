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
from media_growth_schemas import build_clip_candidate, build_media_pdca_records, build_transcript_row  # noqa: E402
from public_post_quality import final_public_post_validator, generate_reader_facing_post, public_preview  # noqa: E402

SOURCES_FILE = ROOT / "config/source_accounts/default_sources.json"
CONFIG_FILE = ROOT / "config/media_growth_engine.json"


def load_sources() -> list[dict[str, Any]]:
    return json.loads(SOURCES_FILE.read_text(encoding="utf-8"))["sources"]


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


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


def build_media_growth_plan(account_id: str, *, apply: bool = False, confirm_media_growth: bool = False) -> dict[str, Any]:
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
        per_source_candidates = []
        if not source_blocked:
            for i in range(1, int(config.get("max_clips_per_source_per_run", 3)) + 1):
                cand = build_clip_candidate(source, i, has_transcript=False)
                cand["download_status"] = "INDIVIDUAL_VIDEO_URL_REQUIRED" if is_channel_or_account_url(source) else "NOT_DOWNLOADED"
                per_source_candidates.append(cand)
                clip_candidates.append(cand)
        source_results.append({
            "source_id": source.get("source_id"),
            "source_url": source.get("source_url"),
            "platform": source.get("source_platform"),
            "rights_check": "PASS" if rights_allows_media_use(rights) else "BLOCKED",
            "permission_evidence": "PASS" if permission_ok(source) else "BLOCKED",
            "metadata_status": "PLAN_ONLY",
            "transcript_status": transcript_status,
            "clip_candidate_count": len(per_source_candidates),
            "blocked_reasons": source_blocked,
        })
    output = generate_reader_facing_post(account_id, index=1)
    public_text = str(output["public_post_text"])
    validation = final_public_post_validator(public_text, account_id)
    media_plan = {
        "download_enabled": bool(config.get("download_enabled")),
        "cut_enabled": bool(config.get("cut_enabled")),
        "upload_enabled": bool(config.get("upload_enabled")),
        "video_post_enabled": bool(config.get("video_post_enabled")),
        "cloudinary_upload_enabled": bool(config.get("cloudinary_upload_enabled")),
        "threads_video_post_enabled": bool(config.get("threads_video_post_enabled")),
        "schedule_enabled": False,
        "manual_apply_only": True,
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
        "video_transcripts_schema": transcript_rows,
        "clip_candidate_count": len(clip_candidates),
        "top_clip_candidates": clip_candidates[:5],
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
    args = parser.parse_args()
    plan = build_media_growth_plan(args.account_id, apply=args.apply, confirm_media_growth=args.confirm_media_growth)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 1 if plan["status"] == "BLOCKED" and args.apply else 0


if __name__ == "__main__":
    raise SystemExit(main())
