"""Deterministic retry and quarantine state transitions."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

QUARANTINE_AFTER_SAME_FAILURES = 2


def failure_signature(reason: str) -> str:
    normalized = re.sub(r"\d+", "#", str(reason or "").strip().lower())[:300]
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def register_failure(
    row: dict[str, Any],
    reason: str,
    *,
    now: str | None = None,
    threshold: int = QUARANTINE_AFTER_SAME_FAILURES,
) -> dict[str, Any]:
    timestamp = now or datetime.now(timezone.utc).isoformat()
    signature = failure_signature(reason)
    previous = str(row.get("failure_signature", ""))
    count = int(str(row.get("same_failure_count", "0") or "0")) + 1 if previous == signature else 1
    quarantined = count >= threshold
    return {
        **row,
        "retry_count": str(int(str(row.get("retry_count", "0") or "0")) + 1),
        "last_error": str(reason)[:240],
        "failure_signature": signature,
        "same_failure_count": str(count),
        "last_attempt_at": timestamp,
        "processing_status": "QUARANTINED" if quarantined else row.get("processing_status", "RETRY_PENDING"),
        "quarantined_at": timestamp if quarantined else str(row.get("quarantined_at", "")),
        "quarantine_reason": str(reason)[:240] if quarantined else str(row.get("quarantine_reason", "")),
    }


def clear_failure(row: dict[str, Any], *, now: str | None = None) -> dict[str, Any]:
    return {
        **row,
        "last_error": "",
        "failure_signature": "",
        "same_failure_count": "0",
        "last_attempt_at": now or datetime.now(timezone.utc).isoformat(),
    }


def is_quarantined(row: dict[str, Any]) -> bool:
    return bool(str(row.get("quarantined_at", "")).strip()) or str(row.get("processing_status", "")).upper() == "QUARANTINED"


def build_quarantine_record(
    row: dict[str, Any],
    *,
    entity_type: str,
    entity_id: str,
    source_id: str,
    account_id: str,
    now: str | None = None,
) -> dict[str, Any]:
    """Build a redacted, idempotent audit row for a quarantined entity."""
    timestamp = now or datetime.now(timezone.utc).isoformat()
    return {
        "quarantine_id": f"q_{entity_type}_{entity_id}",
        "entity_type": entity_type,
        "entity_id": entity_id,
        "source_id": source_id,
        "account_id": account_id,
        "failure_signature": str(row.get("failure_signature", "")),
        "same_failure_count": str(row.get("same_failure_count", "0")),
        "status": "QUARANTINED",
        "first_failed_at": str(row.get("last_attempt_at", timestamp)),
        "last_failed_at": timestamp,
        "quarantined_at": str(row.get("quarantined_at", timestamp)),
        "resolution_status": "OPEN",
        "notes": str(row.get("quarantine_reason", row.get("last_error", "")))[:240],
    }
