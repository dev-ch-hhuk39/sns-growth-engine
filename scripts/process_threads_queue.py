#!/usr/bin/env python3
"""Process one or more Threads queue rows safely.

Default mode is dry-run. Real posting requires all of:
- --confirm-real-post
- PUBLISH_ENABLED=true
- ALLOW_REAL_THREADS_POST=true

This worker never posts X, never posts beauty_account, and never retries
immediately after a failure.
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
from media_post_validator import validate_media_post  # noqa: E402
from publishers.threads_publisher import ThreadsPublisher  # noqa: E402
from public_post_quality import extract_public_post_text, final_public_post_validator, public_preview  # noqa: E402
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
    "DUPLICATE_BLOCKED",
}
BEAUTY_BLOCKED = {"beauty_account"}

# media_status がこれらのときだけ「投稿に使える media」とみなす
MEDIA_OK_STATUSES = {"ATTACHED", "UPLOADED"}

# Sheets ヘッダー行のキャッシュ（ws オブジェクトの id をキーにする）
_headers_cache: dict[int, list[str]] = {}

FALLBACK_DIR = ROOT / "output" / "posted_results_fallback"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_true(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def get_ws(client: SheetsClient, logical: str):
    return client._ws(logical)


def records(client: SheetsClient, logical: str) -> list[dict[str, Any]]:
    return [dict(r) for r in get_ws(client, logical).get_all_records()]


def row_by_key(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {str(r.get(key, "")): r for r in rows if str(r.get(key, ""))}


def _get_headers(ws) -> list[str]:
    """ヘッダー行を取得する。セッション内でキャッシュし、429 発生時は指数バックオフでリトライする。"""
    ws_id = id(ws)
    if ws_id in _headers_cache:
        return _headers_cache[ws_id]
    delays = [0, 5, 15, 30]
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
    delays = [0, 5, 15, 30]
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
        raise KeyError(f"{logical}: missing key header {key}")
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
            and str(posted.get("media_asset_id", "")).strip() == media_asset_id
            and text.strip()
        )
        if same_text:
            return "same text/account/platform/media already POSTED"
    return ""


def select_candidates(client: SheetsClient, account_id: str | None, max_posts: int) -> list[dict[str, Any]]:
    rows = records(client, "queue")
    candidates: list[dict[str, Any]] = []
    for row in rows:
        row_account = str(row.get("account_id", ""))
        status = str(row.get("status", "")).upper()
        platform = str(row.get("platform", "")).lower()
        if row_account in BEAUTY_BLOCKED:
            continue
        if account_id and row_account != account_id:
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
        "validator_status": validator_status,
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


def process_one(client: SheetsClient, queue_row: dict[str, Any], *, dry_run: bool, confirm_real_post: bool) -> dict[str, Any]:
    account_id = str(queue_row.get("account_id", ""))
    queue_id = str(queue_row.get("queue_id", ""))

    social_rows = records(client, "social_derivatives")
    draft_rows = records(client, "drafts")
    posted_rows = records(client, "posted_results")
    social = find_social_for_queue(client, queue_row, social_rows)
    draft = find_draft_for_queue(queue_row, row_by_key(draft_rows, "draft_id"))
    text = text_for_queue(queue_row, social, draft)

    if account_id in BEAUTY_BLOCKED:
        return {"status": "BLOCKED", "reason": "beauty_account is blocked", "queue_id": queue_id}
    if str(queue_row.get("platform", "")).lower() != "threads":
        return {"status": "SKIPPED", "reason": "non-threads row ignored", "queue_id": queue_id}
    if not text:
        if not dry_run:
            update_row(client, "queue", "queue_id", queue_id, {"status": "FAILED", "error": "EMPTY_TEXT", "processed_at": now_iso()})
            log_event(client, account_id, "FAILED", "Queue text is empty", {"queue_id": queue_id})
        return {"status": "FAILED", "reason": "EMPTY_TEXT", "queue_id": queue_id}

    public_validation = final_public_post_validator(text, account_id)
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
        media_type="IMAGE" if media["media_type"] == "image" else "VIDEO",
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
        media_validation = validate_media_post({
            "rights_status": queue_row.get("rights_status", ""),
            "permission_status": queue_row.get("permission_status", ""),
            "media_url": media["effective_media_url"],
            "media_asset_id": media["media_asset_id"],
            "platform": "threads",
            "account_id": account_id,
            "media_type": media["media_type"],
            "duration_seconds": queue_row.get("duration_seconds", "0"),
            "aspect_ratio": queue_row.get("aspect_ratio", ""),
            "public_post_text": text,
            "media_origin": "direct_reference" if str(queue_row.get("generation_mode", "")) == "direct_reference_media" else "generated_clip",
        })
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
        media_type="IMAGE" if media["media_type"] == "image" else "VIDEO",
        media_urls=media["effective_media_urls"],
        media_types=["IMAGE" if item == "image" else "VIDEO" for item in media["media_types"]],
    )
    if not result.success:
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

    pdca_warning = ""
    try:
        save_pdca_initial(client, queue_row, result_id)
        log_event(client, account_id, "POSTED", "Threads post saved to posted_results", {"queue_id": queue_id, "result_id": result_id})
    except Exception as exc:
        pdca_warning = f"pdca_or_log_save_failed:{type(exc).__name__}"

    return {
        "status": "POSTED",
        "queue_id": queue_id,
        "result_id": result_id,
        "external_post_id": result.external_post_id or "",
        "post_url": result.posted_url or "",
        "warning": pdca_warning,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Process Threads queue rows safely")
    parser.add_argument("--account-id", choices=["night_scout", "liver_manager", "beauty_account"], help="Target account")
    parser.add_argument("--dry-run", action="store_true", help="Validate only; no post or Sheets mutation")
    parser.add_argument("--confirm-real-post", action="store_true", help="Required for real post")
    parser.add_argument("--max-posts", type=int, default=1, help="Max posts to process. Default 1")
    args = parser.parse_args()

    if args.account_id == "beauty_account":
        print("[BLOCKED] beauty_account is draft_only and cannot be posted")
        return 1
    if args.max_posts < 1:
        print("[ERROR] --max-posts must be >= 1")
        return 1
    if args.max_posts > 1 and not args.confirm_real_post and not args.dry_run:
        print("[BLOCKED] real multi-post requires --confirm-real-post")
        return 1
    if args.max_posts > 2:
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

    candidates = select_candidates(client, args.account_id, args.max_posts)
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
