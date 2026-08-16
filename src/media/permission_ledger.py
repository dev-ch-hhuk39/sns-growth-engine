"""Fail-closed evaluation of the live reusable-media permission ledger."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable

from media.rights_policy import APPROVED_MEDIA_RIGHTS, normalize_rights_status


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "approved", "allow", "allowed"}


def _targets(value: Any) -> set[str]:
    if isinstance(value, list):
        return {str(item).strip() for item in value if str(item).strip()}
    text = str(value or "").strip()
    if not text:
        return set()
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = []
        if isinstance(parsed, list):
            return {str(item).strip() for item in parsed if str(item).strip()}
    return {item.strip() for item in text.split(",") if item.strip()}


def latest_permission(rows: Iterable[dict[str, Any]], source_id: str) -> dict[str, Any]:
    matches = [
        (index, dict(row))
        for index, row in enumerate(rows)
        if str(row.get("source_id") or "").strip() == source_id
    ]
    if not matches:
        return {}
    return max(
        matches,
        key=lambda item: (
            str(item[1].get("updated_at") or item[1].get("approved_at") or ""),
            item[0],
        ),
    )[1]


def evaluate_permission(
    rows: Iterable[dict[str, Any]],
    source_id: str,
    *,
    account_id: str = "",
    source_handle: str = "",
    required_flags: Iterable[str] = (),
) -> dict[str, Any]:
    """Evaluate one source-specific latest ledger row without inferring rights."""
    row = latest_permission(rows, source_id)
    reasons: list[str] = []
    if not row:
        reasons.append("permission_row_missing")
        return {"allowed": False, "reasons": reasons, "row": {}}
    if truthy(row.get("revoked")):
        reasons.append("permission_revoked")
    expires_at = str(row.get("expires_at") or "").strip()
    if expires_at:
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry <= datetime.now(timezone.utc):
                reasons.append("permission_expired")
        except ValueError:
            reasons.append("permission_expiry_invalid")
    if str(row.get("permission_status") or "").strip().lower() != "approved":
        reasons.append("permission_status_not_approved")
    if normalize_rights_status(row.get("rights_status")) not in APPROVED_MEDIA_RIGHTS:
        reasons.append("rights_status_not_approved_for_media")
    if str(row.get("usage_mode") or "").strip().lower() in {
        "reference_only",
        "analysis_only",
        "text_reference",
    }:
        reasons.append("permission_usage_mode_reference_only")
    if not str(row.get("evidence_type") or "").strip():
        reasons.append("permission_evidence_type_missing")
    if not str(row.get("evidence_reference") or "").strip():
        reasons.append("permission_evidence_reference_missing")
    if not str(row.get("approved_by") or "").strip():
        reasons.append("permission_approved_by_missing")
    if not str(row.get("approved_at") or "").strip():
        reasons.append("permission_approved_at_missing")
    scoped_accounts = _targets(row.get("allowed_accounts") or row.get("account_id"))
    if account_id and scoped_accounts and account_id not in scoped_accounts:
        reasons.append("permission_account_scope_mismatch")
    expected_handle = str(source_handle or "").strip().lstrip("@").lower()
    ledger_handle = str(row.get("source_handle") or "").strip().lstrip("@").lower()
    if expected_handle and not ledger_handle:
        reasons.append("permission_source_handle_missing")
    elif expected_handle and ledger_handle != expected_handle:
        reasons.append("permission_source_handle_mismatch")
    for flag in required_flags:
        if not truthy(row.get(flag)):
            reasons.append(f"permission_flag_missing:{flag}")
    return {"allowed": not reasons, "reasons": reasons, "row": row}
