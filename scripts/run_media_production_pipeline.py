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
from content_slot_runs import business_date, build_slot_run, claim_slot_run, existing_slot_status, posts_used_in_business_date, upsert_slot_run  # noqa: E402
from cut_approved_clips import build_plan as build_cut_plan, execute_cut  # noqa: E402
from download_approved_media import build_download_plan, execute_download, is_individual_video_url  # noqa: E402
from media_post_validator import validate_media_post  # noqa: E402
from media_growth_schemas import build_media_pdca_records, extract_video_id  # noqa: E402
from acquisition.models import (  # noqa: E402
    SourceMediaItem,
    SourcePostBundle,
    stable_content_hash,
)
from generation.source_grounded_caption import (  # noqa: E402
    DeterministicGroundedProvider,
    GitHubModelsGroundedProvider,
    SourceGroundedCaptionService,
)
from process_threads_queue import process_one  # noqa: E402
from public_post_quality import final_public_post_validator, public_preview  # noqa: E402
from sheets_client import TAB_DEFINITIONS, SheetsClient  # noqa: E402
from upload_media_assets import build_upload_plan, execute_cloudinary_uploads  # noqa: E402
from acquisition.reliability import build_quarantine_record, clear_failure, is_quarantined, register_failure  # noqa: E402

MEDIA_CONFIG = ROOT / "config/media_growth_engine.json"
AUTONOMOUS_CONFIG = ROOT / "config/autonomous_mode.json"
JST = timezone(timedelta(hours=9))
APPROVED_RIGHTS = {"owned", "licensed", "approved_creator_clip"}
POSTED_SLOT_STATUSES = {"POSTED_PRIMARY", "POSTED_FALLBACK", "BACKFILLED", "POSTED"}
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


def _alignment_fields(clip: dict[str, Any]) -> dict[str, Any]:
    return {
        "alignment_status": clip.get("alignment_status", ""),
        "final_alignment_score": clip.get("final_alignment_score", ""),
        "main_claim_coverage": clip.get("main_claim_coverage", ""),
        "unsupported_claim_count": clip.get("unsupported_claim_count", ""),
        "source_copy_similarity": clip.get("source_copy_similarity", ""),
        "recent_post_similarity": clip.get("recent_post_similarity", ""),
    }


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _records(client: SheetsClient, logical: str) -> list[dict[str, Any]]:
    client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    operation = lambda: client._ws(logical).get_all_records()
    retry = getattr(client, "_call_with_rate_limit_retry", None)
    rows = retry(f"get_all_records:{logical}:media_production", operation) if retry else operation()
    return [dict(row) for row in rows]


def _append(client: SheetsClient, logical: str, row: dict[str, Any]) -> None:
    client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    ws = client._ws(logical)
    retry = getattr(client, "_call_with_rate_limit_retry", None)
    read_headers = lambda: ws.row_values(1)
    headers = retry(f"row_values:{logical}:media_production", read_headers) if retry else read_headers()
    append = lambda: ws.append_row([str(row.get(h, "")) for h in headers], value_input_option="USER_ENTERED")
    if retry:
        retry(f"append_row:{logical}:media_production", append)
    else:
        append()


def _record_clip_failure(
    client: SheetsClient,
    clip: dict[str, Any],
    *,
    account_id: str,
    reason: str,
) -> dict[str, Any]:
    """Persist bounded retry state and quarantine only on a repeated failure."""
    clip_id = str(clip.get("clip_candidate_id") or clip.get("clip_id") or "")
    state = register_failure(clip, reason)
    updates = {
        key: state.get(key, "")
        for key in (
            "retry_count", "last_error", "failure_signature", "same_failure_count",
            "last_attempt_at", "quarantined_at", "quarantine_reason",
        )
    }
    if is_quarantined(state):
        updates.update({"clip_status": "QUARANTINED", "reviewer_status": "QUARANTINED", "post_status": "QUARANTINED"})
    client.update_video_clip_candidate(clip_id, **updates)
    if is_quarantined(state):
        quarantine = build_quarantine_record(
            state,
            entity_type="video_clip_candidate",
            entity_id=clip_id,
            source_id=str(clip.get("source_id", "")),
            account_id=account_id,
        )
        existing = {str(row.get("quarantine_id", "")) for row in _records(client, "quarantined_items")}
        if quarantine["quarantine_id"] not in existing:
            _append(client, "quarantined_items", quarantine)
    return state


def _clear_clip_failure(client: SheetsClient, clip: dict[str, Any]) -> None:
    clip_id = str(clip.get("clip_candidate_id") or clip.get("clip_id") or "")
    state = clear_failure(clip)
    client.update_video_clip_candidate(
        clip_id,
        retry_count=state.get("retry_count", clip.get("retry_count", "0")),
        last_error="",
        failure_signature="",
        same_failure_count="0",
        last_attempt_at=state.get("last_attempt_at", ""),
    )


def _record_media_slot_result(plan: dict[str, Any], client: SheetsClient, result: dict[str, Any]) -> dict[str, Any]:
    slot_id = str(plan.get("slot_id", ""))
    if not slot_id:
        return {"status": "SKIPPED", "reason": "slot_id_not_provided"}
    posted = str(result.get("status", "")) in {"POSTED", "POSTED_SAVE_FAILED"}
    row = build_slot_run(
        str(plan["account_id"]),
        slot_id,
        status="POSTED_PRIMARY" if posted else "FAILED",
        actual_post_type="approved_source_clip",
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
    if posts_used_in_business_date(account_id, rows) == 0:
        return []
    target = business_date(datetime.now(JST))
    result = []
    for row in rows:
        if str(row.get("account_id", "")) != account_id or str(row.get("status", "")).upper() != "POSTED":
            continue
        posted = _parse_time(row.get("posted_at"))
        if posted and business_date(posted) == target:
            result.append(row)
    return result



def _recent_public_posts(
    posted_results: list[dict[str, Any]],
    account_id: str,
) -> list[str]:
    texts: list[str] = []

    for row in posted_results:
        if str(row.get("account_id", "")) != account_id:
            continue

        if str(row.get("status", "")).upper() != "POSTED":
            continue

        public_text = str(
            row.get("posted_text")
            or row.get("public_post_text")
            or ""
        ).strip()

        if public_text:
            texts.append(public_text)

    return texts[-20:]


def _build_final_caption_bundle(
    *,
    clip: dict[str, Any],
    source_video: dict[str, Any],
    account_id: str,
    media_asset: dict[str, Any] | None = None,
) -> tuple[SourcePostBundle | None, str, list[str]]:
    """Build one exact clip evidence packet for final captioning."""
    reasons: list[str] = []

    if not _true(clip.get("transcript_grounded")):
        reasons.append("transcript_grounding_required")

    transcript_excerpt = str(
        clip.get("transcript_excerpt")
        or ""
    ).strip()

    if not transcript_excerpt:
        reasons.append("transcript_excerpt_missing")

    start_seconds = str(
        clip.get("start_seconds")
        or clip.get("start_time")
        or ""
    ).strip()
    end_seconds = str(
        clip.get("end_seconds")
        or clip.get("end_time")
        or ""
    ).strip()

    if not start_seconds or not end_seconds:
        reasons.append("final_clip_time_range_missing")

    video_url = str(
        source_video.get("canonical_video_url")
        or source_video.get("source_video_url")
        or ""
    ).strip()

    if not is_individual_video_url(video_url):
        reasons.append("individual_video_url_required")

    if reasons:
        return None, transcript_excerpt, reasons

    source_video_id = str(
        source_video.get("source_video_id")
        or clip.get("source_video_id")
        or ""
    )

    final_asset = media_asset or {}

    media = SourceMediaItem(
        source_post_media_id=(
            f"spm_{source_video_id}_final_clip"
        ),
        source_post_id=source_video_id,
        media_index=0,
        media_type="video",
        canonical_post_url=video_url,
        original_media_url=video_url,
        resolver_backend="approved_source_clip",
        duration_seconds=str(
            final_asset.get("duration_seconds")
            or final_asset.get("duration")
            or clip.get("duration_seconds")
            or ""
        ),
        width=str(final_asset.get("width", "")),
        height=str(final_asset.get("height", "")),
    )

    source_text = "\n".join(filter(None, [
        str(source_video.get("title", "")).strip(),
        str(
            source_video.get("description_preview", "")
        ).strip(),
    ]))

    clip_identity = "\n".join([
        transcript_excerpt,
        f"start_seconds={start_seconds}",
        f"end_seconds={end_seconds}",
    ])

    content_hash = str(
        source_video.get("content_hash")
        or ""
    ).strip()

    if not content_hash:
        content_hash = stable_content_hash(
            clip_identity,
            [video_url],
        )

    bundle = SourcePostBundle(
        source_post_id=source_video_id,
        source_id=str(source_video.get("source_id", "")),
        target_account_id=account_id,
        platform=str(source_video.get("platform", "")),
        profile_url=str(
            source_video.get("source_url")
            or source_video.get("profile_url")
            or ""
        ),
        canonical_post_url=video_url,
        external_post_id=str(
            source_video.get("video_id")
            or extract_video_id(
                video_url,
                str(source_video.get("platform", "")),
            )
        ),
        original_post_text=source_text,
        published_at=str(
            source_video.get("published_at", "")
        ),
        author_name=str(
            source_video.get("author_name", "")
        ),
        author_handle=str(
            source_video.get("author_handle", "")
        ),
        media_items=(media,),
        content_hash=content_hash,
    )

    return bundle, transcript_excerpt, []


def _default_final_caption_service(
) -> SourceGroundedCaptionService:
    """Use the canonical provider with only a grounded fallback."""
    return SourceGroundedCaptionService(
        generation_provider=GitHubModelsGroundedProvider(),
        fallback_provider=DeterministicGroundedProvider(),
        allow_deterministic_fallback=True,
        # The production pipeline owns the explicit three-attempt
        # contract. One service call therefore equals one attempt.
        retry_primary_on_alignment_failure=False,
    )


def _finalize_generated_caption(text: Any) -> str:
    """Apply final formatting before the public validator."""
    raw = str(text or "").replace("\r\n", "\n").strip()

    lines = [
        line.rstrip()
        for line in raw.splitlines()
    ]

    compact: list[str] = []
    previous_blank = False

    for line in lines:
        blank = not line.strip()

        if blank and previous_blank:
            continue

        compact.append(line.strip() if not blank else "")
        previous_blank = blank

    return "\n".join(compact).strip()


def _generate_final_media_caption(
    *,
    clip: dict[str, Any],
    source_video: dict[str, Any],
    media_asset: dict[str, Any],
    account_id: str,
    recent_posts: list[str],
    caption_service: Any | None = None,
    max_attempts: int = 3,
) -> dict[str, Any]:
    """Generate only from the final clip packet, at most three times."""
    bundle, transcript_excerpt, grounding_reasons = (
        _build_final_caption_bundle(
            clip=clip,
            source_video=source_video,
            account_id=account_id,
            media_asset=media_asset,
        )
    )

    if grounding_reasons or bundle is None:
        return {
            "status": "REVIEW_REQUIRED",
            "public_post_text": "",
            "caption_attempt_count": 0,
            "caption_attempts": [],
            "blocked_reasons": grounding_reasons,
            "caption_provider": "",
            "caption_provider_version": "",
            "alignment_status": "BLOCKED",
            "final_alignment_score": 0,
            "main_claim_coverage": 0,
            "unsupported_claim_count": 1,
            "source_copy_similarity": 1,
            "recent_post_similarity": 1,
            "claim_support_json": "[]",
        }

    service = (
        caption_service
        if caption_service is not None
        else _default_final_caption_service()
    )

    attempt_limit = min(
        3,
        max(1, int(max_attempts or 3)),
    )

    attempts: list[dict[str, Any]] = []
    all_reasons: list[str] = []

    for attempt in range(1, attempt_limit + 1):
        try:
            output = service.generate(
                bundle,
                account_id=account_id,
                recent_posts=recent_posts,
                transcript_excerpt=transcript_excerpt,
            )
        except Exception as exc:
            output = {
                "status": "BLOCKED",
                "public_post_text": "",
                "blocked_reasons": [
                    (
                        f"{type(exc).__name__}:"
                        "final_caption_generation_failed"
                    )
                ],
                "provider_name": "",
                "provider_version": "",
                "provider_status": "FAILED",
                "semantic_alignment": {
                    "status": "BLOCKED",
                    "blocked_reasons": [
                        "caption_service_exception"
                    ],
                },
                "claim_support": [],
            }

        finalized_text = _finalize_generated_caption(
            output.get("public_post_text", "")
        )

        validation = final_public_post_validator(
            finalized_text,
            account_id,
        )

        semantic = (
            output.get("semantic_alignment")
            if isinstance(
                output.get("semantic_alignment"),
                dict,
            )
            else {}
        )

        attempt_reasons = [
            str(reason)
            for reason in output.get(
                "blocked_reasons",
                [],
            )
            if str(reason)
        ]

        attempt_reasons.extend(
            str(reason)
            for reason in validation.get(
                "blocked_reasons",
                [],
            )
            if str(reason)
        )

        if semantic.get("status") != "PASS":
            attempt_reasons.extend(
                str(reason)
                for reason in semantic.get(
                    "blocked_reasons",
                    ["semantic_alignment_failed"],
                )
                if str(reason)
            )

        attempt_reasons = sorted(
            set(attempt_reasons)
        )

        attempts.append({
            "attempt": attempt,
            "provider_name": str(
                output.get("provider_name", "")
            ),
            "provider_version": str(
                output.get("provider_version", "")
            ),
            "provider_status": str(
                output.get("provider_status", "")
            ),
            "generation_status": str(
                output.get("status", "")
            ),
            "semantic_alignment_status": str(
                semantic.get("status", "BLOCKED")
            ),
            "final_validator_status": str(
                validation.get("status", "BLOCKED")
            ),
            "blocked_reasons": attempt_reasons,
        })

        passed = (
            output.get("status") == "PASS"
            and semantic.get("status") == "PASS"
            and validation.get("status") == "PASS"
            and bool(finalized_text)
        )

        if passed:
            return {
                "status": "PASS",
                "public_post_text": finalized_text,
                "caption_attempt_count": attempt,
                "caption_attempts": attempts,
                "blocked_reasons": [],
                "caption_provider": str(
                    output.get("provider_name", "")
                ),
                "caption_provider_version": str(
                    output.get("provider_version", "")
                ),
                "alignment_status": "PASS",
                "final_alignment_score": (
                    semantic.get(
                        "final_alignment_score",
                        0,
                    )
                ),
                "main_claim_coverage": (
                    semantic.get(
                        "main_claim_coverage",
                        0,
                    )
                ),
                "unsupported_claim_count": (
                    semantic.get(
                        "unsupported_claim_count",
                        0,
                    )
                ),
                "source_copy_similarity": (
                    semantic.get(
                        "source_copy_similarity",
                        0,
                    )
                ),
                "recent_post_similarity": (
                    semantic.get(
                        "recent_post_similarity",
                        0,
                    )
                ),
                "claim_support_json": json.dumps(
                    output.get("claim_support", []),
                    ensure_ascii=False,
                ),
                "final_validation": validation,
            }

        all_reasons.extend(attempt_reasons)

    return {
        "status": "REVIEW_REQUIRED",
        # Never reuse the pre-generated candidate caption.
        "public_post_text": "",
        "caption_attempt_count": attempt_limit,
        "caption_attempts": attempts,
        "blocked_reasons": sorted(set(
            all_reasons
            + ["caption_retry_limit_reached"]
        )),
        "caption_provider": str(
            attempts[-1].get("provider_name", "")
            if attempts
            else ""
        ),
        "caption_provider_version": str(
            attempts[-1].get(
                "provider_version",
                "",
            )
            if attempts
            else ""
        ),
        "alignment_status": "BLOCKED",
        "final_alignment_score": 0,
        "main_claim_coverage": 0,
        "unsupported_claim_count": 1,
        "source_copy_similarity": 1,
        "recent_post_similarity": 1,
        "claim_support_json": "[]",
    }


def _caption_clip_fields(
    caption: dict[str, Any],
) -> dict[str, Any]:
    return {
        "public_post_text": (
            caption.get("public_post_text", "")
        ),
        "public_post_validator_status": (
            "PASS"
            if caption.get("status") == "PASS"
            else "BLOCKED"
        ),
        "caption_provider": (
            caption.get("caption_provider", "")
        ),
        "caption_provider_version": (
            caption.get(
                "caption_provider_version",
                "",
            )
        ),
        "alignment_status": (
            caption.get("alignment_status", "")
        ),
        "final_alignment_score": (
            caption.get("final_alignment_score", "")
        ),
        "main_claim_coverage": (
            caption.get("main_claim_coverage", "")
        ),
        "unsupported_claim_count": (
            caption.get(
                "unsupported_claim_count",
                "",
            )
        ),
        "source_copy_similarity": (
            caption.get(
                "source_copy_similarity",
                "",
            )
        ),
        "recent_post_similarity": (
            caption.get(
                "recent_post_similarity",
                "",
            )
        ),
        "claim_support_json": (
            caption.get("claim_support_json", "[]")
        ),
        "text_generation_status": (
            "done"
            if caption.get("status") == "PASS"
            else "failed"
        ),
        "generated_at": (
            datetime.now(timezone.utc).isoformat()
        ),
        "notes": (
            "final_caption_attempts="
            + json.dumps(
                caption.get("caption_attempts", []),
                ensure_ascii=False,
                separators=(",", ":"),
            )[:4500]
        ),
    }


def _mark_caption_review_required(
    client: SheetsClient,
    *,
    clip_id: str,
    caption: dict[str, Any],
) -> None:
    fields = _caption_clip_fields(caption)

    fields.update({
        "public_post_text": "",
        "post_status": "REVIEW_REQUIRED",
        "reviewer_status": "REVIEW_REQUIRED",
        "clip_status": "REVIEW_REQUIRED",
        "last_error": (
            "caption:"
            + "|".join(
                str(reason)
                for reason in caption.get(
                    "blocked_reasons",
                    [],
                )[:12]
            )
        ),
    })

    client.update_video_clip_candidate(
        clip_id,
        **fields,
    )

def select_candidate(
    clips: list[dict[str, Any]],
    source_videos: list[dict[str, Any]],
    posted_results: list[dict[str, Any]],
    account_id: str = "liver_manager",
    media_assets: list[dict[str, Any]] | None = None,
    excluded_clip_ids: set[str] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[str]]:
    sources = {str(row.get("source_video_id", "")): row for row in source_videos}
    posted_clip_ids = {str(row.get("clip_candidate_id", "")) for row in posted_results if row.get("clip_candidate_id")}
    prepared_clip_ids = {
        str(row.get("clip_candidate_id") or row.get("video_clip_id") or "")
        for row in (media_assets or [])
        if (row.get("clip_candidate_id") or row.get("video_clip_id"))
        and (
            str(row.get("upload_status", "")).upper() == "UPLOADED"
            or bool(row.get("storage_url") or row.get("cloudinary_url"))
        )
    }
    reasons: list[str] = []
    eligible = []
    excluded = excluded_clip_ids or set()
    for clip in clips:
        clip_id = str(clip.get("clip_candidate_id") or clip.get("clip_id") or "")
        if clip_id in excluded:
            reasons.append(f"{clip_id}:attempted_this_run")
            continue
        if is_quarantined(clip):
            reasons.append(f"{clip_id}:quarantined")
            continue
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
        if (
            clip_id in prepared_clip_ids
            or str(clip.get("upload_status", "")).upper() == "UPLOADED"
            or bool(clip.get("media_asset_id") or clip.get("clip_media_asset_id") or clip.get("storage_url"))
        ):
            reasons.append(f"{clip_id}:already_prepared")
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
        eligible.append((clip, source_video))
    if not eligible:
        return None, None, reasons
    source_usage: dict[str, int] = {}
    platform_usage: dict[str, int] = {}
    for row in posted_results:
        if str(row.get("account_id", "")) != account_id or str(row.get("status", "")).upper() != "POSTED":
            continue
        source_video = sources.get(str(row.get("source_video_id", "")), {})
        source_id = str(source_video.get("source_id", ""))
        platform = str(source_video.get("platform", "")).lower()
        if source_id:
            source_usage[source_id] = source_usage.get(source_id, 0) + 1
        if platform:
            platform_usage[platform] = platform_usage.get(platform, 0) + 1
    eligible.sort(key=lambda pair: (
        source_usage.get(str(pair[1].get("source_id", "")), 0),
        platform_usage.get(str(pair[1].get("platform", "")).lower(), 0),
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
    excluded_clip_ids: set[str] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None, list[str]]:
    """Select one uploaded-but-never-posted approved asset for a timed slot."""
    clips_by_id = {str(row.get("clip_candidate_id") or row.get("clip_id") or ""): row for row in clips}
    videos_by_id = {str(row.get("source_video_id", "")): row for row in source_videos}
    posted_clips = {str(row.get("clip_candidate_id", "")) for row in posted_results if row.get("clip_candidate_id")}
    posted_assets = {str(row.get("media_asset_id", "") or row.get("media_id", "")) for row in posted_results}
    reasons: list[str] = []
    candidates: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    excluded = excluded_clip_ids or set()
    for asset in media_assets:
        media_id = str(asset.get("media_asset_id") or asset.get("media_id") or "")
        clip_id = str(asset.get("clip_candidate_id") or asset.get("video_clip_id") or "")
        clip = clips_by_id.get(clip_id)
        source_video = videos_by_id.get(str((clip or {}).get("source_video_id") or asset.get("source_video_id") or ""))
        if str(asset.get("account_id", "")) != account_id:
            continue
        if clip_id in excluded:
            reasons.append(f"{media_id}:attempted_this_run")
            continue
        if clip and is_quarantined(clip):
            reasons.append(f"{media_id}:clip_quarantined")
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

        # Legacy system-generated videos are not valid approved-source clips.
        # Fail closed even when their rows still carry owned/approved metadata.
        synthetic_identity = "|".join(
            str(value or "").strip().lower()
            for value in (
                asset.get("media_origin"),
                asset.get("source_platform"),
                asset.get("provider_name"),
                clip.get("media_origin"),
                clip.get("source_platform"),
                source_video.get("platform"),
                media_id,
                clip_id,
            )
        )
        if (
            "system_generated" in synthetic_identity
            or "system-owned" in synthetic_identity
            or "system_owned" in synthetic_identity
            or "pillow+ffmpeg" in synthetic_identity
        ):
            reasons.append(f"{media_id}:synthetic_media_forbidden")
            continue

        clip_status = str(
            clip.get("clip_status")
            or clip.get("reviewer_status")
            or ""
        ).upper()
        if clip_status not in {"READY", "AUTO_APPROVED", "MEDIA_READY"}:
            reasons.append(f"{media_id}:clip_not_ready")
            continue

        # Reuse the final-caption evidence contract at selection time so an
        # uploaded asset cannot be chosen unless its transcript, exact time
        # range and individual parent-video URL are all available.
        bundle, _transcript_excerpt, grounding_reasons = (
            _build_final_caption_bundle(
                clip=clip,
                source_video=source_video,
                account_id=account_id,
                media_asset=asset,
            )
        )
        if bundle is None or grounding_reasons:
            for reason in grounding_reasons or [
                "final_caption_evidence_missing"
            ]:
                reasons.append(f"{media_id}:{reason}")
            continue

        candidates.append((clip, source_video, asset))
    if not candidates:
        return None, None, None, reasons
    candidates.sort(key=lambda row: str(row[2].get("uploaded_at") or row[2].get("created_at") or ""))
    clip, source_video, asset = candidates[0]
    return clip, source_video, asset, reasons



def _candidate_block_status(
    reasons: list[str],
) -> str:
    """Map an empty candidate set to an explicit fail-closed state."""
    normalized = "|".join(
        str(reason).lower()
        for reason in reasons
    )

    if "public_post_validator_blocked" in normalized:
        return "BLOCKED_TONE_FAILED"

    if any(
        marker in normalized
        for marker in (
            "rights_or_permission_blocked",
            "rights_blocked",
            "permission_blocked",
        )
    ):
        return "BLOCKED_NO_APPROVED_SOURCE"

    if any(
        marker in normalized
        for marker in (
            "source_video_missing",
            "clip_or_source_video_missing",
            "individual_video_url_required",
            "planned_or_invalid_video_id",
            "not_uploaded",
        )
    ):
        return "BLOCKED_NO_SOURCE_MEDIA"

    if any(
        marker in normalized
        for marker in (
            "clip_not_ready",
            "transcript_grounding_required",
            "semantic_alignment_required",
            "quarantined",
        )
    ):
        return "REVIEW_REQUIRED"

    if not reasons:
        return "BLOCKED_NO_SOURCE_MEDIA"

    return "NO_POST"


def _validation_failure_status(
    validation: dict[str, Any],
) -> str:
    """Separate caption/tone failure from non-text review failures."""
    reasons = [
        str(reason).lower()
        for reason in validation.get(
            "blocked_reasons",
            [],
        )
    ]

    tone_markers = (
        "public_post_validator",
        "account_fit",
        "persona_",
        "quality_",
        "naturalness_",
        "reader_value_",
        "cta_pressure_",
        "risk_score_",
        "internal_terms",
        "source_metadata",
        "too_short",
        "too_long",
    )

    if any(
        marker in reason
        for reason in reasons
        for marker in tone_markers
    ):
        return "BLOCKED_TONE_FAILED"

    return "REVIEW_REQUIRED"

def build_plan(
    *,
    apply: bool,
    confirm: bool,
    client: SheetsClient | None = None,
    account_id: str = "liver_manager",
    prepare_only: bool = False,
    post_saved_media: bool = False,
    slot_id: str = "",
    excluded_clip_ids: set[str] | None = None,
) -> dict[str, Any]:
    media_cfg = _load(MEDIA_CONFIG)
    autonomous_cfg = _load(AUTONOMOUS_CONFIG)
    blocked = []
    # Never convert a generated-clip slot into text when a resource gate is
    # unavailable. The caller receives a safe NO_POST instead.
    if _true(os.environ.get("BLOCK_MEDIA_SLOT")):
        return {
            "status": "NO_POST",
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
            "blocked_reasons": ["resource_budget_media_slot"],
        }
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
    # Asset preparation does not publish anything. Post caps belong to the
    # posting path and must not prevent the inventory builder from preparing
    # the next approved clip for a future slot.
    if not prepare_only:
        if len(today_posts) >= daily_cap:
            blocked.append("daily_post_cap_reached")
        if len(media_today) >= media_cap:
            blocked.append("media_daily_post_cap_reached")
    if post_saved_media:
        clip, source_video, selected_asset, skipped = select_saved_media_candidate(
            clips, source_videos, media_assets, posted, account_id, excluded_clip_ids,
        )
    else:
        clip, source_video, skipped = select_candidate(
            clips, source_videos, posted, account_id, media_assets, excluded_clip_ids,
        )
        selected_asset = None
    no_candidate = not clip or not source_video
    candidate_status = ""

    if no_candidate:
        blocked.append("no_eligible_media_candidate")
        candidate_status = _candidate_block_status(
            skipped
        )

    fatal_blocked = [
        reason
        for reason in blocked
        if reason != "no_eligible_media_candidate"
    ]
    # The final caption is generated only after the real media asset is confirmed.
    text = ""

    return {
        "status": (
            "BLOCKED"
            if fatal_blocked and apply
            else candidate_status
            if no_candidate
            else "PLAN_ONLY"
        ),
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
    caption = _generate_final_media_caption(
        clip=clip,
        source_video=source_video,
        media_asset=asset,
        account_id=account_id,
        recent_posts=_recent_public_posts(
            _records(client, "posted_results"),
            account_id,
        ),
        max_attempts=3,
    )

    if caption.get("status") != "PASS":
        _mark_caption_review_required(
            client,
            clip_id=clip_id,
            caption=caption,
        )

        return {
            **plan,
            "status": "REVIEW_REQUIRED",
            "selected_clip": {
                **clip,
                **_caption_clip_fields(caption),
            },
            "public_post_preview": "",
            "caption_result": caption,
            "retryable_candidate_failure": False,
            "would_post_video": False,
        }

    caption_fields = _caption_clip_fields(caption)
    clip.update(caption_fields)

    client.update_video_clip_candidate(
        clip_id,
        **caption_fields,
    )

    text = str(
        caption.get("public_post_text", "")
    )

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
        **_alignment_fields(clip),
    })
    if validation["status"] != "PASS":
        reason = "media_validator:" + "|".join(validation.get("blocked_reasons", []))
        failure = _record_clip_failure(client, clip, account_id=account_id, reason=reason)
        return {
            **plan,
            "status": _validation_failure_status(validation),
            "selected_clip": clip,
            "public_post_preview": public_preview(text),
            "caption_result": caption,
            "media_validation": validation,
            "retryable_candidate_failure": True,
            "candidate_quarantined": is_quarantined(failure),
        }
    slot_id = str(plan.get("slot_id", ""))
    if slot_id:
        claim = claim_slot_run(client, account_id, slot_id)
        if claim.get("status") != "CLAIMED":
            return {
                **plan,
                "status": "SKIPPED",
                "reason": claim.get("reason", "slot_not_claimed"),
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
        "generation_mode": "approved_saved_media",
        "slot_id": slot_id,
        "business_date_jst": business_date(),
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
        "caption_provider": clip.get("caption_provider", ""),
        "caption_provider_version": clip.get("caption_provider_version", ""),
        **_alignment_fields(clip),
        "claim_support_json": clip.get("claim_support_json", ""),
        "media_url": media_url,
        "media_status": "UPLOADED",
        "media_required": "true",
        "media_type": "video",
        "media_origin": "approved_source_clip",
        "duration_seconds": asset.get("duration_seconds") or asset.get("duration", ""),
        "aspect_ratio": asset.get("aspect_ratio", "9:16"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    existing_queue_ids = {str(row.get("queue_id", "")) for row in _records(client, "queue")}
    if queue_id not in existing_queue_ids:
        _append(client, "queue", queue_row)
    result = process_one(client, queue_row, dry_run=False, confirm_real_post=True)
    final_status = str(result.get("status", ""))
    failure_state: dict[str, Any] | None = None
    externally_posted = final_status in {"POSTED", "POSTED_SAVE_FAILED"}
    if externally_posted:
        _clear_clip_failure(client, clip)
    else:
        failure_state = _record_clip_failure(
            client,
            clip,
            account_id=account_id,
            reason=f"publisher_uncertain:{result.get('reason', final_status or 'unknown')}",
        )
    retry_status = "QUARANTINED" if failure_state and is_quarantined(failure_state) else "VERIFY_REQUIRED"
    client.update_video_clip_candidate(
        clip_id,
        post_status="POSTED" if externally_posted else final_status,
        reviewer_status="AUTO_APPROVED" if externally_posted else retry_status,
        clip_status="POSTED" if externally_posted else retry_status,
    )
    if externally_posted:
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
    return {
        **plan,
        "status": final_status,
        "selected_clip": clip,
        "public_post_preview": public_preview(text),
        "caption_result": caption,
        "queue_id": queue_id,
        "media_asset_id": media_id,
        "post_result": result,
        "media_pdca": media_pdca,
        "content_slot_run": slot_record,
            "would_download": False, "would_cut": False, "would_upload": False, "would_post_video": False}


def execute(plan: dict[str, Any], client: SheetsClient) -> dict[str, Any]:
    plan_status = str(plan.get("status", ""))

    if (
        plan_status.startswith("BLOCKED")
        or plan_status in {
            "REVIEW_REQUIRED",
            "NO_POST",
        }
    ):
        return plan
    slot_id = str(plan.get("slot_id", ""))
    if slot_id and existing_slot_status(client, str(plan["account_id"]), slot_id) in POSTED_SLOT_STATUSES:
        return {**plan, "status": "SKIPPED", "reason": "slot_already_posted", "would_post_video": False}
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
        reason = "download:" + "|".join(download.get("blocked_reasons", []) or [str(download.get("status", "failed"))])
        failure = _record_clip_failure(client, clip, account_id=account_id, reason=reason)
        client.save_source_video({**source_video, "download_status": "FAILED", "skip_reason": reason})
        return {
            **plan, "status": "BLOCKED_MEDIA_DOWNLOAD_FAILED", "download_result": download,
            "would_download": False, "retryable_candidate_failure": True,
            "candidate_quarantined": is_quarantined(failure),
        }
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
        reason = "cut:" + "|".join(cut.get("blocked_reasons", []) or [str(cut.get("status", "failed"))])
        failure = _record_clip_failure(client, clip, account_id=account_id, reason=reason)
        client.update_video_clip_candidate(clip_id, cut_status="FAILED", notes=reason)
        return {
            **plan, "status": "BLOCKED_CLIP_FAILED", "cut_result": cut,
            "would_cut": False, "retryable_candidate_failure": True,
            "candidate_quarantined": is_quarantined(failure),
        }
    asset = dict(cut["media_asset_result"])
    asset["account_id"] = account_id
    asset["clip_candidate_id"] = clip_id

    upload_args = SimpleNamespace(upload=True, confirm_upload=True, dry_run=False)
    upload = execute_cloudinary_uploads(build_upload_plan(upload_args, [asset]))
    if upload.get("status") != "UPLOADED":
        reason = "upload:" + "|".join(upload.get("blocked_reasons", []) or [str(upload.get("status", "failed"))])
        failure = _record_clip_failure(client, clip, account_id=account_id, reason=reason)
        # Standard GitHub-hosted runners are ephemeral. A failed upload cannot
        # rely on this local path in the next run, so retry the bounded
        # download/cut sequence instead of pretending the clip is durable.
        client.update_video_clip_candidate(clip_id, cut_status="RETRY_REQUIRED", local_clip_path="", upload_status="FAILED")
        return {
            **plan, "status": "FAILED_UPLOAD", "upload_result": upload,
            "would_upload": False, "retryable_candidate_failure": True,
            "candidate_quarantined": is_quarantined(failure),
        }
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

    caption = _generate_final_media_caption(
        clip=clip,
        source_video=source_video,
        media_asset={
            **asset,
            **uploaded,
            "media_asset_id": media_id,
            "storage_url": media_url,
            "upload_status": "UPLOADED",
        },
        account_id=account_id,
        recent_posts=_recent_public_posts(
            _records(client, "posted_results"),
            account_id,
        ),
        max_attempts=3,
    )

    if caption.get("status") != "PASS":
        _mark_caption_review_required(
            client,
            clip_id=clip_id,
            caption=caption,
        )

        return {
            **plan,
            "status": "REVIEW_REQUIRED",
            "selected_clip": {
                **clip,
                **_caption_clip_fields(caption),
            },
            "media_asset_id": media_id,
            "public_post_preview": "",
            "caption_result": caption,
            "retryable_candidate_failure": False,
            "would_download": False,
            "would_cut": False,
            "would_upload": False,
            "would_post_video": False,
        }

    caption_fields = _caption_clip_fields(caption)
    clip.update(caption_fields)

    client.update_video_clip_candidate(
        clip_id,
        **caption_fields,
    )

    text = str(
        caption.get("public_post_text", "")
    )

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
        **_alignment_fields(clip),
    })
    if validation["status"] != "PASS":
        reason = "media_validator:" + "|".join(validation.get("blocked_reasons", []))
        failure = _record_clip_failure(client, clip, account_id=account_id, reason=reason)
        client.update_video_clip_candidate(clip_id, cut_status="DONE", upload_status="UPLOADED", storage_url=media_url, post_status="BLOCKED")
        return {
            **plan,
            "status": _validation_failure_status(validation),
            "selected_clip": clip,
            "public_post_preview": public_preview(text),
            "caption_result": caption,
            "media_validation": validation,
            "retryable_candidate_failure": True,
            "candidate_quarantined": is_quarantined(failure),
        }

    if plan.get("prepare_only"):
        _clear_clip_failure(client, clip)
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
            "selected_clip": clip,
            "public_post_preview": public_preview(text),
            "caption_result": caption,
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
        "caption_provider": clip.get("caption_provider", ""),
        "caption_provider_version": clip.get("caption_provider_version", ""),
        **_alignment_fields(clip),
        "claim_support_json": clip.get("claim_support_json", ""),
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
    failure_state: dict[str, Any] | None = None
    if final_status == "POSTED":
        _clear_clip_failure(client, clip)
    else:
        failure_state = _record_clip_failure(
            client,
            clip,
            account_id=account_id,
            reason=f"publisher_uncertain:{result.get('reason', final_status or 'unknown')}",
        )
    retry_status = "QUARANTINED" if failure_state and is_quarantined(failure_state) else "VERIFY_REQUIRED"
    client.update_video_clip_candidate(
        clip_id,
        cut_status="DONE",
        local_clip_path=asset.get("local_path", ""),
        clip_media_asset_id=media_id,
        media_asset_id=media_id,
        storage_url=media_url,
        upload_status="UPLOADED",
        post_status="POSTED" if final_status == "POSTED" else final_status,
        reviewer_status="AUTO_APPROVED" if final_status == "POSTED" else retry_status,
        clip_status="POSTED" if final_status == "POSTED" else retry_status,
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
        "selected_clip": clip,
        "public_post_preview": public_preview(text),
        "caption_result": caption,
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
    parser.add_argument("--slot-id", default="", help="canonical approved_source_clip slot for idempotency and reporting")
    args = parser.parse_args()
    if args.prepare_only and args.post_saved_media:
        print(json.dumps({"status": "BLOCKED", "blocked_reasons": ["prepare_only_and_post_saved_media_are_mutually_exclusive"]}, ensure_ascii=False))
        return 1

    client = None
    if args.use_sheets:
        cfg = get_config()
        client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    excluded_clip_ids: set[str] = set()
    plan = build_plan(
        account_id=args.account_id,
        apply=args.apply,
        confirm=args.confirm_production_media,
        client=client,
        prepare_only=args.prepare_only,
        post_saved_media=args.post_saved_media,
        slot_id=args.slot_id,
        excluded_clip_ids=excluded_clip_ids,
    )
    if args.slot_id:
        slot = slot_by_id(args.account_id, args.slot_id)
        if not slot or slot.get("post_type") != "approved_source_clip":
            plan = {**plan, "status": "BLOCKED", "blocked_reasons": ["slot_id must be a approved_source_clip slot"]}
        else:
            plan["slot_id"] = args.slot_id
    if (
        args.apply
        and args.confirm_production_media
        and client
        and plan.get("status") == "PLAN_ONLY"
    ):
        candidate_attempts: list[dict[str, Any]] = []
        max_attempts = min(3, int(_load(MEDIA_CONFIG).get("max_clip_candidates_per_video", 3) or 3))
        for _ in range(max_attempts):
            result = execute(plan, client)
            candidate_attempts.append({
                "clip_candidate_id": plan.get("selected_clip_candidate_id", ""),
                "status": result.get("status", ""),
                "candidate_quarantined": bool(result.get("candidate_quarantined")),
            })
            if not result.get("retryable_candidate_failure"):
                plan = {**result, "candidate_attempts": candidate_attempts}
                break
            excluded_clip_ids.add(str(plan.get("selected_clip_candidate_id", "")))
            next_plan = build_plan(
                account_id=args.account_id,
                apply=True,
                confirm=True,
                client=client,
                prepare_only=args.prepare_only,
                post_saved_media=args.post_saved_media,
                slot_id=args.slot_id,
                excluded_clip_ids=excluded_clip_ids,
            )
            if next_plan.get("status") != "PLAN_ONLY":
                plan = {
                    **result,
                    "candidate_attempts": candidate_attempts,
                    "next_candidate_status": next_plan.get("status"),
                    "next_candidate_reasons": next_plan.get("blocked_reasons", []),
                }
                break
            plan = next_plan
        else:
            plan = {
                **plan,
                "status": "REVIEW_REQUIRED",
                "candidate_attempts": candidate_attempts,
                "blocked_reasons": [
                    "candidate_attempt_limit_reached"
                ],
            }
    if args.slot_id and (
        str(plan.get("status", "")).startswith(
            ("BLOCKED", "FAILED")
        )
        or plan.get("status") in {
            "NO_POST",
            "REVIEW_REQUIRED",
            "SAFETY_STOP_MEDIA_GATE",
            "SAFETY_STOP_MEDIA_VALIDATOR",
        }
    ):
        plan = {
            **plan,
            "status": "SKIPPED_NO_VALID_MEDIA",
            "no_post_reason": "media_slot_has_no_ready_approved_source_clip",
            "would_post": False,
        }
    safe = {k: v for k, v in plan.items() if k not in {"selected_clip", "selected_source_video"}}
    print(json.dumps(safe, ensure_ascii=False, indent=2))
    final_status = str(plan.get("status", ""))

    return 1 if (
        final_status.startswith(("FAILED", "BLOCKED"))
        or final_status == "REVIEW_REQUIRED"
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
