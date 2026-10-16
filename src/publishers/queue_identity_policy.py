"""Legacy queue identity preflight for incremental source-authority migration.

This is NOT distributed CAS, a publish permission, or a schema migration.
Provider and human-authenticated controls remain separate.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

IMMUTABLE_QUEUE_FIELDS = frozenset({
    "queue_id", "account_id", "platform", "slot_id", "draft_id",
})
NON_REOPENABLE_STATUSES = frozenset({
    "POSTED", "PROCESSING", "PUBLISH_OUTCOME_UNVERIFIED",
    "POSTED_SAVE_FAILED", "POSTED_SAVE_UNVERIFIED",
    "REJECTED", "SUPERSEDED", "FAILED",
})


def assert_safe_queue_patch(
    current: Mapping[str, Any],
    patch: Mapping[str, Any],
    *,
    queue_id: str,
) -> None:
    """Reject identity rewrites and stale/uncertain READY promotions.

    Missing historical fields are not repaired implicitly. Existing values
    may be sent unchanged but an account, route, or queue key cannot move.
    """
    if not queue_id or str(current.get("queue_id", "")) != str(queue_id):
        raise PermissionError("queue_identity_preflight_failed")
    for field in IMMUTABLE_QUEUE_FIELDS.intersection(patch):
        if str(patch[field] if patch[field] is not None else "") != str(current.get(field, "")):
            raise PermissionError("queue_immutable_identity_change")
    desired = str(patch.get("status") or "").strip().upper()
    if desired == "READY":
        previous = str(current.get("status") or "").strip().upper()
        if previous in NON_REOPENABLE_STATUSES or previous not in {"READY", "WAITING_REVIEW"}:
            raise PermissionError("queue_ready_invalid_prior_state")
