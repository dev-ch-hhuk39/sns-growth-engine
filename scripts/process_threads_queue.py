#!/usr/bin/env python3
"""Process one or more Threads queue rows safely.

Default mode is dry-run. Real posting requires all of:
- --confirm-real-post
- PUBLISH_ENABLED=true
- ALLOW_REAL_THREADS_POST=true

This worker never posts X and never retries immediately after a failure.
Beauty rows require the normal READY review gate plus the dedicated
BEAUTY_PRODUCTION_ENABLED runtime gate.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from config_loader import get_config  # noqa: E402
from media_post_validator import publisher_media_type, validate_media_post  # noqa: E402
from publishers.threads_publisher import ThreadsPublisher  # noqa: E402
from public_post_quality import extract_public_post_text, final_public_post_validator, public_preview  # noqa: E402
from generation.source_copyedit import validate_source_preserving_public_post  # noqa: E402
from direct_caption_policy import queue_caption_mode  # noqa: E402
from hybrid_ai_gate import hybrid_ai_gate_passed, requires_hybrid_ai_gate  # noqa: E402
from hybrid_ai_source_context import build_source_context  # noqa: E402
from publisher_delivery_contract import delivery_idempotency_key, retry_disposition, verify_posted_result_persistence  # noqa: E402
from metrics_collection_schedule import build_metric_collection_jobs  # noqa: E402
from sheets_record_reader import read_records_safely  # noqa: E402
from sheets_client import SheetsClient  # noqa: E402

# 投稿対象として選ばれるのは READY のみ。
# WAITING_REVIEW はレビュー待ち（人間が approve_queue.py で READY に昇格させるまで投稿不可）、
# PLANNED は計画段階、DRAFT は生成/PDCA候補で、いずれも投稿対象にしない。
# READY への昇格は approve_queue.py（人間承認）または auto_approve_queue.py（AUTO_READY）経由のみ。
# 生成系CLIは直接 READY を書かない。
ELIGIBLE_STATUSES = {"READY"}
FINAL_OR_LOCKED_STATUSES = {
    "POSTED",
    "PROCESSING",
    "FAILED",
    "POSTED_SAVE_FAILED",
    "POSTED_SAVE_UNVERIFIED",
    "PUBLISH_OUTCOME_UNVERIFIED",
    "DUPLICATE_BLOCKED",
}
BEAUTY_ACCOUNT = "beauty_account"
BEAUTY_PIPELINE_CONFIG = ROOT / "config" / "beauty_account_pipeline.json"

# media_status がこれらのときだけ「投稿に使える media」とみなす
MEDIA_OK_STATUSES = {"ATTACHED", "UPLOADED"}

# Sheets ヘッダー行のキャッシュ（ws オブジェクトの id をキーにする）
_headers_cache: dict[int, list[str]] = {}

FALLBACK_DIR = ROOT / "output" / "posted_results_fallback"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_true(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def beauty_production_configured() -> bool:
    try:
        config = json.loads(BEAUTY_PIPELINE_CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(
        config.get("status") == "review_required_production"
        and config.get("scheduled_publish_enabled") is True
        and config.get("real_post_enabled") is True
        and config.get("auto_ready_enabled") is False
    )


def beauty_publish_gate(*, dry_run: bool) -> tuple[bool, str]:
    if not beauty_production_configured():
        return False, "beauty_production_config_not_enabled"
    if not dry_run and not is_true(os.environ.get("BEAUTY_PRODUCTION_ENABLED", "false")):
        return False, "BEAUTY_PRODUCTION_ENABLED is not true"
    return True, ""


def get_ws(client: SheetsClient, logical: str):
    return client._ws(logical)


def records(client: SheetsClient, logical: str) -> list[dict[str, Any]]:
    return read_records_safely(
        client,
        logical,
    )


def row_by_key(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {str(r.get(key, "")): r for r in rows if str(r.get(key, ""))}


def _get_headers(ws) -> list[str]:
    """ヘッダー行を取得する。セッション内でキャッシュし、429 発生時は指数バックオフでリトライする。"""
    ws_id = id(ws)
    if ws_id in _headers_cache:
        return _headers_cache[ws_id]
    delays = [0, 10, 30, 60]
    for attempt, delay in enumerate(delays):
        if delay > 0:
            print(f"[RATE_LIMIT] Sheets 429; waiting {delay}s (attempt {attempt + 1}/{len(delays)})")
            time.sleep(delay)
        try:
            headers = ws.row_values(1)
            _headers_cache[ws_id] = headers
            return headers
        except Exception as exc:
            msg = str(exc).lower()
            if "429" in msg or "quota" in msg:
                if attempt < len(delays) - 1:
                    continue
            raise
    return []


def _col_letter(col: int) -> str:
    letters = ""
    while col:
        col, rem = divmod(col - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _call_with_rate_limit_retry(label: str, fn):
    delays = [0, 10, 30, 60]
    for attempt, delay in enumerate(delays):
        if delay > 0:
            print(f"[RATE_LIMIT] Sheets 429 during {label}; waiting {delay}s (attempt {attempt + 1}/{len(delays)})")
            time.sleep(delay)
        try:
            return fn()
        except Exception as exc:
            msg = str(exc).lower()
            if ("429" in msg or "quota" in msg) and attempt < len(delays) - 1:
                continue
            raise


def append_row(client: SheetsClient, logical: str, row: dict[str, Any]) -> None:
    ws = get_ws(client, logical)
    headers = _get_headers(ws)
    values = [str(row.get(h, "")) for h in headers]
    _call_with_rate_limit_retry(
        f"append_row:{logical}",
        lambda: ws.append_row(values, value_input_option="USER_ENTERED"),
    )


def update_row(client: SheetsClient, logical: str, key: str, key_value: str, fields: dict[str, Any]) -> bool:
    ws = get_ws(client, logical)
    headers = _get_headers(ws)
    if key not in headers:
        # The caller has already made the fail-closed posting decision. A
        # legacy or partially provisioned sheet must not turn that safe block
        # into an uncaught exception; schema health reports the missing column.
        return False
    cell = _call_with_rate_limit_retry(
        f"find:{logical}:{key}",
        lambda: ws.find(key_value, in_column=headers.index(key) + 1),
    )
    if cell is None:
        return False
    update_ranges = []
    for field, value in fields.items():
        if field in headers:
            col = headers.index(field) + 1
            update_ranges.append({
                "range": f"{_col_letter(col)}{cell.row}",
                "values": [[str(value)]],
            })
    if update_ranges:
        _call_with_rate_limit_retry(
            f"batch_update:{logical}:{key_value}",
            lambda: ws.batch_update(update_ranges, value_input_option="USER_ENTERED"),
        )
    return True


def find_social_for_queue(client: SheetsClient, queue_row: dict[str, Any], social_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    draft_id = str(queue_row.get("draft_id", ""))
    for row in social_rows:
        if row.get("draft_id") == draft_id and str(row.get("platform", "")).lower() == "threads":
            return row
    return None


def find_draft_for_queue(queue_row: dict[str, Any], drafts_by_id: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    return drafts_by_id.get(str(queue_row.get("draft_id", "")))


def text_for_queue(queue_row: dict[str, Any], social: dict[str, Any] | None, draft: dict[str, Any] | None) -> str:
    if str(queue_row.get("public_post_text", "")).strip():
        return extract_public_post_text(queue_row.get("public_post_text", ""))
    if social and str(social.get("text", "")).strip():
        return extract_public_post_text(social.get("text", ""))
    if draft:
        for key in ("body_md", "content"):
            if str(draft.get(key, "")).strip():
                return extract_public_post_text(draft.get(key, ""))
    return ""


def resolve_queue_media(queue_row: dict[str, Any]) -> dict[str, Any]:
    """queue 行から media 関連フィールドを防御的に読む。

    queue タブに存在する列は media_asset_id のみで、media_url / media_status /
    media_required は列が無いことがあるため .get() で安全に読む。
    media_status が ATTACHED / UPLOADED かつ media_url があるときだけ
    「投稿に使える media」とみなす。
    """
    media_asset_id = str(queue_row.get("media_asset_id", "")).strip()
    media_url = str(queue_row.get("media_url", "")).strip()
    def json_list(name: str) -> list[str]:
        try:
            value = json.loads(str(queue_row.get(name, "") or "[]"))
            return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []
        except (TypeError, json.JSONDecodeError):
            return []
    media_urls = json_list("media_urls_json") or ([media_url] if media_url else [])
    media_asset_ids = json_list("media_asset_ids_json") or ([media_asset_id] if media_asset_id else [])
    media_types = [item.lower() for item in json_list("media_types_json")]
    media_status = str(queue_row.get("media_status", "")).strip().upper()
    media_required = is_true(queue_row.get("media_required", "false"))
    status_ok = media_status in MEDIA_OK_STATUSES
    media_usable = bool(media_urls) and status_ok
    block_reason = ""
    if media_required and not media_usable:
        block_reason = "MEDIA_REQUIRED_MISSING"
    return {
        "media_asset_id": media_asset_id,
        "media_asset_ids": media_asset_ids,
        "media_url": media_url,
        "media_urls": media_urls,
        "media_status": media_status,
        "source_video_id": queue_row.get("source_video_id", ""),
        "clip_candidate_id": queue_row.get("clip_candidate_id", queue_row.get("video_clip_id", "")),
        "media_required": media_required,
        "media_usable": media_usable,
        "effective_media_url": media_urls[0] if media_usable else "",
        "effective_media_urls": media_urls if media_usable else [],
        "media_type": (media_types[0] if media_types else str(queue_row.get("media_type", "video")).lower()),
        "media_types": media_types or [str(queue_row.get("media_type", "video")).lower()] * len(media_urls),
        "block_reason": block_reason,
    }


def duplicate_reason(
    *,
    queue_row: dict[str, Any],
    social: dict[str, Any] | None,
    text: str,
    posted_rows: list[dict[str, Any]],
    media_asset_id: str = "",
) -> str:
    queue_id = str(queue_row.get("queue_id", ""))
    draft_id = str(queue_row.get("draft_id", ""))
    derivative_id = str(social.get("derivative_id", "")) if social else ""
    account_id = str(queue_row.get("account_id", ""))

    for posted in posted_rows:
        status = str(posted.get("status", "")).upper()
        platform = str(posted.get("platform", "")).lower()
        if platform and platform != "threads":
            continue
        if queue_id and str(posted.get("queue_id", "")) == queue_id:
            return f"queue_id already in posted_results: {queue_id}"
        if derivative_id and str(posted.get("derivative_id", "")) == derivative_id:
            return f"derivative_id already in posted_results: {derivative_id}"
        if draft_id and str(posted.get("draft_id", "")) == draft_id and status in {"POSTED", "RECOVERED"}:
            return f"draft_id already posted/recovered: {draft_id}"
        same_text = (
            status == "POSTED"
            and str(posted.get("account_id", "")) == account_id
            and str(posted.get("platform", "")).lower() == "threads"
            and str(posted.get("posted_text", "")).strip() == text.strip()
            and text.strip()
        )
        if same_text:
            return "same text/account/platform already POSTED"
    return ""


def select_candidates(client: SheetsClient, account_id: str | None, max_posts: int, queue_ids: set[str] | None = None) -> list[dict[str, Any]]:
    rows = records(client, "queue")
    candidates: list[dict[str, Any]] = []
    for row in rows:
        row_account = str(row.get("account_id", ""))
        status = str(row.get("status", "")).upper()
        platform = str(row.get("platform", "")).lower()
        if account_id and row_account != account_id:
            continue
        if queue_ids is not None and str(row.get("queue_id", "")) not in queue_ids:
            continue
        if platform != "threads":
            continue
        if status in FINAL_OR_LOCKED_STATUSES:
            continue
        if status not in ELIGIBLE_STATUSES:
            continue
        candidates.append(row)
    def sort_key(row: dict[str, Any]) -> tuple[int, int, str]:
        # A historical fallback row may have been written before the Sheet
        # exposed public_post_text.  Preserve it for audit, but do not let an
        # inevitably-empty legacy row starve a newly generated safe candidate.
        generation_mode = str(row.get("generation_mode", ""))
        queue_id = str(row.get("queue_id", ""))
        missing_legacy_public_text = (
            (generation_mode.startswith("slot_fallback_") or queue_id.startswith("slot_fallback_"))
            and not str(row.get("public_post_text", "")).strip()
        )
        try:
            priority = int(str(row.get("priority", "999") or "999"))
        except ValueError:
            priority = 999
        return (1 if missing_legacy_public_text else 0, priority, queue_id)

    candidates.sort(key=sort_key)
    return candidates[:max_posts]


def log_event(client: SheetsClient, account_id: str, status: str, message: str, details: dict[str, Any] | None = None) -> None:
    # Audit telemetry must never prevent a completed duplicate check or a
    # real publish from returning its durable result when Sheets is rate-limited.
    try:
        append_row(client, "logs", {
            "log_id": f"threads_queue_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "timestamp": now_iso(),
            "account_id": account_id,
            "operation": "process_threads_queue",
            "level": "INFO" if status in {"DRY_RUN", "POSTED", "SKIPPED"} else "ERROR",
            "status": status,
            "message": message,
            "details": json.dumps(details or {}, ensure_ascii=False),
        })
    except Exception as exc:
        print(f"[WARN] noncritical log save skipped: {type(exc).__name__}")


def save_pdca_initial(client: SheetsClient, queue_row: dict[str, Any], result_id: str) -> None:
    account_id = str(queue_row.get("account_id", ""))
    created_at = now_iso()
    append_row(client, "pdca_runs", {
        "run_id": f"pdca_threads_{result_id}",
        "account_id": account_id,
        "platform": "threads",
        "days": "0",
        "total_results": "1",
        "suggestion_count": "1",
        "next_jobs_count": "1",
        "best_content_type": "manual_pending",
        "best_er": "",
        "created_at": created_at,
        "notes": f"Initial PDCA placeholder after queue post result_id={result_id}; metrics pending.",
    })
    append_row(client, "prompt_improvement_suggestions", {
        "suggestion_id": f"sug_threads_{result_id}",
        "account_id": account_id,
        "created_at": created_at,
        "source": "process_threads_queue",
        "suggestion_type": "metrics_followup",
        "target_template": "",
        "current_behavior": "Threads post created; metrics not imported yet.",
        "suggested_change": "Import Threads metrics manually before changing prompts.",
        "reason": f"result_id={result_id}",
        "expected_impact": "Enable human-reviewed PDCA loop.",
        "priority": "medium",
        "status": "WAITING_REVIEW",
        "reviewed_by": "",
        "reviewed_at": "",
        "notes": "auto_apply=false; do not activate learning rule automatically.",
    })


def save_posted_result(
    client: SheetsClient,
    *,
    queue_row: dict[str, Any],
    social: dict[str, Any] | None,
    text: str,
    external_post_id: str,
    post_url: str,
    media_used: str = "false",
    media_asset_id: str = "",
    media_url: str = "",
    media_status: str = "",
    validator_status: str = "",
) -> str:
    result_id = f"threads_{queue_row.get('queue_id')}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    permalink_note = " permalink_pending=true" if not post_url else ""
    append_row(client, "posted_results", {
        "result_id": result_id,
        "queue_id": queue_row.get("queue_id", ""),
        "draft_id": queue_row.get("draft_id", ""),
        "derivative_id": social.get("derivative_id", "") if social else "",
        "account_id": queue_row.get("account_id", ""),
        "platform": "threads",
        "external_post_id": external_post_id,
        "post_url": post_url,
        "posted_text": text,
        "posted_at": now_iso(),
        "status": "POSTED",
        "metrics_status": "PENDING",
        "real_post": "true",
        "media_used": media_used,
        "media_asset_id": media_asset_id,
        "media_url": media_url,
        "media_status": media_status,
        "source_id": queue_row.get("source_id", ""),
        "source_url": queue_row.get("source_url", ""),
        "source_post_id": queue_row.get("source_post_id", ""),
        "source_video_id": queue_row.get("source_video_id", ""),
        "clip_candidate_id": queue_row.get("clip_candidate_id", ""),
        "generation_mode": queue_row.get("generation_mode", ""),
        "content_route": (
            queue_row.get("content_route", "")
            or queue_row.get("content_type", "")
            or queue_row.get("generation_mode", "")
        ),
        "source_content_route": queue_row.get("source_content_route", ""),
        "source_generation_mode": queue_row.get("source_generation_mode", ""),
        "source_result_id": queue_row.get("source_result_id", ""),
        "validator_status": validator_status,
        "caption_provider": queue_row.get("caption_provider", ""),
        "caption_provider_version": queue_row.get("caption_provider_version", ""),
        "alignment_status": queue_row.get("alignment_status", ""),
        "final_alignment_score": queue_row.get("final_alignment_score", ""),
        "main_claim_coverage": queue_row.get("main_claim_coverage", ""),
        "unsupported_claim_count": queue_row.get("unsupported_claim_count", ""),
        "source_copy_similarity": queue_row.get("source_copy_similarity", ""),
        "recent_post_similarity": queue_row.get("recent_post_similarity", ""),
        "source_content_hash": queue_row.get("content_hash", ""),
        "verification_status": "PENDING",
        "verification_checked_at": "",
        # Preserve generation features for measured attribution.
        "canary_id": queue_row.get("canary_id", ""),
        "batch_id": queue_row.get("batch_id", ""),
        "content_type": queue_row.get("content_type", ""),
        "feature_schema_version": queue_row.get("feature_schema_version", ""),
        "primary_topic": queue_row.get("primary_topic", ""),
        "supporting_topics": queue_row.get("supporting_topics", ""),
        "structure_variant": queue_row.get("structure_variant", ""),
        "hook_text": queue_row.get("hook_text", ""),
        "body_text": queue_row.get("body_text", ""),
        "closing_text": queue_row.get("closing_text", ""),
        "cta_intent": queue_row.get("cta_intent", ""),
        "key_claims_json": queue_row.get("key_claims_json", ""),
        "post_design_json": queue_row.get("post_design_json", ""),
        "visual_plan_json": queue_row.get("visual_plan_json", ""),
        "generation_policy_json": queue_row.get("generation_policy_json", ""),
        "quality_gate_version": queue_row.get("quality_gate_version", ""),
        "batch_diversity_status": queue_row.get("batch_diversity_status", ""),
        "topic_coherence_status": queue_row.get("topic_coherence_status", ""),
        "topic_confidence": queue_row.get("topic_confidence", ""),
        "hook_topic_match": queue_row.get("hook_topic_match", ""),
        "closing_topic_match": queue_row.get("closing_topic_match", ""),
        "shared_hook_detected": queue_row.get("shared_hook_detected", ""),
        "shared_closing_detected": queue_row.get("shared_closing_detected", ""),
        "media_primary_topic": queue_row.get("media_primary_topic", ""),
        "visual_topic": queue_row.get("visual_topic", ""),
        "visual_topic_match": queue_row.get("visual_topic_match", ""),
        "visual_cta_match": queue_row.get("visual_cta_match", ""),
        "visual_plan_version": queue_row.get("visual_plan_version", ""),
        "visual_text_hash": queue_row.get("visual_text_hash", ""),
        "publisher_media_type": queue_row.get("publisher_media_type", ""),
        "media_type": queue_row.get("media_type", ""),
        "source_queue_status": queue_row.get("status", ""),
        "save_source": "process_threads_queue",
        "created_by": "process_threads_queue",
        "measurement_window": "pending",
        # Unknown metrics stay blank. Confirmed zero is written only by a collector.
        "views": "",
        "likes": "",
        "comments": "",
        "follows": "",
        "profile_clicks": "",
        "line_adds": "",
        "manual_memo": f"Created by process_threads_queue. Metrics pending.{permalink_note}",
        "collected_at": now_iso(),
    })
    return result_id


def schedule_metrics_after_post(client: SheetsClient, result_id: str) -> int:
    """Persist 24h/72h/7d collection jobs after a verified Threads result.

    The call is deliberately after read-after-write verification: an ambiguous
    publisher outcome must never create a second observation lifecycle.
    """
    posted = records(client, "posted_results")
    existing = records(client, "metrics_collection_jobs")
    jobs = [job for job in build_metric_collection_jobs(posted, existing) if job["result_id"] == result_id]
    for job in jobs:
        append_row(client, "metrics_collection_jobs", job)
    return len(jobs)


def write_fallback(queue_row: dict[str, Any], social: dict[str, Any] | None = None, text: str = "", result: Any = None, *, dry_run: bool = False) -> Path | None:
    if dry_run:
        return None
    fallback_dir = FALLBACK_DIR
    fallback_dir.mkdir(parents=True, exist_ok=True)
    path = fallback_dir / f"{queue_row.get('queue_id', 'unknown')}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.json"
    payload = {
        "created_at": now_iso(),
        "queue": queue_row,
        "social": social or {},
        "posted_text": text,
        "external_post_id": getattr(result, "external_post_id", "") or "",
        "posted_url": getattr(result, "posted_url", "") or "",
        "message": getattr(result, "message", "") or "",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return path



def build_media_validation_plan(
    queue_row: dict[str, Any],
    account_id: str,
    media: dict[str, Any],
    text: str,
) -> dict[str, Any]:
    direct_reference = (
        str(
            queue_row.get(
                "generation_mode",
                "",
            )
        )
        == "direct_reference_media"
    )

    return {
        "rights_status": queue_row.get(
            "rights_status",
            "",
        ),
        "permission_status": queue_row.get(
            "permission_status",
            "",
        ),
        "media_url": media[
            "effective_media_url"
        ],
        "media_asset_id": media[
            "media_asset_id"
        ],
        "platform": "threads",
        "account_id": account_id,
        "media_type": media[
            "media_type"
        ],
        "content_type": queue_row.get(
            "content_type",
            "",
        ),
        "publisher_media_type": (
            queue_row.get(
                "publisher_media_type",
                "",
            )
        ),
        "media_urls": media[
            "effective_media_urls"
        ],
        "duration_seconds": queue_row.get(
            "duration_seconds",
            "0",
        ),
        "aspect_ratio": queue_row.get(
            "aspect_ratio",
            "",
        ),
        "width": queue_row.get(
            "width",
            "",
        ),
        "height": queue_row.get(
            "height",
            "",
        ),
        "video_stream_count": (
            queue_row.get(
                "video_stream_count",
                0,
            )
        ),
        "audio_stream_count": (
            queue_row.get(
                "audio_stream_count",
                0,
            )
        ),
        "media_probe_status": (
            queue_row.get(
                "media_probe_status",
                "",
            )
        ),
        "enforce_video_stream_evidence": (
            queue_row.get(
                "enforce_video_stream_evidence",
                "false",
            )
        ),
        "public_post_text": text,
        "media_origin": (
            "direct_reference"
            if direct_reference
            else "approved_source_clip"
        ),
        "caption_mode": queue_caption_mode(
            queue_row,
            direct_reference=direct_reference,
        ),
        "alignment_status": queue_row.get(
            "alignment_status",
            "",
        ),
        "final_alignment_score": (
            queue_row.get(
                "final_alignment_score",
                "",
            )
        ),
        "main_claim_coverage": (
            queue_row.get(
                "main_claim_coverage",
                "",
            )
        ),
        "unsupported_claim_count": (
            queue_row.get(
                "unsupported_claim_count",
                "",
            )
        ),
        "source_copy_similarity": (
            queue_row.get(
                "source_copy_similarity",
                "",
            )
        ),
        "recent_post_similarity": (
            queue_row.get(
                "recent_post_similarity",
                "",
            )
        ),
    }


def process_one(client: SheetsClient, queue_row: dict[str, Any], *, dry_run: bool, confirm_real_post: bool) -> dict[str, Any]:
    account_id = str(queue_row.get("account_id", ""))
    queue_id = str(queue_row.get("queue_id", ""))

    social_rows = records(client, "social_derivatives")
    draft_rows = records(client, "drafts")
    posted_rows = records(client, "posted_results")
    social = find_social_for_queue(client, queue_row, social_rows)
    draft = find_draft_for_queue(queue_row, row_by_key(draft_rows, "draft_id"))
    text = text_for_queue(queue_row, social, draft)

    if account_id == BEAUTY_ACCOUNT:
        allowed, reason = beauty_publish_gate(dry_run=dry_run)
        if not allowed:
            return {"status": "BLOCKED", "reason": reason, "queue_id": queue_id}
        if str(queue_row.get("review_lane", "BEAUTY_STANDARD")).upper() == "BEAUTY_MEDICAL":
            return {"status": "BLOCKED", "reason": "beauty_medical_requires_human_review", "queue_id": queue_id}
    if str(queue_row.get("platform", "")).lower() != "threads":
        return {"status": "SKIPPED", "reason": "non-threads row ignored", "queue_id": queue_id}
    if not text:
        if not dry_run:
            update_row(client, "queue", "queue_id", queue_id, {"status": "FAILED", "error": "EMPTY_TEXT", "processed_at": now_iso()})
            log_event(client, account_id, "FAILED", "Queue text is empty", {"queue_id": queue_id})
        return {"status": "FAILED", "reason": "EMPTY_TEXT", "queue_id": queue_id}

    if requires_hybrid_ai_gate(queue_row):
        gate_ok, gate_reason = hybrid_ai_gate_passed(
            queue_row,
            build_source_context(client, queue_row),
        )
        if not gate_ok:
            status = "DRY_RUN_BLOCKED" if dry_run else "SAFETY_STOP_HYBRID_AI_GATE"
            reason = f"HYBRID_AI_GATE_BLOCKED:{gate_reason}"
            if not dry_run:
                update_row(client, "queue", "queue_id", queue_id, {
                    "status": status,
                    "error": reason,
                    "processed_at": now_iso(),
                })
                log_event(client, account_id, status, reason, {"queue_id": queue_id})
            return {"status": status, "reason": reason, "queue_id": queue_id}

    direct_reference = (
        str(
            queue_row.get(
                "generation_mode",
                "",
            )
        )
        == "direct_reference_media"
    )
    caption_mode = queue_caption_mode(
        queue_row,
        direct_reference=direct_reference,
    )
    public_validation = (
        validate_source_preserving_public_post(text, account_id)
        if direct_reference and caption_mode == "source_copyedit"
        else final_public_post_validator(text, account_id)
    )

    if public_validation["status"] != "PASS":
        reason = "FINAL_PUBLIC_POST_VALIDATOR_BLOCKED:" + ",".join(public_validation["blocked_reasons"])
        if not dry_run:
            update_row(client, "queue", "queue_id", queue_id, {
                "status": "BLOCKED_INTERNAL_LEAK",
                "error": reason,
                "processed_at": now_iso(),
            })
            log_event(client, account_id, "BLOCKED_INTERNAL_LEAK", reason, {
                "queue_id": queue_id,
                "internal_hits": public_validation["internal_leak_check"]["hits"],
                "preview": public_preview(text),
            })
        return {
            "status": "BLOCKED_INTERNAL_LEAK",
            "reason": reason,
            "queue_id": queue_id,
            "account_id": account_id,
            "internal_leak_check": public_validation["internal_leak_check"]["status"],
            "account_fit_check": public_validation["account_fit_check"]["status"],
            "voice_persona_status": public_validation.get("voice_persona_check", {}).get("status", "BLOCKED"),
            "voice_persona_score": public_validation.get("voice_persona_check", {}).get("score", 0),
            "final_public_post_validator": "BLOCKED",
            "public_post_preview": public_preview(text),
        }

    media = resolve_queue_media(queue_row)

    # media_required=true なのに使える media_url が無い場合は投稿しない（dry-run でもブロック）。
    if media["block_reason"]:
        if not dry_run:
            log_event(client, account_id, "DRY_RUN_BLOCKED", media["block_reason"], {"queue_id": queue_id, "media_asset_id": media["media_asset_id"]})
        return {
            "status": "DRY_RUN_BLOCKED",
            "reason": media["block_reason"],
            "queue_id": queue_id,
            "media_asset_id": media["media_asset_id"],
            "media_status": media["media_status"],
        }


    direct_media_validation: dict[str, Any] | None = None

    if (
        direct_reference
        and media["effective_media_url"]
    ):
        direct_media_validation = (
            validate_media_post(
                build_media_validation_plan(
                    queue_row,
                    account_id,
                    media,
                    text,
                )
            )
        )

        if (
            direct_media_validation[
                "status"
            ]
            != "PASS"
        ):
            status = (
                "DRY_RUN_BLOCKED"
                if dry_run
                else "SAFETY_STOP_MEDIA_VALIDATOR"
            )

            if not dry_run:
                log_event(
                    client,
                    account_id,
                    status,
                    "direct-reference media validator blocked post",
                    {
                        "queue_id": queue_id,
                        "blocked_reasons": (
                            direct_media_validation[
                                "blocked_reasons"
                            ]
                        ),
                    },
                )

            return {
                "status": status,
                "reason": ",".join(
                    direct_media_validation[
                        "blocked_reasons"
                    ]
                ),
                "queue_id": queue_id,
                "media_asset_id": media[
                    "media_asset_id"
                ],
                "media_status": media[
                    "media_status"
                ],
                "media_planned": bool(
                    media[
                        "effective_media_url"
                    ]
                ),
                "final_public_post_validator": (
                    public_validation[
                        "status"
                    ]
                ),
            }

    duplicate = duplicate_reason(
        queue_row=queue_row,
        social=social,
        text=text,
        posted_rows=posted_rows,
        media_asset_id=media["media_asset_id"],
    )
    if duplicate:
        if not dry_run:
            update_row(client, "queue", "queue_id", queue_id, {
                "status": "DUPLICATE_BLOCKED",
                "error": duplicate,
                "processed_at": now_iso(),
            })
            log_event(client, account_id, "DUPLICATE_BLOCKED", duplicate, {"queue_id": queue_id})
        return {"status": "DUPLICATE_BLOCKED", "reason": duplicate, "queue_id": queue_id}

    publisher = ThreadsPublisher()
    dry_result = publisher.publish(
        text,
        account={"account_id": account_id},
        derivative={"derivative_id": social.get("derivative_id", "") if social else "", "platform": "threads"},
        queue_item={"queue_id": queue_id, "platform": "threads"},
        dry_run=True,
        media_url=media["effective_media_url"] or None,
        media_type=publisher_media_type(str(queue_row.get("content_type", "")), media["effective_media_urls"]) or ("IMAGE" if media["media_type"] == "image" else "VIDEO"),
        media_urls=media["effective_media_urls"],
        media_types=["IMAGE" if item == "image" else "VIDEO" for item in media["media_types"]],
    )
    if not dry_result.success:
        if not dry_run:
            update_row(client, "queue", "queue_id", queue_id, {"status": "FAILED", "error": dry_result.message, "processed_at": now_iso()})
            log_event(client, account_id, "FAILED", "Dry-run validation failed", {"queue_id": queue_id, "message": dry_result.message})
        return {"status": "FAILED", "reason": dry_result.message, "queue_id": queue_id}

    if dry_run:
        return {
            "status": "DRY_RUN",
            "read_only": True,
            "queue_id": queue_id,
            "account_id": account_id,
            "draft_id": queue_row.get("draft_id", ""),
            "derivative_id": social.get("derivative_id", "") if social else "",
            "text_length": len(text),
            "public_post_preview": public_preview(text),
            "internal_leak_check": public_validation["internal_leak_check"]["status"],
            "account_fit_check": public_validation["account_fit_check"]["status"],
            "voice_persona_status": public_validation.get("voice_persona_check", {}).get("status", "BLOCKED"),
            "voice_persona_score": public_validation.get("voice_persona_check", {}).get("score", 0),
            "final_public_post_validator": public_validation["status"],
            "media_asset_id": media["media_asset_id"],
            "media_status": media["media_status"],
            "media_required": media["media_required"],
            "media_planned": bool(media["effective_media_url"]),
            "message": dry_result.message,
        }

    # media 付き実投稿は追加gateとmedia validatorが必須。既定ではOFF。
    if media["effective_media_url"]:
        allow_media = is_true(os.environ.get("ALLOW_MEDIA_POSTS", "false"))
        allow_video_post = is_true(os.environ.get("ALLOW_REAL_THREADS_VIDEO_POST", "false"))
        if not allow_media or (media["media_type"] == "video" and not allow_video_post):
            log_event(client, account_id, "SAFETY_STOP_MEDIA_GATE", "media付き投稿には ALLOW_MEDIA_POSTS=true と ALLOW_REAL_THREADS_VIDEO_POST=true が必要", {"queue_id": queue_id, "media_asset_id": media["media_asset_id"]})
            return {
                "status": "SAFETY_STOP_MEDIA_GATE",
                "reason": "ALLOW_MEDIA_POSTS=true and ALLOW_REAL_THREADS_VIDEO_POST=true are required",
                "queue_id": queue_id,
                "media_asset_id": media["media_asset_id"],
            }
        media_validation = (
            direct_media_validation
            if direct_media_validation is not None
            else validate_media_post(
                build_media_validation_plan(
                    queue_row,
                    account_id,
                    media,
                    text,
                )
            )
        )
        if media_validation["status"] != "PASS":
            log_event(client, account_id, "SAFETY_STOP_MEDIA_VALIDATOR", "media validator blocked post", {"queue_id": queue_id, "blocked_reasons": media_validation["blocked_reasons"]})
            return {
                "status": "SAFETY_STOP_MEDIA_VALIDATOR",
                "reason": ",".join(media_validation["blocked_reasons"]),
                "queue_id": queue_id,
                "media_asset_id": media["media_asset_id"],
            }

    if not confirm_real_post:
        return {"status": "BLOCKED", "reason": "--confirm-real-post required", "queue_id": queue_id}
    if not is_true(os.environ.get("PUBLISH_ENABLED", "false")) or not is_true(os.environ.get("ALLOW_REAL_THREADS_POST", "false")):
        return {"status": "BLOCKED", "reason": "PUBLISH_ENABLED=true and ALLOW_REAL_THREADS_POST=true are required", "queue_id": queue_id}

    update_row(client, "queue", "queue_id", queue_id, {"status": "PROCESSING", "error": "", "processed_at": ""})
    log_event(client, account_id, "PROCESSING", "Threads queue row locked for processing", {"queue_id": queue_id})

    result = publisher.publish(
        text,
        account={"account_id": account_id},
        derivative={"derivative_id": social.get("derivative_id", "") if social else "", "platform": "threads"},
        queue_item={"queue_id": queue_id, "platform": "threads"},
        dry_run=False,
        media_url=media["effective_media_url"] or None,
        media_type=publisher_media_type(str(queue_row.get("content_type", "")), media["effective_media_urls"]) or ("IMAGE" if media["media_type"] == "image" else "VIDEO"),
        media_urls=media["effective_media_urls"],
        media_types=["IMAGE" if item == "image" else "VIDEO" for item in media["media_types"]],
    )
    if not result.success:
        if result.delivery_state == "CONTAINER_CREATED_PUBLISH_UNVERIFIED":
            update_row(client, "queue", "queue_id", queue_id, {
                "status": "PUBLISH_OUTCOME_UNVERIFIED",
                "error": "CONTAINER_CREATED_PUBLISH_UNVERIFIED",
                "processed_at": now_iso(),
            })
            log_event(client, account_id, "PUBLISH_OUTCOME_UNVERIFIED", "Container exists; do not retry before manual outcome verification", {"queue_id": queue_id, "container_created": True})
            return {"status": "PUBLISH_OUTCOME_UNVERIFIED", "reason": "MANUAL_OUTCOME_VERIFICATION_REQUIRED", "queue_id": queue_id}
        update_row(client, "queue", "queue_id", queue_id, {
            "status": "FAILED",
            "error": f"THREADS_API_FAILED: {result.message}",
            "processed_at": now_iso(),
        })
        log_event(client, account_id, "FAILED", "Threads post failed; no immediate retry", {"queue_id": queue_id, "message": result.message})
        return {"status": "FAILED", "reason": result.message, "queue_id": queue_id}

    try:
        result_id = save_posted_result(
            client,
            queue_row=queue_row,
            social=social,
            text=text,
            external_post_id=result.external_post_id or "",
            post_url=result.posted_url or "",
            media_used="true" if media["effective_media_url"] else "false",
            media_asset_id=media["media_asset_id"],
            media_url=media["effective_media_url"] or "",
            media_status=media["media_status"],
            validator_status=public_validation["status"],
        )
        persistence = verify_posted_result_persistence(
            records(client, "posted_results"),
            result_id=result_id,
            queue_id=queue_id,
            account_id=account_id,
            external_post_id=result.external_post_id or "",
        )
        if persistence["status"] != "PASS":
            fallback = write_fallback(queue_row, social, text, result)
            update_row(client, "queue", "queue_id", queue_id, {
                "status": "POSTED_SAVE_UNVERIFIED",
                "error": persistence["reason"],
                "processed_at": now_iso(),
            })
            log_event(client, account_id, "POSTED_SAVE_UNVERIFIED", "Posted result needs manual read-after-write recovery", {
                "queue_id": queue_id,
                "persistence_reason": persistence["reason"],
                "retry_disposition": retry_disposition(publish_succeeded=True, persisted=False, api_outcome_known=True),
            })
            return {"status": "POSTED_SAVE_UNVERIFIED", "queue_id": queue_id, "fallback": str(fallback), "reason": persistence["reason"]}

        verification_checked_at = now_iso()
        verification_saved = update_row(
            client,
            "posted_results",
            "result_id",
            result_id,
            {
                "verification_status": "READ_AFTER_WRITE_PASS",
                "verification_checked_at": verification_checked_at,
            },
        )

        verified_result = next(
            (
                row
                for row in records(client, "posted_results")
                if str(row.get("result_id", "")) == result_id
            ),
            {},
        )

        if (
            not verification_saved
            or str(
                verified_result.get("verification_status", "")
            ).upper() != "READ_AFTER_WRITE_PASS"
        ):
            fallback = write_fallback(queue_row, social, text, result)
            update_row(client, "queue", "queue_id", queue_id, {
                "status": "POSTED_SAVE_UNVERIFIED",
                "error": "READ_AFTER_WRITE_STATUS_NOT_PERSISTED",
                "processed_at": now_iso(),
            })
            log_event(
                client,
                account_id,
                "POSTED_SAVE_UNVERIFIED",
                "Posted result verification status was not persisted",
                {
                    "queue_id": queue_id,
                    "result_id": result_id,
                    "retry_disposition": retry_disposition(
                        publish_succeeded=True,
                        persisted=True,
                        api_outcome_known=True,
                    ),
                },
            )
            return {
                "status": "POSTED_SAVE_UNVERIFIED",
                "queue_id": queue_id,
                "fallback": str(fallback),
                "reason": "READ_AFTER_WRITE_STATUS_NOT_PERSISTED",
            }

        update_row(client, "queue", "queue_id", queue_id, {
            "status": "POSTED",
            "error": "",
            "processed_at": now_iso(),
            "posted_at": now_iso(),
            "post_url": result.posted_url or "",
            "result_id": result_id,
        })
    except Exception as exc:
        fallback = write_fallback(queue_row, social, text, result)
        try:
            update_row(client, "queue", "queue_id", queue_id, {
                "status": "POSTED_SAVE_FAILED",
                "error": f"posted_results save failed; fallback={fallback}",
                "processed_at": now_iso(),
            })
            log_event(client, account_id, "POSTED_SAVE_FAILED", "Posted but failed to save posted_results", {"queue_id": queue_id, "fallback": str(fallback), "error": str(exc)})
        except Exception:
            pass
        return {"status": "POSTED_SAVE_FAILED", "queue_id": queue_id, "fallback": str(fallback)}

    slot_warning = ""
    slot_id = str(queue_row.get("slot_id", "")).strip()
    if slot_id:
        try:
            from content_slot_runs import build_slot_run, upsert_slot_run
            slot_row = build_slot_run(
                account_id,
                slot_id,
                status="POSTED_PRIMARY",
                actual_post_type=str(queue_row.get("content_type") or queue_row.get("generation_mode") or "threads"),
                fallback_level=0,
                queue_id=queue_id,
                result_id=result_id,
                post_url=result.posted_url or "",
                media_asset_id=media["media_asset_id"],
                source_post_id=str(queue_row.get("source_post_id", "")),
                source_video_id=str(queue_row.get("source_video_id", "")),
                actual_generation_mode=str(queue_row.get("generation_mode", "")),
                actual_posted_at=now_iso(),
            )
            upsert_slot_run(client, slot_row)
            clip_candidate_id = str(queue_row.get("clip_candidate_id") or queue_row.get("video_clip_id") or "").strip()
            if clip_candidate_id and hasattr(client, "update_video_clip_candidate"):
                client.update_video_clip_candidate(
                    clip_candidate_id,
                    post_status="POSTED",
                    reviewer_status="AUTO_APPROVED",
                    clip_status="POSTED",
                )
        except Exception as exc:
            slot_warning = f"content_slot_finalize_failed:{type(exc).__name__}"

    pdca_warning = ""
    metrics_job_count = 0
    try:
        metrics_job_count = schedule_metrics_after_post(client, result_id)
        save_pdca_initial(client, queue_row, result_id)
        log_event(client, account_id, "POSTED", "Threads post saved to posted_results", {"queue_id": queue_id, "result_id": result_id})
    except Exception as exc:
        pdca_warning = f"pdca_or_log_save_failed:{type(exc).__name__}"

    return {
        "status": "POSTED",
        "queue_id": queue_id,
        "result_id": result_id,
        "external_post_id": result.external_post_id or "",
        "delivery_idempotency_key": delivery_idempotency_key(
            account_id=account_id,
            platform="threads",
            queue_id=queue_id,
            external_post_id=result.external_post_id or "",
        ),
        "post_url": result.posted_url or "",
        "metrics_collection_job_count": metrics_job_count,
        "warning": ",".join(item for item in (pdca_warning, slot_warning) if item),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Process Threads queue rows safely")
    parser.add_argument("--account-id", choices=["night_scout", "liver_manager", "beauty_account"], help="Target account")
    parser.add_argument("--dry-run", action="store_true", help="Validate only; no post or Sheets mutation")
    parser.add_argument("--confirm-real-post", action="store_true", help="Required for real post")
    parser.add_argument("--max-posts", type=int, default=1, help="Max posts to process. Default 1")
    parser.add_argument("--queue-id", action="append", default=[], help="Process only this approved queue ID; repeatable")
    args = parser.parse_args()

    if args.account_id == BEAUTY_ACCOUNT:
        allowed, reason = beauty_publish_gate(dry_run=args.dry_run)
        if not allowed:
            print(f"[BLOCKED] {reason}")
            return 1
    if args.max_posts < 1:
        print("[ERROR] --max-posts must be >= 1")
        return 1
    if args.max_posts > 1 and not args.confirm_real_post and not args.dry_run:
        print("[BLOCKED] real multi-post requires --confirm-real-post")
        return 1
    if args.max_posts > 2 and not args.queue_id:
        print("[BLOCKED] --max-posts is capped at 2")
        return 1
    if not args.dry_run and not args.confirm_real_post:
        print("[BLOCKED] real post mode requires --confirm-real-post")
        return 1

    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    if args.dry_run:
        print("[READ_ONLY] --dry-run: setup_all/update/append/post/fallback are disabled")
    else:
        # setup_all はタブ初期化に多くの API 呼び出しを行うため、本番運用では呼ばない。
        # タブは recover_production_sheets_threads_first.py で既に初期化済みであること。
        print("[REAL_POST] setup_all をスキップします（本番タブは初期化済みを前提）")

    requested_queue_ids = {item.strip() for item in args.queue_id if item.strip()}
    if requested_queue_ids and args.max_posts != len(requested_queue_ids):
        args.max_posts = len(requested_queue_ids)
    candidates = select_candidates(client, args.account_id, args.max_posts, requested_queue_ids or None)
    if requested_queue_ids and {str(row.get("queue_id", "")) for row in candidates} != requested_queue_ids:
        missing = sorted(requested_queue_ids - {str(row.get("queue_id", "")) for row in candidates})
        print(json.dumps({"status": "NO_POST", "reason": "REQUESTED_QUEUE_NOT_READY", "missing_queue_ids": missing}, ensure_ascii=False))
        return 1
    print(f"[process_threads_queue] candidates={len(candidates)} dry_run={args.dry_run} max_posts={args.max_posts}")
    if not candidates:
        print("[DONE] no eligible Threads queue rows")
        print(json.dumps({
            "status": "NO_POST",
            "reason": "NO_READY_QUEUE",
            "account_id": args.account_id or "all",
            "eligible_statuses": sorted(ELIGIBLE_STATUSES),
            "dry_run": args.dry_run,
        }, ensure_ascii=False))
        return 0

    results = []
    for queue_row in candidates:
        outcome = process_one(client, queue_row, dry_run=args.dry_run, confirm_real_post=args.confirm_real_post)
        results.append(outcome)
        print(json.dumps(outcome, ensure_ascii=False))

    bad = [r for r in results if r["status"] in {"FAILED", "POSTED_SAVE_FAILED"}]
    blocked = [r for r in results if r["status"] in {"BLOCKED"}]
    return 1 if bad or blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
