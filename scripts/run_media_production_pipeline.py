#!/usr/bin/env python3
"""Run one fully gated approved-media Threads post for liver_manager.

The runner is intentionally single-item and stateful through Sheets. It never
accepts arbitrary accounts or rights values and every external action requires
both the production confirmation flag and its dedicated environment gate.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from config_loader import get_config  # noqa: E402
from cut_approved_clips import build_plan as build_cut_plan, execute_cut  # noqa: E402
from download_approved_media import build_download_plan, execute_download, is_individual_video_url  # noqa: E402
from media_post_validator import validate_media_post  # noqa: E402
from media_growth_schemas import extract_video_id  # noqa: E402
from process_threads_queue import process_one  # noqa: E402
from public_post_quality import final_public_post_validator, public_preview  # noqa: E402
from sheets_client import TAB_DEFINITIONS, SheetsClient  # noqa: E402
from upload_media_assets import build_upload_plan, execute_cloudinary_uploads  # noqa: E402

MEDIA_CONFIG = ROOT / "config/media_growth_engine.json"
AUTONOMOUS_CONFIG = ROOT / "config/autonomous_mode.json"
JST = timezone(timedelta(hours=9))
APPROVED_RIGHTS = {"owned", "licensed", "approved_creator_clip"}
REQUIRED_ENV = (
    "ALLOW_VIDEO_DOWNLOAD",
    "ALLOW_VIDEO_CUT",
    "ALLOW_CLOUDINARY_UPLOAD",
    "ALLOW_MEDIA_POSTS",
    "ALLOW_REAL_THREADS_VIDEO_POST",
    "PUBLISH_ENABLED",
    "ALLOW_REAL_THREADS_POST",
)


def _true(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _records(client: SheetsClient, logical: str) -> list[dict[str, Any]]:
    client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    return [dict(row) for row in client._ws(logical).get_all_records()]


def _append(client: SheetsClient, logical: str, row: dict[str, Any]) -> None:
    client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    ws = client._ws(logical)
    headers = ws.row_values(1)
    ws.append_row([str(row.get(h, "")) for h in headers], value_input_option="USER_ENTERED")


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _today_posts(rows: list[dict[str, Any]], account_id: str) -> list[dict[str, Any]]:
    today = datetime.now(JST).date()
    result = []
    for row in rows:
        if str(row.get("account_id", "")) != account_id or str(row.get("status", "")).upper() != "POSTED":
            continue
        posted = _parse_time(row.get("posted_at"))
        if posted and posted.astimezone(JST).date() == today:
            result.append(row)
    return result


def select_candidate(
    clips: list[dict[str, Any]],
    source_videos: list[dict[str, Any]],
    posted_results: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[str]]:
    sources = {str(row.get("source_video_id", "")): row for row in source_videos}
    posted_clip_ids = {str(row.get("clip_candidate_id", "")) for row in posted_results if row.get("clip_candidate_id")}
    reasons: list[str] = []
    eligible = []
    for clip in clips:
        clip_id = str(clip.get("clip_candidate_id") or clip.get("clip_id") or "")
        source_video_id = str(clip.get("source_video_id") or clip.get("reference_post_id") or "")
        source_video = sources.get(source_video_id)
        if not source_video:
            reasons.append(f"{clip_id}:source_video_missing")
            continue
        rights = str(clip.get("rights_status") or source_video.get("rights_status") or "").lower()
        permission = str(clip.get("permission_status") or source_video.get("permission_status") or "").lower()
        status = str(clip.get("clip_status") or clip.get("reviewer_status") or "").upper()
        url = str(source_video.get("canonical_video_url") or "")
        if rights not in APPROVED_RIGHTS or permission != "approved":
            reasons.append(f"{clip_id}:rights_or_permission_blocked")
            continue
        if status not in {"READY", "AUTO_APPROVED"}:
            reasons.append(f"{clip_id}:clip_not_ready")
            continue
        if clip_id in posted_clip_ids:
            reasons.append(f"{clip_id}:already_posted")
            continue
        if not is_individual_video_url(url):
            reasons.append(f"{clip_id}:individual_video_url_required")
            continue
        video_id = extract_video_id(url, str(source_video.get("platform", "")))
        if str(source_video.get("platform", "")).lower() == "youtube" and len(video_id) != 11:
            reasons.append(f"{clip_id}:planned_or_invalid_video_id")
            continue
        if str(source_video.get("platform", "")).lower() == "tiktok" and not video_id.isdigit():
            reasons.append(f"{clip_id}:planned_or_invalid_video_id")
            continue
        text = str(clip.get("public_post_text") or "")
        if final_public_post_validator(text, "liver_manager")["status"] != "PASS":
            reasons.append(f"{clip_id}:public_post_validator_blocked")
            continue
        eligible.append((clip, source_video))
    if not eligible:
        return None, None, reasons
    eligible.sort(key=lambda pair: (
        0 if str(pair[1].get("platform", "")).lower() == "youtube" else 1,
        -float(pair[0].get("confidence_score") or pair[0].get("clip_score") or 0),
        str(pair[0].get("clip_id", "")),
    ))
    return eligible[0][0], eligible[0][1], reasons


def build_plan(*, apply: bool, confirm: bool, client: SheetsClient | None = None) -> dict[str, Any]:
    media_cfg = _load(MEDIA_CONFIG)
    autonomous_cfg = _load(AUTONOMOUS_CONFIG)
    blocked = []
    if autonomous_cfg.get("kill_switch"):
        blocked.append("kill_switch=true")
    if not media_cfg.get("media_public_post_auto_enabled"):
        blocked.append("media_public_post_auto_disabled")
    if apply and not confirm:
        blocked.append("--apply requires --confirm-production-media")
    if apply:
        blocked.extend(f"{name}=true required" for name in REQUIRED_ENV if not _true(os.environ.get(name)))
    if not client:
        return {
            "status": "BLOCKED" if blocked else "PLAN_ONLY",
            "account_id": "liver_manager",
            "apply": apply,
            "selected_clip_candidate_id": "",
            "public_post_preview": "",
            "would_download": False,
            "would_cut": False,
            "would_upload": False,
            "would_post_video": False,
            "blocked_reasons": blocked,
        }

    source_videos = _records(client, "source_videos")
    clips = _records(client, "video_clip_candidates")
    posted = _records(client, "posted_results")
    today_posts = _today_posts(posted, "liver_manager")
    daily_cap = int(autonomous_cfg.get("daily_post_cap_per_account", 5))
    media_cap = int(media_cfg.get("media_daily_post_cap", 1))
    media_today = [row for row in today_posts if _true(row.get("media_used"))]
    if len(today_posts) >= daily_cap:
        blocked.append("daily_post_cap_reached")
    if len(media_today) >= media_cap:
        blocked.append("media_daily_post_cap_reached")
    clip, source_video, skipped = select_candidate(clips, source_videos, posted)
    if not clip or not source_video:
        blocked.append("no_eligible_media_candidate")
    text = str((clip or {}).get("public_post_text") or "")
    return {
        "status": "BLOCKED" if blocked and apply else "NO_POST" if "no_eligible_media_candidate" in blocked else "PLAN_ONLY",
        "account_id": "liver_manager",
        "apply": apply,
        "selected_clip_candidate_id": str((clip or {}).get("clip_candidate_id") or (clip or {}).get("clip_id") or ""),
        "selected_source_video_id": str((source_video or {}).get("source_video_id") or ""),
        "selected_clip": clip or {},
        "selected_source_video": source_video or {},
        "public_post_preview": public_preview(text),
        "today_post_count": len(today_posts),
        "today_media_post_count": len(media_today),
        "daily_post_cap": daily_cap,
        "media_daily_post_cap": media_cap,
        "would_download": bool(apply and confirm and not blocked),
        "would_cut": bool(apply and confirm and not blocked),
        "would_upload": bool(apply and confirm and not blocked),
        "would_post_video": bool(apply and confirm and not blocked),
        "blocked_reasons": blocked,
        "skipped_candidates": skipped[:20],
    }


def execute(plan: dict[str, Any], client: SheetsClient) -> dict[str, Any]:
    if plan.get("status") == "BLOCKED":
        return plan
    clip = dict(plan["selected_clip"])
    source_video = dict(plan["selected_source_video"])
    clip_id = str(clip.get("clip_candidate_id") or clip.get("clip_id"))
    source_video_id = str(source_video.get("source_video_id"))

    download_args = SimpleNamespace(
        source_video_id=source_video_id,
        source_video_row=source_video,
        source_videos_json="",
        source_url="",
        rights_status=source_video.get("rights_status", ""),
        download=True,
        confirm_download=True,
        dry_run=False,
    )
    download = execute_download(build_download_plan(download_args))
    if download.get("status") != "DOWNLOADED":
        client.save_source_video({**source_video, "download_status": "FAILED", "skip_reason": ",".join(download.get("blocked_reasons", []))})
        client.update_video_clip_candidate(clip_id, clip_status="BLOCKED", reviewer_status="BLOCKED", post_status="FAILED_DOWNLOAD")
        return {**plan, "status": "FAILED_DOWNLOAD", "download_result": download, "would_download": False}
    local_source = str(download["download_result"]["local_path"])
    client.save_source_video({**source_video, "download_status": "DOWNLOADED", "local_path": local_source, "downloaded_at": datetime.now(timezone.utc).isoformat()})

    cut_args = SimpleNamespace(
        clip_candidate_id=clip_id,
        clip_candidate_row=clip,
        clip_candidates_json="",
        input_path=local_source,
        rights_status=clip.get("rights_status", ""),
        start_seconds=float(clip.get("start_seconds") or clip.get("start_time") or 0),
        end_seconds=float(clip.get("end_seconds") or clip.get("end_time") or 0),
        vertical=True,
        burn_subtitles=False,
        cut=True,
        confirm_cut=True,
        dry_run=False,
    )
    cut = execute_cut(build_cut_plan(cut_args))
    if cut.get("status") != "CUT":
        client.update_video_clip_candidate(clip_id, clip_status="BLOCKED", reviewer_status="BLOCKED", cut_status="FAILED", notes=",".join(cut.get("blocked_reasons", [])))
        return {**plan, "status": "FAILED_CUT", "cut_result": cut, "would_cut": False}
    asset = dict(cut["media_asset_result"])
    asset["account_id"] = "liver_manager"
    asset["clip_candidate_id"] = clip_id

    upload_args = SimpleNamespace(upload=True, confirm_upload=True, dry_run=False)
    upload = execute_cloudinary_uploads(build_upload_plan(upload_args, [asset]))
    if upload.get("status") != "UPLOADED":
        client.update_video_clip_candidate(clip_id, clip_status="BLOCKED", reviewer_status="BLOCKED", cut_status="DONE", local_clip_path=asset["local_path"], upload_status="FAILED")
        return {**plan, "status": "FAILED_UPLOAD", "upload_result": upload, "would_upload": False}
    uploaded = dict(upload["uploaded_assets"][0])
    media_id = str(uploaded["media_asset_id"])
    media_url = str(uploaded["cloudinary_url"])

    media_row = {
        "media_id": media_id,
        "account_id": "liver_manager",
        "reference_post_id": source_video_id,
        "source_platform": source_video.get("platform", ""),
        "source_post_url": source_video.get("canonical_video_url", ""),
        "original_media_url": source_video.get("canonical_video_url", ""),
        "storage_provider": "cloudinary",
        "storage_url": media_url,
        "cloudinary_public_id": uploaded.get("cloudinary_public_id", ""),
        "media_type": "video",
        "mime_type": "video/mp4",
        "duration": asset.get("duration_seconds", ""),
        "duration_seconds": asset.get("duration_seconds", ""),
        "reuse_status": "approved_creator_clip",
        "rights_status": clip.get("rights_status", ""),
        "permission_status": clip.get("permission_status", ""),
        "aspect_ratio": "9:16",
        "video_clip_id": clip_id,
        "local_path": asset.get("local_path", ""),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "upload_status": "UPLOADED",
        "allow_download": "true",
        "allow_cut": "true",
        "allow_upload": "true",
        "notes": "Approved creator clip produced by production media pipeline.",
    }
    existing_media_ids = {str(row.get("media_id", "")) for row in _records(client, "media_assets")}
    if media_id not in existing_media_ids:
        _append(client, "media_assets", media_row)

    text = str(clip.get("public_post_text") or "")
    validation = validate_media_post({
        "rights_status": clip.get("rights_status", ""),
        "permission_status": clip.get("permission_status", ""),
        "media_url": media_url,
        "media_asset_id": media_id,
        "platform": "threads",
        "account_id": "liver_manager",
        "media_type": "video",
        "duration_seconds": asset.get("duration_seconds", 0),
        "aspect_ratio": "9:16",
        "public_post_text": text,
    })
    if validation["status"] != "PASS":
        client.update_video_clip_candidate(clip_id, clip_status="BLOCKED", reviewer_status="BLOCKED", cut_status="DONE", upload_status="UPLOADED", storage_url=media_url, post_status="BLOCKED")
        return {**plan, "status": "BLOCKED_MEDIA_VALIDATOR", "media_validation": validation}

    queue_id = f"media_q_{clip_id}"
    queue_row = {
        "queue_id": queue_id,
        "account_id": "liver_manager",
        "target_account_id": "liver_manager",
        "platform": "threads",
        "priority": "1",
        "status": "READY",
        "auto_publish": "true",
        "generation_mode": "approved_media_growth",
        "media_asset_id": media_id,
        "video_clip_id": clip_id,
        "source_video_id": source_video_id,
        "clip_candidate_id": clip_id,
        "rights_status": clip.get("rights_status", ""),
        "permission_status": clip.get("permission_status", ""),
        "rights_review_required": "false",
        "media_reuse_risk": "low",
        "source_video_url": source_video.get("canonical_video_url", ""),
        "source_time_range": f"{clip.get('start_seconds', clip.get('start_time', ''))}-{clip.get('end_seconds', clip.get('end_time', ''))}",
        "public_post_text": text,
        "validator_status": "PASS",
        "internal_leak_status": "PASS",
        "account_fit_status": "PASS",
        "media_url": media_url,
        "media_status": "UPLOADED",
        "media_required": "true",
        "duration_seconds": asset.get("duration_seconds", ""),
        "aspect_ratio": "9:16",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    existing_queue_ids = {str(row.get("queue_id", "")) for row in _records(client, "queue")}
    if queue_id not in existing_queue_ids:
        _append(client, "queue", queue_row)
    result = process_one(client, queue_row, dry_run=False, confirm_real_post=True)
    final_status = str(result.get("status", ""))
    client.update_video_clip_candidate(
        clip_id,
        cut_status="DONE",
        local_clip_path=asset.get("local_path", ""),
        clip_media_asset_id=media_id,
        media_asset_id=media_id,
        storage_url=media_url,
        upload_status="UPLOADED",
        post_status="POSTED" if final_status == "POSTED" else final_status,
        reviewer_status="AUTO_APPROVED" if final_status == "POSTED" else "BLOCKED",
        clip_status="POSTED" if final_status == "POSTED" else "BLOCKED",
    )
    if final_status == "POSTED":
        client.save_source_video({**source_video, "download_status": "DOWNLOADED", "cut_status": "CUT", "upload_status": "UPLOADED", "post_status": "POSTED", "processed_at": datetime.now(timezone.utc).isoformat()})
    return {
        **plan,
        "status": final_status,
        "queue_id": queue_id,
        "media_asset_id": media_id,
        "post_result": result,
        "would_download": False,
        "would_cut": False,
        "would_upload": False,
        "would_post_video": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="run one approved media production post")
    parser.add_argument("--account-id", default="liver_manager", choices=["liver_manager"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-production-media", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()

    client = None
    if args.use_sheets:
        cfg = get_config()
        client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    plan = build_plan(apply=args.apply, confirm=args.confirm_production_media, client=client)
    if args.apply and args.confirm_production_media and client and plan.get("status") not in {"BLOCKED", "NO_POST"}:
        plan = execute(plan, client)
    safe = {k: v for k, v in plan.items() if k not in {"selected_clip", "selected_source_video"}}
    print(json.dumps(safe, ensure_ascii=False, indent=2))
    return 1 if str(plan.get("status", "")).startswith(("FAILED", "BLOCKED")) else 0


if __name__ == "__main__":
    raise SystemExit(main())
