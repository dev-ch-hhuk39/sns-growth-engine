#!/usr/bin/env python3
"""Run one fully gated approved-media Threads post for an enabled account.

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
from content_schedule import slot_by_id  # noqa: E402
from content_slot_runs import build_slot_run, upsert_slot_run  # noqa: E402
from cut_approved_clips import build_plan as build_cut_plan, execute_cut  # noqa: E402
from download_approved_media import build_download_plan, execute_download, is_individual_video_url  # noqa: E402
from media_post_validator import validate_media_post  # noqa: E402
from media_growth_schemas import build_media_pdca_records, extract_video_id  # noqa: E402
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
PREPARE_REQUIRED_ENV = (
    "ALLOW_VIDEO_DOWNLOAD",
    "ALLOW_VIDEO_CUT",
    "ALLOW_CLOUDINARY_UPLOAD",
)
SAVED_MEDIA_POST_REQUIRED_ENV = (
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


def _record_media_slot_result(plan: dict[str, Any], client: SheetsClient, result: dict[str, Any]) -> dict[str, Any]:
    slot_id = str(plan.get("slot_id", ""))
    if not slot_id:
        return {"status": "SKIPPED", "reason": "slot_id_not_provided"}
    posted = str(result.get("status", "")) == "POSTED"
    row = build_slot_run(
        str(plan["account_id"]),
        slot_id,
        status="POSTED_PRIMARY" if posted else "FAILED",
        actual_post_type="generated_clip_media",
        fallback_level=0,
        no_post_reason="" if posted else str(result.get("reason", result.get("status", "media_post_failed"))),
        queue_id=result.get("queue_id", ""),
        result_id=result.get("result_id", ""),
        post_url=result.get("post_url", ""),
        media_asset_id=result.get("media_asset_id", ""),
        source_video_id=plan.get("selected_source_video_id", ""),
        actual_posted_at=datetime.now(timezone.utc).isoformat() if posted else "",
    )
    return upsert_slot_run(client, row)


def _save_media_pdca_records(
    client: SheetsClient,
    *,
    clip: dict[str, Any],
    source_video: dict[str, Any],
    media_asset_id: str,
    post_result: dict[str, Any],
) -> dict[str, int]:
    """Persist one media-post baseline without fabricating metrics.

    The normal publisher already saves `posted_results`. These media-specific
    records provide the join keys needed by later metrics/clip analysis, while
    intentionally leaving metric values blank and PENDING until collected.
    """
    clip_id = str(clip.get("clip_candidate_id") or clip.get("clip_id") or "")
    result_id = str(post_result.get("result_id") or "")
    created = datetime.now(timezone.utc).isoformat()
    records = build_media_pdca_records(clip, media_asset_id)
    media_result_id = f"mpr_{clip_id}"
    records["media_post_results"].update({
        "media_post_result_id": media_result_id,
        "result_id": result_id,
        "queue_id": post_result.get("queue_id", ""),
        "source_video_id": source_video.get("source_video_id", ""),
        "external_post_id": post_result.get("external_post_id", ""),
        "post_url": post_result.get("post_url", ""),
        "posted_text": clip.get("public_post_text", ""),
        "status": "POSTED",
        "metrics_status": "PENDING",
        "posted_at": created,
        "updated_at": created,
        "notes": "Metrics remain blank until a collector reports them.",
    })
    records["media_metrics"].update({
        "media_metrics_id": f"mm_{clip_id}",
        "media_post_result_id": media_result_id,
        "result_id": result_id,
        "account_id": clip.get("account_id", ""),
        "platform": "threads",
        "media_asset_id": media_asset_id,
        "post_url": post_result.get("post_url", ""),
        "metrics_status": "PENDING",
        "source": "pending_collection",
        "confidence": "",
        "error_reason": "",
        "collected_at": "",
        "created_at": created,
        "updated_at": created,
    })
    records["clip_performance"].update({
        "clip_performance_id": f"cp_{clip_id}",
        "media_post_result_id": media_result_id,
        "result_id": result_id,
        "account_id": clip.get("account_id", ""),
        "platform": "threads",
        "source_video_id": source_video.get("source_video_id", ""),
        "media_asset_id": media_asset_id,
        "status": "PENDING_METRICS",
        "posted_at": created,
        "updated_at": created,
        "notes": "No subtitle burn-in; clip performance awaits measured metrics.",
    })

    saved = 0
    for logical, row in ((name, records[name]) for name in ("media_post_results", "media_metrics", "clip_performance")):
        existing = _records(client, logical)
        if any(str(item.get("clip_candidate_id", "")) == clip_id for item in existing):
            continue
        _append(client, logical, row)
        saved += 1
    return {"saved": saved, "skipped": 3 - saved}


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
    account_id: str = "liver_manager",
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
        candidate_account = str(clip.get("account_id") or source_video.get("account_id") or "")
        if candidate_account and candidate_account != account_id:
            reasons.append(f"{clip_id}:account_not_targeted")
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
        if not _true(clip.get("transcript_grounded")):
            reasons.append(f"{clip_id}:transcript_grounding_required")
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
        if final_public_post_validator(text, account_id)["status"] != "PASS":
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


def select_saved_media_candidate(
    clips: list[dict[str, Any]],
    source_videos: list[dict[str, Any]],
    media_assets: list[dict[str, Any]],
    posted_results: list[dict[str, Any]],
    account_id: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None, list[str]]:
    """Select one uploaded-but-never-posted approved asset for a timed slot."""
    clips_by_id = {str(row.get("clip_candidate_id") or row.get("clip_id") or ""): row for row in clips}
    videos_by_id = {str(row.get("source_video_id", "")): row for row in source_videos}
    posted_clips = {str(row.get("clip_candidate_id", "")) for row in posted_results if row.get("clip_candidate_id")}
    posted_assets = {str(row.get("media_asset_id", "") or row.get("media_id", "")) for row in posted_results}
    reasons: list[str] = []
    candidates: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for asset in media_assets:
        media_id = str(asset.get("media_asset_id") or asset.get("media_id") or "")
        clip_id = str(asset.get("clip_candidate_id") or asset.get("video_clip_id") or "")
        clip = clips_by_id.get(clip_id)
        source_video = videos_by_id.get(str((clip or {}).get("source_video_id") or asset.get("source_video_id") or ""))
        if str(asset.get("account_id", "")) != account_id:
            continue
        if not clip or not source_video:
            reasons.append(f"{media_id}:clip_or_source_video_missing")
            continue
        if media_id in posted_assets or clip_id in posted_clips:
            reasons.append(f"{media_id}:already_posted")
            continue
        if str(asset.get("upload_status", "")).upper() != "UPLOADED" or not str(asset.get("storage_url") or asset.get("cloudinary_url") or ""):
            reasons.append(f"{media_id}:not_uploaded")
            continue
        if str(asset.get("rights_status") or clip.get("rights_status") or "").lower() not in APPROVED_RIGHTS:
            reasons.append(f"{media_id}:rights_blocked")
            continue
        if str(asset.get("permission_status") or clip.get("permission_status") or "").lower() != "approved":
            reasons.append(f"{media_id}:permission_blocked")
            continue
        if final_public_post_validator(clip.get("public_post_text", ""), account_id)["status"] != "PASS":
            reasons.append(f"{media_id}:public_post_validator_blocked")
            continue
        candidates.append((clip, source_video, asset))
    if not candidates:
        return None, None, None, reasons
    candidates.sort(key=lambda row: str(row[2].get("uploaded_at") or row[2].get("created_at") or ""))
    clip, source_video, asset = candidates[0]
    return clip, source_video, asset, reasons


def build_plan(
    *,
    apply: bool,
    confirm: bool,
    client: SheetsClient | None = None,
    account_id: str = "liver_manager",
    prepare_only: bool = False,
    post_saved_media: bool = False,
    slot_id: str = "",
) -> dict[str, Any]:
    media_cfg = _load(MEDIA_CONFIG)
    autonomous_cfg = _load(AUTONOMOUS_CONFIG)
    blocked = []
    if autonomous_cfg.get("kill_switch"):
        blocked.append("kill_switch=true")
    if not media_cfg.get("media_public_post_auto_enabled"):
        blocked.append("media_public_post_auto_disabled")
    if account_id not in set(media_cfg.get("allowed_target_account_ids", [media_cfg.get("target_account_id")])):
        blocked.append("account_not_allowed")
    if apply and not confirm:
        blocked.append("--apply requires --confirm-production-media")
    if apply:
        required_env = SAVED_MEDIA_POST_REQUIRED_ENV if post_saved_media else (PREPARE_REQUIRED_ENV if prepare_only else REQUIRED_ENV)
        blocked.extend(f"{name}=true required" for name in required_env if not _true(os.environ.get(name)))
    if not client:
        return {
            "status": "BLOCKED" if blocked else "PLAN_ONLY",
            "account_id": account_id,
            "apply": apply,
            "selected_clip_candidate_id": "",
            "public_post_preview": "",
            "would_download": False,
            "would_cut": False,
            "would_upload": False,
            "would_post_video": False,
            "prepare_only": prepare_only,
            "post_saved_media": post_saved_media,
            "slot_id": slot_id,
            "blocked_reasons": blocked,
        }

    source_videos = _records(client, "source_videos")
    clips = _records(client, "video_clip_candidates")
    media_assets = _records(client, "media_assets")
    posted = _records(client, "posted_results")
    today_posts = _today_posts(posted, account_id)
    daily_cap = int(autonomous_cfg.get("daily_post_cap_per_account", 5))
    media_cap = int(media_cfg.get("media_daily_post_cap", 1))
    media_today = [row for row in today_posts if _true(row.get("media_used"))]
    if len(today_posts) >= daily_cap:
        blocked.append("daily_post_cap_reached")
    if len(media_today) >= media_cap:
        blocked.append("media_daily_post_cap_reached")
    if post_saved_media:
        clip, source_video, selected_asset, skipped = select_saved_media_candidate(
            clips, source_videos, media_assets, posted, account_id,
        )
    else:
        clip, source_video, skipped = select_candidate(clips, source_videos, posted, account_id)
        selected_asset = None
    no_candidate = not clip or not source_video
    if no_candidate:
        blocked.append("no_eligible_media_candidate")
    fatal_blocked = [reason for reason in blocked if reason != "no_eligible_media_candidate"]
    text = str((clip or {}).get("public_post_text") or "")
    return {
        "status": "BLOCKED" if fatal_blocked and apply else "NO_POST" if no_candidate else "PLAN_ONLY",
        "account_id": account_id,
        "apply": apply,
        "selected_clip_candidate_id": str((clip or {}).get("clip_candidate_id") or (clip or {}).get("clip_id") or ""),
        "selected_source_video_id": str((source_video or {}).get("source_video_id") or ""),
        "selected_clip": clip or {},
        "selected_source_video": source_video or {},
        "selected_media_asset": selected_asset or {},
        "prepare_only": prepare_only,
        "post_saved_media": post_saved_media,
        "slot_id": slot_id,
        "public_post_preview": public_preview(text),
        "today_post_count": len(today_posts),
        "today_media_post_count": len(media_today),
        "daily_post_cap": daily_cap,
        "media_daily_post_cap": media_cap,
        "would_download": bool(apply and confirm and not blocked and not post_saved_media),
        "would_cut": bool(apply and confirm and not blocked and not post_saved_media),
        "would_upload": bool(apply and confirm and not blocked and not post_saved_media),
        "would_post_video": bool(apply and confirm and not blocked and not prepare_only),
        "blocked_reasons": blocked,
        "skipped_candidates": skipped[:20],
    }


def execute_saved_media_post(plan: dict[str, Any], client: SheetsClient) -> dict[str, Any]:
    """Publish a previously uploaded, approved clip without download/cut/upload."""
    clip = dict(plan["selected_clip"])
    source_video = dict(plan["selected_source_video"])
    asset = dict(plan["selected_media_asset"])
    clip_id = str(clip.get("clip_candidate_id") or clip.get("clip_id") or "")
    source_video_id = str(source_video.get("source_video_id") or "")
    account_id = str(plan["account_id"])
    media_id = str(asset.get("media_asset_id") or asset.get("media_id") or "")
    media_url = str(asset.get("storage_url") or asset.get("cloudinary_url") or "")
    text = str(clip.get("public_post_text") or "")
    validation = validate_media_post({
        "rights_status": asset.get("rights_status") or clip.get("rights_status", ""),
        "permission_status": asset.get("permission_status") or clip.get("permission_status", ""),
        "media_url": media_url,
        "media_asset_id": media_id,
        "platform": "threads",
        "account_id": account_id,
        "media_type": "video",
        "duration_seconds": asset.get("duration_seconds") or asset.get("duration", 0),
        "aspect_ratio": asset.get("aspect_ratio", "9:16"),
        "public_post_text": text,
    })
    if validation["status"] != "PASS":
        client.update_video_clip_candidate(clip_id, clip_status="BLOCKED", reviewer_status="BLOCKED", post_status="BLOCKED")
        return {**plan, "status": "BLOCKED_MEDIA_VALIDATOR", "media_validation": validation}
    queue_id = f"media_q_{clip_id}"
    queue_row = {
        "queue_id": queue_id,
        "account_id": account_id,
        "target_account_id": account_id,
        "platform": "threads",
        "priority": "1",
        "status": "READY",
        "auto_publish": "true",
        "generation_mode": "approved_saved_media",
        "media_asset_id": media_id,
        "video_clip_id": clip_id,
        "source_video_id": source_video_id,
        "clip_candidate_id": clip_id,
        "rights_status": asset.get("rights_status") or clip.get("rights_status", ""),
        "permission_status": asset.get("permission_status") or clip.get("permission_status", ""),
        "rights_review_required": "false",
        "media_reuse_risk": "low",
        "source_video_url": source_video.get("canonical_video_url", ""),
        "public_post_text": text,
        "validator_status": "PASS",
        "internal_leak_status": "PASS",
        "account_fit_status": "PASS",
        "media_url": media_url,
        "media_status": "UPLOADED",
        "media_required": "true",
        "duration_seconds": asset.get("duration_seconds") or asset.get("duration", ""),
        "aspect_ratio": asset.get("aspect_ratio", "9:16"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    existing_queue_ids = {str(row.get("queue_id", "")) for row in _records(client, "queue")}
    if queue_id not in existing_queue_ids:
        _append(client, "queue", queue_row)
    result = process_one(client, queue_row, dry_run=False, confirm_real_post=True)
    final_status = str(result.get("status", ""))
    client.update_video_clip_candidate(
        clip_id,
        post_status="POSTED" if final_status == "POSTED" else final_status,
        reviewer_status="AUTO_APPROVED" if final_status == "POSTED" else "MEDIA_READY",
        clip_status="POSTED" if final_status == "POSTED" else "MEDIA_READY",
    )
    if final_status == "POSTED":
        client.save_source_video({**source_video, "post_status": "POSTED", "processed_at": datetime.now(timezone.utc).isoformat()})
        try:
            media_pdca = _save_media_pdca_records(
                client,
                clip=clip,
                source_video=source_video,
                media_asset_id=media_id,
                post_result=result,
            )
        except Exception as exc:
            media_pdca = {"saved": 0, "skipped": 3, "warning": f"media_pdca_save_failed:{type(exc).__name__}"}
    else:
        media_pdca = {"saved": 0, "skipped": 3}
    slot_record = _record_media_slot_result(plan, client, {**result, "media_asset_id": media_id})
    return {**plan, "status": final_status, "queue_id": queue_id, "media_asset_id": media_id, "post_result": result,
            "media_pdca": media_pdca, "content_slot_run": slot_record,
            "would_download": False, "would_cut": False, "would_upload": False, "would_post_video": False}


def execute(plan: dict[str, Any], client: SheetsClient) -> dict[str, Any]:
    if plan.get("status") == "BLOCKED":
        return plan
    if plan.get("post_saved_media"):
        return execute_saved_media_post(plan, client)
    clip = dict(plan["selected_clip"])
    source_video = dict(plan["selected_source_video"])
    clip_id = str(clip.get("clip_candidate_id") or clip.get("clip_id"))
    source_video_id = str(source_video.get("source_video_id"))
    account_id = str(plan["account_id"])

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
    asset["account_id"] = account_id
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
        "account_id": account_id,
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
        "account_id": account_id,
        "media_type": "video",
        "duration_seconds": asset.get("duration_seconds", 0),
        "aspect_ratio": "9:16",
        "public_post_text": text,
    })
    if validation["status"] != "PASS":
        client.update_video_clip_candidate(clip_id, clip_status="BLOCKED", reviewer_status="BLOCKED", cut_status="DONE", upload_status="UPLOADED", storage_url=media_url, post_status="BLOCKED")
        return {**plan, "status": "BLOCKED_MEDIA_VALIDATOR", "media_validation": validation}

    if plan.get("prepare_only"):
        client.update_video_clip_candidate(
            clip_id,
            cut_status="DONE",
            local_clip_path=asset.get("local_path", ""),
            clip_media_asset_id=media_id,
            media_asset_id=media_id,
            storage_url=media_url,
            upload_status="UPLOADED",
            post_status="MEDIA_READY",
            reviewer_status="MEDIA_READY",
            clip_status="MEDIA_READY",
        )
        client.save_source_video({**source_video, "download_status": "DOWNLOADED", "cut_status": "CUT", "upload_status": "UPLOADED", "post_status": "MEDIA_READY", "processed_at": datetime.now(timezone.utc).isoformat()})
        return {
            **plan,
            "status": "MEDIA_READY",
            "media_asset_id": media_id,
            "queue_id": "",
            "would_download": False,
            "would_cut": False,
            "would_upload": False,
            "would_post_video": False,
        }

    queue_id = f"media_q_{clip_id}"
    queue_row = {
        "queue_id": queue_id,
        "account_id": account_id,
        "target_account_id": account_id,
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
        try:
            media_pdca = _save_media_pdca_records(
                client,
                clip=clip,
                source_video=source_video,
                media_asset_id=media_id,
                post_result=result,
            )
        except Exception as exc:
            media_pdca = {"saved": 0, "skipped": 3, "warning": f"media_pdca_save_failed:{type(exc).__name__}"}
    else:
        media_pdca = {"saved": 0, "skipped": 3}
    slot_record = _record_media_slot_result(plan, client, {**result, "media_asset_id": media_id})
    return {
        **plan,
        "status": final_status,
        "queue_id": queue_id,
        "media_asset_id": media_id,
        "post_result": result,
        "media_pdca": media_pdca,
        "content_slot_run": slot_record,
        "would_download": False,
        "would_cut": False,
        "would_upload": False,
        "would_post_video": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="run one approved media production post")
    parser.add_argument("--account-id", default="liver_manager", choices=["liver_manager", "night_scout"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-production-media", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--prepare-only", action="store_true", help="download/cut/upload one approved clip, but never post it")
    parser.add_argument("--post-saved-media", action="store_true", help="post one previously uploaded unused approved clip")
    parser.add_argument("--slot-id", default="", help="canonical generated_clip_media slot for idempotency and reporting")
    parser.add_argument("--fallback-to-text", action="store_true", help="use the named slot's safe text fallback when no media asset is ready")
    args = parser.parse_args()
    if args.prepare_only and args.post_saved_media:
        print(json.dumps({"status": "BLOCKED", "blocked_reasons": ["prepare_only_and_post_saved_media_are_mutually_exclusive"]}, ensure_ascii=False))
        return 1

    client = None
    if args.use_sheets:
        cfg = get_config()
        client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    plan = build_plan(
        account_id=args.account_id,
        apply=args.apply,
        confirm=args.confirm_production_media,
        client=client,
        prepare_only=args.prepare_only,
        post_saved_media=args.post_saved_media,
        slot_id=args.slot_id,
    )
    if args.slot_id:
        slot = slot_by_id(args.account_id, args.slot_id)
        if not slot or slot.get("post_type") != "generated_clip_media":
            plan = {**plan, "status": "BLOCKED", "blocked_reasons": ["slot_id must be a generated_clip_media slot"]}
        else:
            plan["slot_id"] = args.slot_id
    if args.apply and args.confirm_production_media and client and plan.get("status") not in {"BLOCKED", "NO_POST"}:
        plan = execute(plan, client)
    elif args.apply and args.confirm_production_media and client and args.fallback_to_text and plan.get("status") == "NO_POST":
        from run_slot_text_fallback import build_plan as build_fallback_plan, execute as execute_fallback
        if not args.slot_id:
            plan = {**plan, "status": "BLOCKED", "blocked_reasons": ["--fallback-to-text requires --slot-id"]}
        else:
            fallback_plan = build_fallback_plan(args.account_id, args.slot_id, "generated_clip_media_unavailable", apply=True)
            fallback = execute_fallback(fallback_plan, client)
            plan = {**plan, "status": fallback.get("status", "FAILED"), "fallback": fallback, "actual_post_type": fallback_plan.get("actual_post_type", "")}
    safe = {k: v for k, v in plan.items() if k not in {"selected_clip", "selected_source_video"}}
    print(json.dumps(safe, ensure_ascii=False, indent=2))
    return 1 if str(plan.get("status", "")).startswith(("FAILED", "BLOCKED")) else 0


if __name__ == "__main__":
    raise SystemExit(main())
