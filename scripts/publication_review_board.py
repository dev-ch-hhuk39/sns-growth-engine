"""Pure helpers for the human-facing Sheets publication review board."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

ACTIVE_QUEUE_STATUSES = {"WAITING_REVIEW", "READY"}
ALLOWED_ACCOUNTS = {"night_scout", "liver_manager"}
MEDIA_TYPES = {"IMAGE", "VIDEO", "CAROUSEL"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def text(value: Any) -> str:
    return str(value or "").strip()


def truthy(value: Any) -> bool:
    return text(value).lower() in {"1", "true", "yes"}


def post_type(queue: Mapping[str, Any]) -> str:
    explicit = text(queue.get("content_type") or queue.get("publisher_media_type"))
    if explicit:
        return explicit.lower()
    media_type = text(queue.get("media_type")).upper()
    if media_type in MEDIA_TYPES:
        return f"direct_{media_type.lower()}"
    if text(queue.get("clip_candidate_id")):
        return "generated_clip"
    return "text"


def is_reviewable(queue: Mapping[str, Any]) -> bool:
    return (
        text(queue.get("account_id")) in ALLOWED_ACCOUNTS
        and text(queue.get("platform")).lower() == "threads"
        and text(queue.get("status")).upper() in ACTIVE_QUEUE_STATUSES
        and not truthy(queue.get("excluded_from_activation"))
        and bool(text(queue.get("public_post_text")))
    )


def review_row(queue: Mapping[str, Any], existing: Mapping[str, Any] | None = None) -> dict[str, str]:
    """Mirror operational queue data while retaining user-editable review cells."""
    existing = existing or {}
    queue_id = text(queue.get("queue_id"))
    media_url = text(queue.get("media_url"))
    return {
        "review_id": text(existing.get("review_id")) or f"review_{queue_id}",
        "queue_id": queue_id,
        "account_id": text(queue.get("account_id")),
        "platform": "threads",
        "post_type": post_type(queue),
        "queue_status": text(queue.get("status")).upper(),
        "review_status": (
            "APPROVED_PENDING_MEDIA_GATE"
            if text(existing.get("decision_result")) == "APPROVED_PENDING_MEDIA_GATE"
            else "PENDING_REVIEW"
        ),
        "public_post_text": text(queue.get("public_post_text")),
        "media_asset_id": text(queue.get("media_asset_id")),
        "media_preview_url": media_url,
        "media_type": text(queue.get("publisher_media_type") or queue.get("media_type")).upper(),
        "source_url": text(queue.get("source_url") or queue.get("source_video_url")),
        "primary_topic": text(queue.get("primary_topic")),
        "validator_status": text(queue.get("validator_status")).upper(),
        "internal_leak_status": text(queue.get("internal_leak_status")).upper(),
        "account_fit_status": text(queue.get("account_fit_status")).upper(),
        "topic_coherence_status": text(queue.get("topic_coherence_status")).upper(),
        "batch_diversity_status": text(queue.get("batch_diversity_status")).upper(),
        "media_validator_status": text(queue.get("media_status")).upper(),
        "created_at": text(existing.get("created_at")) or now_iso(),
        "updated_at": now_iso(),
        # These cells are owned by the reviewer, never the synchronizer.
        "review_decision": text(existing.get("review_decision")).upper(),
        "reviewer_note": text(existing.get("reviewer_note")),
        "decision_applied_at": text(existing.get("decision_applied_at")),
        "decision_result": text(existing.get("decision_result")),
        "last_sync_at": now_iso(),
    }


def decision_for_row(review: Mapping[str, Any], queue: Mapping[str, Any], *, allow_media_posts: bool) -> tuple[str, dict[str, str]]:
    """Return a bounded queue transition; never publish from a review decision."""
    decision = text(review.get("review_decision")).upper()
    if decision not in {"OK", "NG", "HOLD"}:
        return "SKIP", {}
    if text(queue.get("status")).upper() != "WAITING_REVIEW":
        return "SKIP", {}
    if decision == "NG":
        return "REJECTED", {
            "status": "REJECTED",
            "human_review_decision": "NG",
            "human_review_note": text(review.get("reviewer_note")),
            "human_reviewed_at": now_iso(),
            "rejected_reason": "human_review_ng",
        }
    if decision == "HOLD":
        return "HOLD", {"human_review_decision": "HOLD", "human_review_note": text(review.get("reviewer_note")), "human_reviewed_at": now_iso()}

    if text(queue.get("validator_status")).upper() != "PASS" or text(queue.get("internal_leak_status")).upper() not in {"", "PASS"}:
        return "BLOCKED_VALIDATION", {}
    if text(queue.get("media_required")).lower() in {"true", "1", "yes"} and not allow_media_posts:
        return "APPROVED_PENDING_MEDIA_GATE", {}
    return "READY", {
        "status": "READY",
        "human_review_decision": "OK",
        "human_review_note": text(review.get("reviewer_note")),
        "human_reviewed_at": now_iso(),
    }
