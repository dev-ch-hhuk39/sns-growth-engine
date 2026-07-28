#!/usr/bin/env python3
"""Fail-closed persistence and retry decisions after a social publish call."""
from __future__ import annotations

import hashlib
from typing import Any


def delivery_idempotency_key(*, account_id: str, platform: str, queue_id: str, external_post_id: str) -> str:
    raw = "|".join((account_id, platform, queue_id, external_post_id))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_posted_result_persistence(rows: list[dict[str, Any]], *, result_id: str, queue_id: str, account_id: str, external_post_id: str) -> dict[str, str]:
    """Confirm that the exact published result is visible before considering it saved."""
    for row in rows:
        if str(row.get("result_id", "")) != result_id:
            continue
        if str(row.get("status", "")).upper() != "POSTED":
            return {"status": "FAIL", "reason": "RESULT_STATUS_NOT_POSTED"}
        if str(row.get("queue_id", "")) != queue_id or str(row.get("account_id", "")) != account_id:
            return {"status": "FAIL", "reason": "RESULT_IDENTITY_MISMATCH"}
        if external_post_id and str(row.get("external_post_id", "")) != external_post_id:
            return {"status": "FAIL", "reason": "EXTERNAL_POST_ID_MISMATCH"}
        return {"status": "PASS", "reason": "READ_AFTER_WRITE_CONFIRMED"}
    return {"status": "FAIL", "reason": "RESULT_NOT_VISIBLE_AFTER_WRITE"}


def retry_disposition(*, publish_succeeded: bool, persisted: bool, api_outcome_known: bool) -> str:
    """Never retry a request whose remote posting outcome may already be true."""
    if publish_succeeded or api_outcome_known:
        return "DO_NOT_RETRY_MANUAL_RECOVERY"
    if persisted:
        return "DO_NOT_RETRY_ALREADY_PERSISTED"
    return "RETRY_SAFE_BEFORE_REMOTE_ACCEPTANCE"
