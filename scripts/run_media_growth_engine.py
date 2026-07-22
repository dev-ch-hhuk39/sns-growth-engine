#!/usr/bin/env python3
"""Dry-run first Media Growth Engine for approved liver_manager video sources."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from media.rights_policy import rights_allows_media_use  # noqa: E402
from acquisition.models import SourceMediaItem, SourcePostBundle, stable_content_hash  # noqa: E402
from generation.source_grounded_caption import (  # noqa: E402
    DeterministicGroundedProvider,
    GitHubModelsGroundedProvider,
    SourceGroundedCaptionService,
)
from video.semantic_clip_planner import plan_semantic_clips  # noqa: E402
from discover_approved_source_videos import load_existing_source_videos  # noqa: E402
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
from public_post_quality import (  # noqa: E402
    final_public_post_validator,
    generate_grounded_reader_facing_post,
    generate_reader_facing_post,
    public_preview,
)
from sheets_client import TAB_DEFINITIONS, SheetsClient  # noqa: E402

SOURCES_FILE = ROOT / "config/source_accounts/default_sources.json"
CONFIG_FILE = ROOT / "config/media_growth_engine.json"


def load_sources() -> list[dict[str, Any]]:
    return json.loads(SOURCES_FILE.read_text(encoding="utf-8"))["sources"]


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


def load_source_videos_from_sheets() -> tuple[SheetsClient, list[dict[str, Any]], list[dict[str, Any]]]:
    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    client._ensure_tab("source_videos", TAB_DEFINITIONS["source_videos"])
    client._ensure_tab("video_transcripts", TAB_DEFINITIONS["video_transcripts"])
    client._ensure_tab("video_clip_candidates", TAB_DEFINITIONS["video_clip_candidates"])
    return (
        client,
        [
            dict(r)
            for r in client._call_with_rate_limit_retry(
                "get_all_records:source_videos:media_growth",
                lambda: client._ws("source_videos").get_all_records(),
            )
        ],
        [
            dict(r)
            for r in client._call_with_rate_limit_retry(
                "get_all_records:video_transcripts:media_growth",
                lambda: client._ws("video_transcripts").get_all_records(),
            )
        ],
    )


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
        "caption_provider": row.get("caption_provider", ""),
        "caption_provider_version": row.get("caption_provider_version", ""),
        "alignment_status": row.get("alignment_status", ""),
        "final_alignment_score": row.get("final_alignment_score", ""),
        "main_claim_coverage": row.get("main_claim_coverage", ""),
        "unsupported_claim_count": row.get("unsupported_claim_count", ""),
        "source_copy_similarity": row.get("source_copy_similarity", ""),
        "recent_post_similarity": row.get("recent_post_similarity", ""),
        "claim_support_json": row.get("claim_support_json", ""),
        "notes": "Auto-saved by run_media_growth_engine; production execution remains rights/env gated.",
    }


def append_clip_candidates_to_sheets(client: SheetsClient, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    from gspread.utils import rowcol_to_a1

    ws = client._ws("video_clip_candidates")
    headers = client._call_with_rate_limit_retry(
        "row_values:video_clip_candidates:media_growth",
        lambda: ws.row_values(1),
    )
    existing: dict[str, tuple[int, dict[str, Any]]] = {}
    existing_rows = client._call_with_rate_limit_retry(
        "get_all_records:video_clip_candidates:media_growth",
        lambda: ws.get_all_records(),
    )
    for row_number, existing_row in enumerate(existing_rows, start=2):
        existing[str(existing_row.get("clip_id") or existing_row.get("clip_candidate_id", ""))] = (row_number, dict(existing_row))
    to_add = []
    to_update = []
    for row in rows:
        mapped = _clip_row_for_sheets(row)
        clip_id = str(mapped.get("clip_id", ""))
        if not clip_id:
            continue
        if clip_id in existing:
            row_number, old = existing[clip_id]
            old_grounded = str(old.get("transcript_grounded", "")).lower() in {"1", "true", "yes"}
            new_grounded = str(mapped.get("transcript_grounded", "")).lower() in {"1", "true", "yes"}
            old_ready = str(old.get("clip_status") or old.get("reviewer_status") or "").upper() in {"READY", "AUTO_APPROVED"}
            new_ready = str(mapped.get("clip_status") or mapped.get("reviewer_status") or "").upper() in {"READY", "AUTO_APPROVED"}
            old_validator = str(old.get("public_post_validator_status", "")).upper()
            new_validator = str(mapped.get("public_post_validator_status", "")).upper()
            should_refresh = (
                (new_grounded and not old_grounded)
                or (new_ready and not old_ready)
                or (new_validator == "PASS" and old_validator != "PASS")
                or (bool(mapped.get("public_post_text")) and not old.get("public_post_text"))
            )
            if should_refresh:
                merged = {**old, **mapped}
                old_clip_status = str(old.get("clip_status", "")).upper()
                old_reviewer_status = str(old.get("reviewer_status", "")).upper()
                old_post_status = str(old.get("post_status", "")).upper()
                if old_post_status == "POSTED" or old_clip_status in {"MEDIA_READY", "POSTED"}:
                    merged["post_status"] = old.get("post_status", "")
                    merged["clip_status"] = old.get("clip_status", "")
                    merged["reviewer_status"] = old.get("reviewer_status", "")
                elif old_reviewer_status == "MEDIA_READY":
                    merged["reviewer_status"] = old.get("reviewer_status", "")
                if str(old.get("cut_status", "")).upper() in {"DONE", "CUT"}:
                    merged["cut_status"] = old.get("cut_status", "")
                    merged["local_clip_path"] = old.get("local_clip_path", "")
                if str(old.get("upload_status", "")).upper() == "UPLOADED":
                    merged["upload_status"] = old.get("upload_status", "")
                    merged["storage_url"] = old.get("storage_url", "")
                    merged["media_asset_id"] = old.get("media_asset_id", "")
                    merged["clip_media_asset_id"] = old.get("clip_media_asset_id", "")
                to_update.append({
                    "range": f"{rowcol_to_a1(row_number, 1)}:{rowcol_to_a1(row_number, len(headers))}",
                    "values": [[str(merged.get(h, "")) for h in headers]],
                })
            continue
        to_add.append(mapped)
        existing[clip_id] = (-1, mapped)
    if not to_add and not to_update:
        return 0
    if to_update:
        client._call_with_rate_limit_retry(
            "batch_update:video_clip_candidates:media_growth",
            lambda: ws.batch_update(to_update, value_input_option="USER_ENTERED"),
        )
    if to_add:
        client._call_with_rate_limit_retry(
            "append_rows:video_clip_candidates:media_growth",
            lambda: ws.append_rows(
                [[str(row.get(h, "")) for h in headers] for row in to_add],
                value_input_option="USER_ENTERED",
            ),
        )
    return len(to_add) + len(to_update)


def append_clip_evidence_to_sheets(
    client: SheetsClient,
    rows: list[dict[str, Any]],
    source_videos: list[dict[str, Any]],
) -> int:
    """Persist redacted understanding/alignment evidence once per clip."""
    videos = {str(row.get("source_video_id", "")): row for row in source_videos}
    now = datetime.now(timezone.utc).isoformat()
    saved = 0
    specs = (
        ("content_understanding_runs", "understanding_id"),
        ("semantic_alignment_runs", "alignment_id"),
    )
    existing: dict[str, set[str]] = {}
    for logical, id_field in specs:
        ws = client._ensure_tab(logical, TAB_DEFINITIONS[logical])
        existing[logical] = {
            str(row.get(id_field, ""))
            for row in client._call_with_rate_limit_retry(
                f"get_all_records:{logical}:clip_evidence",
                lambda ws=ws: ws.get_all_records(),
            )
        }
    for clip in rows:
        clip_id = str(clip.get("clip_candidate_id") or clip.get("clip_id") or "")
        if not clip_id:
            continue
        source_video_id = str(clip.get("source_video_id", ""))
        source_video = videos.get(source_video_id, {})
        public_text = str(clip.get("public_post_text", ""))
        understanding = {
            "understanding_id": f"cu_clip_{clip_id}",
            "source_id": clip.get("source_id", ""),
            "source_post_id": "",
            "source_video_id": source_video_id,
            "account_id": clip.get("account_id", ""),
            "platform": clip.get("platform", ""),
            "main_claims_json": clip.get("main_claims_json", "[]"),
            "topic": clip.get("analysis_topic", ""),
            "audience": clip.get("analysis_audience", ""),
            "core_topic": clip.get("analysis_core_topic") or clip.get("analysis_topic", ""),
            "main_claim": clip.get("analysis_main_claim", ""),
            "hook": clip.get("analysis_hook", ""),
            "supporting_points_json": clip.get("analysis_supporting_points_json", "[]"),
            "concrete_example": clip.get("analysis_concrete_example", ""),
            "conclusion": clip.get("analysis_conclusion", ""),
            "intended_audience": clip.get("analysis_intended_audience") or clip.get("analysis_audience", ""),
            "media_role": clip.get("analysis_media_role", ""),
            "factual_constraints_json": clip.get("analysis_factual_constraints_json", "[]"),
            "prohibited_inferences_json": clip.get("analysis_prohibited_inferences_json", "[]"),
            "comment_signal_count": source_video.get("comment_count_collected") or source_video.get("comment_count", "0"),
            "media_item_count": "1",
            "provider_name": clip.get("caption_provider", ""),
            "provider_version": clip.get("caption_provider_version", ""),
            "status": clip.get("content_understanding_status", "BLOCKED"),
            "content_hash": clip.get("source_content_hash") or source_video.get("content_hash", ""),
            "created_at": now,
            "updated_at": now,
        }
        alignment = {
            "alignment_id": f"sa_clip_{clip_id}",
            "source_id": clip.get("source_id", ""),
            "source_post_id": "",
            "source_video_id": source_video_id,
            "clip_candidate_id": clip_id,
            "queue_id": "",
            "account_id": clip.get("account_id", ""),
            "platform": clip.get("platform", ""),
            "caption_provider": clip.get("caption_provider", ""),
            "caption_provider_version": clip.get("caption_provider_version", ""),
            "status": clip.get("alignment_status", "BLOCKED"),
            "final_alignment_score": clip.get("final_alignment_score", ""),
            "main_claim_coverage": clip.get("main_claim_coverage", ""),
            "unsupported_claim_count": clip.get("unsupported_claim_count", ""),
            "source_copy_similarity": clip.get("source_copy_similarity", ""),
            "recent_post_similarity": clip.get("recent_post_similarity", ""),
            "claim_support_json": clip.get("claim_support_json", "[]"),
            "blocked_reasons": json.dumps(clip.get("blocked_reasons", []), ensure_ascii=False),
            "source_content_hash": clip.get("source_content_hash") or source_video.get("content_hash", ""),
            "public_post_hash": hashlib.sha256(public_text.encode("utf-8")).hexdigest() if public_text else "",
            "created_at": now,
            "updated_at": now,
        }
        for logical, id_field, evidence in (
            ("content_understanding_runs", "understanding_id", understanding),
            ("semantic_alignment_runs", "alignment_id", alignment),
        ):
            evidence_id = str(evidence[id_field])
            if evidence_id in existing[logical]:
                continue
            ws = client._ws(logical)
            headers = client._call_with_rate_limit_retry(
                f"row_values:{logical}:clip_evidence",
                lambda ws=ws: ws.row_values(1),
            )
            client._call_with_rate_limit_retry(
                f"append_row:{logical}:clip_evidence",
                lambda ws=ws, headers=headers, evidence=evidence: ws.append_row(
                    [str(evidence.get(header, "")) for header in headers],
                    value_input_option="USER_ENTERED",
                ),
            )
            existing[logical].add(evidence_id)
            saved += 1
    return saved


def is_channel_or_account_url(source: dict[str, Any]) -> bool:
    source_type = str(source.get("source_type", "")).lower()
    url = str(source.get("source_url", ""))
    return source_type in {"channel", "account"} or (source.get("source_platform") == "tiktok" and "/video/" not in url)


def permission_ok(source: dict[str, Any]) -> bool:
    evidence_type = str(source.get("permission_evidence_type", ""))
    if evidence_type == "owner_attestation" and str(source.get("permission_evidence_reference", "")) != "global_owner_attestation_v1":
        return False
    return (
        source.get("permission_status") == "approved"
        and bool(evidence_type)
        and bool(source.get("permission_evidence_note"))
        and bool(source.get("permission_approved_by"))
    )


def is_real_discovered_video(row: dict[str, Any]) -> bool:
    if str(row.get("discovery_status", "")).upper() == "PLANNED_ONLY":
        return False
    # Flat channel discovery often has a real title/video id but no public
    # description. The placeholder description alone must not turn that real
    # video back into a synthetic plan row.
    if "video candidate" in str(row.get("title", "")).lower():
        return False
    platform = str(row.get("platform", "")).lower()
    video_id = extract_video_id(str(row.get("canonical_video_url", "")), platform)
    if platform == "youtube":
        return len(video_id) == 11
    if platform == "tiktok":
        return bool(video_id and video_id.isdigit())
    return bool(video_id)


def _transcript_done(row: dict[str, Any]) -> bool:
    return (
        str(row.get("transcription_status", "")).upper() in {"DONE", "FETCHED", "LOCAL_WHISPER_DONE", "YOUTUBE_CAPTIONS_DONE"}
        and bool(str(row.get("transcript_text", "")).strip())
    )


def night_subject_policy_check(source: dict[str, Any], video: dict[str, Any]) -> dict[str, str]:
    """Conservative, explainable eligibility check for night_scout clip use.

    We do not claim visual recognition. A video must either be explicitly
    reviewed or its public metadata must contain a female-subject cue, and
    clear scout-talking-head/store-recruiting metadata is blocked. Unknown is
    analysis-only, which is safer than turning a source-level permission into a
    blanket claim about every video on that channel.
    """
    if "night_scout" not in (source.get("target_account_ids") or [source.get("target_account_id")]):
        return {"status": "PASS", "reason": "not_night_scout"}
    if str(video.get("subject_review_status", "")).upper() == "APPROVED_FEMALE_SUBJECT":
        return {"status": "PASS", "reason": "explicit_subject_review"}
    text = " ".join(str(video.get(key, "")) for key in ("title", "description_preview", "description")).lower()
    blocked = ("男性スカウト", "スカウトが", "求人", "募集", "店舗pr", "店pr", "recruit")
    if any(token.lower() in text for token in blocked):
        return {"status": "BLOCKED", "reason": "night_subject_policy_analysis_only"}
    female_cues = ("キャバ嬢", "女の子", "女性", "嬢", "キャスト", "girl", "ladies")
    if any(token.lower() in text for token in female_cues):
        return {"status": "PASS", "reason": "metadata_female_subject_cue"}
    return {"status": "BLOCKED", "reason": "night_subject_evidence_required"}


def _segments(row: dict[str, Any]) -> list[dict[str, Any]]:
    raw = str(row.get("segments_json", "") or "[]")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    rows = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        try:
            start = float(item.get("start", 0) or 0)
            end = float(item.get("end", start) or start)
        except (TypeError, ValueError):
            continue
        if end <= start:
            end = start + 3
        rows.append({"start": start, "end": end, "text": text})
    return sorted(rows, key=lambda r: float(r["start"]))


def _clip_specs_from_transcript(video: dict[str, Any], transcript: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    segments = _segments(transcript)
    if not segments:
        return []
    max_count = clip_count_for_video(video, config, transcript_signal_count=len(segments))
    video_duration = float(video.get("duration_seconds") or segments[-1]["end"] or 0)
    return plan_semantic_clips(
        segments,
        video_duration=video_duration,
        max_candidates=max_count,
        min_seconds=float(config.get("clip_duration_min_seconds", 8)),
        max_seconds=float(config.get("clip_duration_max_seconds", 45)),
        overlap_tolerance_seconds=float(config.get("clip_overlap_tolerance_seconds", 2)),
    )


def _comment_signal_count(video: dict[str, Any], excerpt: str) -> int:
    raw = video.get("comments_json") or "[]"
    try:
        comments = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        comments = []
    if not isinstance(comments, list):
        return 0
    meaningful = {
        token
        for token in re.findall(r"[一-龥ぁ-んァ-ンA-Za-z0-9]{2,}", str(excerpt or ""))
        if len(token) >= 2
    }
    count = 0
    for row in comments[:20]:
        text = str(row.get("text", "") if isinstance(row, dict) else row)
        if any(token in text for token in meaningful) or "?" in text or "？" in text:
            count += 1
    return count


def select_sources(account_id: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    allowed_ids = set(config.get("allowed_source_ids", []))
    rows = []
    for source in load_sources():
        targets = source.get("target_account_ids") or [source.get("target_account_id")]
        if account_id not in targets:
            continue
        if not source.get("active"):
            continue
        if source.get("source_id") not in allowed_ids:
            continue
        if config.get("require_source_media_autopilot_enabled") and not source.get("media_autopilot_enabled"):
            continue
        rows.append(source)
    return rows


def build_media_growth_plan(
    account_id: str,
    *,
    apply: bool = False,
    confirm_media_growth: bool = False,
    existing_source_videos: list[dict[str, Any]] | None = None,
    existing_transcripts: list[dict[str, Any]] | None = None,
    caption_service: SourceGroundedCaptionService | None = None,
) -> dict[str, Any]:
    config = load_config()
    selected = select_sources(account_id, config)
    blocked: list[str] = []
    if not config.get("media_growth_engine_enabled"):
        blocked.append("media_growth_engine_disabled")
    if account_id not in set(config.get("allowed_target_account_ids", [config.get("target_account_id")])):
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
    existing_transcripts = existing_transcripts or []
    transcript_by_source_video = {
        str(t.get("source_video_id", "")): t
        for t in existing_transcripts
        if _transcript_done(t)
    }
    planned_source_videos = [
        row
        for row in existing_source_videos
        if (account_id == "all" or str(row.get("account_id", "")) == account_id)
        and is_real_discovered_video(row)
    ]

    source_by_id = {str(s.get("source_id", "")): s for s in selected}
    # One transcript may produce several clip windows. Bound remote generation
    # to one attempt per video so a preparation workflow remains finite.
    remote_caption_timeout = int(config.get("remote_caption_timeout_seconds", 25))
    remote_caption_limit = max(0, int(config.get("max_remote_caption_generations_per_video", 1)))
    uses_default_caption_service = caption_service is None
    caption_service = caption_service or SourceGroundedCaptionService(
        GitHubModelsGroundedProvider(timeout_seconds=remote_caption_timeout),
        fallback_provider=DeterministicGroundedProvider(),
        retry_primary_on_alignment_failure=False,
    )
    deterministic_caption_service = SourceGroundedCaptionService(DeterministicGroundedProvider())
    public_text = ""
    validation = {"status": "BLOCKED", "blocked_reasons": ["no_grounded_clip_caption"]}
    existing_clips: list[dict[str, Any]] = []
    for video_index, source_video in enumerate(planned_source_videos, start=1):
        source = source_by_id.get(str(source_video.get("source_id", "")))
        if not source:
            continue
        subject_check = night_subject_policy_check(source, source_video)
        source_video["subject_policy_status"] = subject_check["status"]
        source_video["subject_policy_reason"] = subject_check["reason"]
        if subject_check["status"] != "PASS":
            source_video["analysis_status"] = "ANALYSIS_ONLY"
            source_video["skip_reason"] = subject_check["reason"]
            continue
        transcript = transcript_by_source_video.get(str(source_video.get("source_video_id", "")))
        if not transcript:
            source_video["transcript_status"] = source_video.get("transcript_status") or "TRANSCRIPT_PENDING"
            source_video["analysis_status"] = "TRANSCRIPT_PENDING"
            continue
        duration = float(source_video.get("duration_seconds") or 0)
        if duration < float(config.get("clip_duration_min_seconds", 8)):
            source_video["skip_reason"] = "duration_metadata_required_or_too_short"
            source_video["analysis_status"] = "SKIPPED"
            continue
        clip_specs = _clip_specs_from_transcript(source_video, transcript, config)
        count = len(clip_specs)
        video_candidates = []
        for i, spec in enumerate(clip_specs, start=1):
            source_video_id = str(source_video.get("source_video_id", ""))
            video_url = str(source_video.get("canonical_video_url", ""))
            media = SourceMediaItem(
                source_post_media_id=f"spm_{source_video_id}_0",
                source_post_id=source_video_id,
                media_index=0,
                media_type="video",
                canonical_post_url=video_url,
                original_media_url=video_url,
                resolver_backend=str(source_video.get("collection_backend", "source_videos")),
                duration_seconds=str(source_video.get("duration_seconds", "")),
            )
            bundle = SourcePostBundle(
                source_post_id=source_video_id,
                source_id=str(source_video.get("source_id", "")),
                target_account_id=account_id,
                platform=str(source_video.get("platform", "")),
                profile_url=str(source_video.get("source_url", "")),
                canonical_post_url=video_url,
                external_post_id=str(source_video.get("video_id", "")),
                original_post_text="\n".join(filter(None, [
                    str(source_video.get("title", "")),
                    str(source_video.get("description_preview", "")),
                ])),
                published_at=str(source_video.get("published_at", "")),
                media_items=(media,),
                content_hash=str(source_video.get("content_hash", "")) or stable_content_hash(str(spec.get("excerpt", "")), [video_url]),
            )
            active_caption_service = (
                caption_service
                if not uses_default_caption_service or i <= remote_caption_limit
                else deterministic_caption_service
            )
            clip_output = active_caption_service.generate(
                bundle,
                account_id=account_id,
                transcript_excerpt=str(spec.get("excerpt", "")),
            )
            clip_public_text = str(clip_output.get("public_post_text", ""))
            clip_validation = final_public_post_validator(clip_public_text, account_id)
            cand = build_clip_candidate_for_video(
                source,
                source_video,
                i,
                config=config,
                public_post_text=clip_public_text,
                validator_status=clip_validation["status"],
                transcript_signal_count=len(_segments(transcript)),
                transcript_grounded=True,
                transcript_id=str(transcript.get("transcript_id", "")),
                transcript_excerpt=str(spec.get("excerpt", "")),
                start_seconds=float(spec.get("start", 0)),
                end_seconds=float(spec.get("end", 0)),
                semantic_score=float(spec.get("semantic_score", 0) or 0),
                comment_signal_count=_comment_signal_count(source_video, str(spec.get("excerpt", ""))),
            )
            alignment = clip_output.get("semantic_alignment", {})
            internal_analysis = clip_output.get("internal_analysis") if isinstance(clip_output.get("internal_analysis"), dict) else {}
            cand.update({
                "caption_provider": clip_output.get("provider_name", ""),
                "caption_provider_version": clip_output.get("provider_version", ""),
                "alignment_status": alignment.get("status", "BLOCKED"),
                "final_alignment_score": alignment.get("final_alignment_score", 0),
                "main_claim_coverage": alignment.get("main_claim_coverage", 0),
                "unsupported_claim_count": alignment.get("unsupported_claim_count", 1),
                "source_copy_similarity": alignment.get("source_copy_similarity", 1),
                "recent_post_similarity": alignment.get("recent_post_similarity", 1),
                "claim_support_json": json.dumps(clip_output.get("claim_support", []), ensure_ascii=False),
                "content_understanding_status": clip_output.get("status", "BLOCKED"),
                "main_claims_json": json.dumps(internal_analysis.get("main_claims", []), ensure_ascii=False),
                "analysis_topic": internal_analysis.get("topic", ""),
                "analysis_audience": internal_analysis.get("audience", ""),
                "analysis_core_topic": internal_analysis.get("core_topic") or internal_analysis.get("topic", ""),
                "analysis_main_claim": internal_analysis.get("main_claim", ""),
                "analysis_hook": internal_analysis.get("hook", ""),
                "analysis_supporting_points_json": json.dumps(internal_analysis.get("supporting_points", []), ensure_ascii=False),
                "analysis_concrete_example": internal_analysis.get("concrete_example", ""),
                "analysis_conclusion": internal_analysis.get("conclusion", ""),
                "analysis_intended_audience": internal_analysis.get("intended_audience") or internal_analysis.get("audience", ""),
                "analysis_media_role": internal_analysis.get("media_role", ""),
                "analysis_factual_constraints_json": json.dumps(internal_analysis.get("factual_constraints", []), ensure_ascii=False),
                "analysis_prohibited_inferences_json": json.dumps(internal_analysis.get("prohibited_inferences", []), ensure_ascii=False),
                "source_content_hash": bundle.content_hash,
                "failure_signature": "" if clip_output.get("status") == "PASS" else "caption_or_alignment_blocked",
                "selected_reason": spec.get("selected_reason", "semantic_window"),
                "semantic_segment_score": spec.get("semantic_score", ""),
            })
            if any(clips_overlap(cand, old, config.get("clip_overlap_tolerance_seconds", 2)) for old in existing_clips):
                cand["clip_status"] = "SKIPPED"
                cand["reviewer_status"] = "SKIPPED"
                cand["selected_reason"] = "overlap_blocked"
                continue
            existing_clips.append(cand)
            if (
                config.get("auto_approve_clip_candidates")
                and clip_validation["status"] == "PASS"
                and clip_output.get("status") == "PASS"
                and alignment.get("status") == "PASS"
                and cand.get("transcript_grounded") is True
                and float(cand.get("clip_score") or 0) >= float(config.get("min_auto_clip_score", 80))
                and cand.get("rights_status") in set(config.get("allowed_rights_statuses", []))
                and cand.get("permission_status") == "approved"
            ):
                cand["reviewer_status"] = "AUTO_APPROVED"
                cand["clip_status"] = "READY"
            video_candidates.append(cand)
            clip_candidates.append(cand)
            if not public_text and clip_output.get("status") == "PASS":
                public_text = clip_public_text
                validation = clip_validation
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
    if planned_source_videos and validation["status"] != "PASS":
        blocked.append("public_post_validator_blocked")
    return {
        "status": "PLAN_ONLY" if not blocked else "BLOCKED",
        "account_id": account_id,
        "selected_sources": [{"source_id": s.get("source_id"), "source_url": s.get("source_url"), "rights_status": s.get("rights_status")} for s in selected],
        "rights_check": "PASS" if all(r["rights_check"] == "PASS" for r in source_results) else "BLOCKED",
        "permission_evidence": "PASS" if all(r["permission_evidence"] == "PASS" for r in source_results) else "BLOCKED",
        "source_results": source_results,
        "source_videos_source": "existing_source_videos" if existing_source_videos else "none_discover_first",
        "source_video_count": len(planned_source_videos),
        "transcript_grounded_source_video_count": len(transcript_by_source_video),
        "source_videos_preview": [
            {
                "source_video_id": row.get("source_video_id", ""),
                "source_id": row.get("source_id", ""),
                "platform": row.get("platform", ""),
                "video_id": row.get("video_id", ""),
                "transcript_status": row.get("transcript_status", ""),
                "analysis_status": row.get("analysis_status", ""),
            }
            for row in planned_source_videos[:5]
        ],
        "video_transcripts_schema": [
            {
                "transcript_id": row.get("transcript_id", ""),
                "source_video_id": row.get("source_video_id", ""),
                "transcript_status": row.get("transcript_status", ""),
                "transcript_language": row.get("transcript_language", ""),
                "chunk_count": row.get("chunk_count", ""),
            }
            for row in transcript_rows
        ],
        "clip_candidate_count": len(clip_candidates),
        "top_clip_candidates": [
            {
                "clip_candidate_id": row.get("clip_candidate_id", ""),
                "source_video_id": row.get("source_video_id", ""),
                "start_seconds": row.get("start_seconds", ""),
                "end_seconds": row.get("end_seconds", ""),
                "clip_score": row.get("clip_score", ""),
                "clip_status": row.get("clip_status", ""),
                "target_audience": row.get("target_audience", ""),
                "transcript_grounded": row.get("transcript_grounded", False),
                "transcript_id": row.get("transcript_id", ""),
                "public_post_validator_status": row.get("public_post_validator_status", ""),
                "caption_provider": row.get("caption_provider", ""),
                "alignment_status": row.get("alignment_status", ""),
                "final_alignment_score": row.get("final_alignment_score", ""),
                "unsupported_claim_count": row.get("unsupported_claim_count", ""),
            }
            for row in clip_candidates[:5]
        ],
        "_clip_candidates_for_save": clip_candidates,
        "media_post_queue_preview": media_post_queue_preview,
        "public_post_preview": public_preview(public_text),
        "final_public_post_validator": validation["status"],
        "media_plan": media_plan,
        "caption_generation_budget": {
            "max_remote_caption_generations_per_video": remote_caption_limit,
            "remote_caption_timeout_seconds": remote_caption_timeout,
            "remaining_candidates_use": "deterministic_grounded_fallback",
        },
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
    transcripts = None
    if args.use_sheets and (args.apply or args.dry_run):
        client, existing, transcripts = load_source_videos_from_sheets()
    plan = build_media_growth_plan(
        args.account_id,
        apply=args.apply,
        confirm_media_growth=args.confirm_media_growth,
        existing_source_videos=existing,
        existing_transcripts=transcripts,
    )
    if args.apply and args.confirm_media_growth and args.use_sheets and client and plan["status"] != "BLOCKED":
        candidates_for_save = plan.get("_clip_candidates_for_save", [])
        added = append_clip_candidates_to_sheets(client, candidates_for_save)
        evidence_saved = append_clip_evidence_to_sheets(client, candidates_for_save, existing or [])
        plan["saved_clip_candidate_count"] = added
        plan["saved_clip_evidence_count"] = evidence_saved
        plan["clip_candidate_save_status"] = "SAVED" if added else "NO_NEW_ROWS"
    elif args.apply and args.confirm_media_growth and not args.use_sheets and plan["status"] != "BLOCKED":
        plan["clip_candidate_save_status"] = "SKIPPED_USE_SHEETS_REQUIRED"
    plan.pop("_clip_candidates_for_save", None)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 1 if plan["status"] == "BLOCKED" and args.apply else 0


if __name__ == "__main__":
    raise SystemExit(main())
