"""Strict, read-only identity checks for legacy human review Sheets.

Applied before review-board planning and writes. No media rights are issued.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class ReviewBoardBlocked(RuntimeError):
    """Sanitized blocking reason; never put editable text into exceptions."""


def index_review_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    source: str,
) -> dict[str, dict[str, Any]]:
    if source not in {"QUEUE", "REVIEW"}:
        raise ReviewBoardBlocked("REVIEW_SOURCE_INVALID")
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ReviewBoardBlocked("REVIEW_SOURCE_ROW_INVALID")
        identity = str(row.get("queue_id") or "").strip()
        if not identity:
            if any(str(value or "").strip() for value in row.values()):
                raise ReviewBoardBlocked(f"{source}_QUEUE_ID_MISSING")
            continue
        if identity in indexed:
            raise ReviewBoardBlocked(f"{source}_QUEUE_ID_DUPLICATE")
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
