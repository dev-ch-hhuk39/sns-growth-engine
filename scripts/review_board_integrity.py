"""Strict, read-only identity checks for legacy human review Sheets.

Applied before review-board planning and writes. No media rights are issued.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any


class ReviewBoardBlocked(RuntimeError):
    """Sanitized blocking reason; never put editable text into exceptions."""


_REVIEW_MUTABLE_FIELDS = (
    "review_decision", "reviewer_note", "decision_applied_at", "decision_result",
)
_LEGACY_IDENTITY_FIELDS = ("review_id", "account_id", "platform", "post_type")


def _timestamp(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None


def _safe_newer_unreviewed_legacy_snapshot(
    prior: Mapping[str, Any], newer: Mapping[str, Any],
) -> bool:
    """Reconcile only clearly older, never-reviewed mirror records.

    The original row stays untouched in Sheets. A newer duplicate may contain
    an operator decision: material evidence is checked separately before use.
    The older row must NEVER contain reviewer-authored data.
    """
    if any(str(prior.get(field) or "").strip() for field in _REVIEW_MUTABLE_FIELDS):
        return False
    if any(
        not str(prior.get(field) or "").strip()
        or str(prior.get(field) or "").strip() != str(newer.get(field) or "").strip()
        for field in _LEGACY_IDENTITY_FIELDS
    ):
        return False
    if str(prior.get("platform") or "").strip().lower() != "threads":
        return False
    if str(prior.get("review_status") or "").strip().upper() != "PENDING_REVIEW":
        return False
    old_time = _timestamp(prior.get("last_sync_at"))
    new_time = _timestamp(newer.get("last_sync_at"))
    return old_time is not None and new_time is not None and new_time > old_time


def index_review_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    source: str,
) -> dict[str, dict[str, Any]]:
    if source not in {"QUEUE", "REVIEW"}:
        raise ReviewBoardBlocked("REVIEW_SOURCE_INVALID")
    indexed: dict[str, dict[str, Any]] = {}
    legacy_duplicates_seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ReviewBoardBlocked("REVIEW_SOURCE_ROW_INVALID")
        identity = str(row.get("queue_id") or "").strip()
        if not identity:
            if any(str(value or "").strip() for value in row.values()):
                raise ReviewBoardBlocked(f"{source}_QUEUE_ID_MISSING")
            continue
        if identity in indexed:
            # Never coalesce operational queue identities or live review votes.
            # Legacy duplicate review mirrors are only reconciled when their
            # older row was never reviewed and the newer row has the same
            # immutable identity, scope and a strictly later sync timestamp.
            if (source != "REVIEW" or identity in legacy_duplicates_seen
                    or not _safe_newer_unreviewed_legacy_snapshot(indexed[identity], row)):
                raise ReviewBoardBlocked(f"{source}_QUEUE_ID_DUPLICATE")
            legacy_duplicates_seen.add(identity)
        indexed[identity] = dict(row)
    return indexed


def require_review_account_match(
    reviews: Mapping[str, Mapping[str, Any]],
    queues: Mapping[str, Mapping[str, Any]],
) -> None:
    for identity, review in reviews.items():
        queue = queues.get(identity)
        if not queue:
            continue
        account = str(queue.get("account_id") or "").strip()
        if not account:
            raise ReviewBoardBlocked("QUEUE_ACCOUNT_MISSING")
        recorded = str(review.get("account_id") or "").strip()
        if recorded and recorded != account:
            raise ReviewBoardBlocked("REVIEW_ACCOUNT_ID_MISMATCH")
        platform = str(review.get("platform") or "").strip().lower()
        queue_platform = str(queue.get("platform") or "").strip().lower()
        if platform and platform != queue_platform:
            raise ReviewBoardBlocked("REVIEW_PLATFORM_MISMATCH")


REVIEW_MATERIAL_FIELDS = (
    "account_id", "platform", "public_post_text", "media_asset_id",
    "media_type", "source_url", "source_id", "post_type",
)


def require_fresh_decision_evidence(
    review: Mapping[str, Any], queue: Mapping[str, Any],
    *,
    selected_fields: Mapping[str, Any],
) -> None:
    """No READY/rejection based on an old caption or another asset.

    Only assert when this decision would mutate operational queue state.
    The review-board projection uses these exact material field definitions.
    """
    if not selected_fields:
        return
    from publication_review_board import review_row, text

    projected = review_row(queue, review)
    for field in REVIEW_MATERIAL_FIELDS:
        if text(review.get(field)) != text(projected.get(field)):
            raise ReviewBoardBlocked("REVIEW_MATERIAL_CHANGED_REAPPROVAL_REQUIRED")
    if text(review.get("review_status")).upper() in {
        "STALE_REVIEW_RECHECK_REQUIRED", "BLOCKED_STALE_REVIEW",
    }:
        raise ReviewBoardBlocked("REVIEW_STALE_DECISION_REAPPROVAL_REQUIRED")
