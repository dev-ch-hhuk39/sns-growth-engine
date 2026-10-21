#!/usr/bin/env python3
"""Summarize a *read-only* content slot scan without logging source Sheet data.

The raw JSON and stderr remain in RUNNER_TEMP and are never uploaded as a
workflow artifact. Only allowlisted status/reason labels and counts escape.
Do not convert a failed audit into a successful job.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

MAX_BYTES = 2_000_000
ACCOUNTS = frozenset(("night_scout", "liver_manager", "beauty_account"))
STATUSES = frozenset((
    "PASS", "FAILED", "BLOCKED", "DRY_RUN", "SKIPPED",
    "PRE_PUBLISH_FAILED", "DELIVERY_FAILED_CONFIRMED",
    "RECOVERY_REQUIRED", "POSTED",
))
REASONS = frozenset((
    "NO_VALIDATED_BUFFERED_QUEUE",
    "KILL_SWITCH_OR_BUFFER_NOT_ACTIVATED",
    "DAILY_CAP_REACHED",
    "COOLDOWN_ACTIVE",
    "POSTED_TIME_UNVERIFIED",
    "SLOT_CLOSED_DURING_RECONCILIATION",
    "RUNTIME_ACTIVATION_GATE_BLOCKED",
    "P0_RELEASE_OWNER_CONSENT_OR_LIVE_PROOF_INVALID",
    "PUBLISH_NOT_VERIFIED",
    "SHEETS_QUOTA_EXHAUSTED",
    "OWNER_REVIEW_REQUIRED",
    "NO_PUBLISHABLE_READY",
    "NO_HARD_GATE_MEDIA",
))


def safe_label(value: object, allowlist: frozenset[str]) -> str:
    return value if isinstance(value, str) and value in allowlist else "OTHER_REDACTED"


def summarize(document: object, account_id: str) -> tuple[str, int]:
    """Returns a log-safe single line and the original aggregate outcome."""
    if account_id not in ACCOUNTS:
        return "SLOT_AUDIT_SUMMARY_INVALID_ACCOUNT", 78
    if not isinstance(document, dict) or document.get("dry_run") is not True:
        return f"SLOT_AUDIT_INVALID_DRY_RUN account={account_id}", 78
    entries = document.get("results")
    status = document.get("status")
    if status not in ("PASS", "FAILED") or not isinstance(entries, list):
        return f"SLOT_AUDIT_INVALID_SCHEMA account={account_id}", 78
    if len(entries) > 100:
        return f"SLOT_AUDIT_OVERSIZED_RESULTS account={account_id}", 78

    statuses: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    for row in entries:
        if not isinstance(row, dict):
            return f"SLOT_AUDIT_INVALID_ROW account={account_id}", 78
        row_account = row.get("account_id")
        if row_account is not None and row_account != account_id:
            return f"SLOT_AUDIT_ACCOUNT_MISMATCH account={account_id}", 78
        bucket = safe_label(row.get("status"), STATUSES)
        statuses[bucket] += 1
        if bucket in ("FAILED", "BLOCKED", "PRE_PUBLISH_FAILED",
                      "DELIVERY_FAILED_CONFIRMED", "RECOVERY_REQUIRED"):
            reasons[safe_label(row.get("reason"), REASONS)] += 1

    def counts(values: Counter[str]) -> str:
        return ",".join(f"{key}:{values[key]}" for key in sorted(values)) or "none"

    line = (f"SLOT_AUDIT_REDACTED account={account_id} status={status} "
            f"slots={len(entries)} statuses={counts(statuses)} "
            f"reasons={counts(reasons)}")
    return line, 0 if status == "PASS" else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-file", type=Path, required=True)
    parser.add_argument("--account-id", choices=sorted(ACCOUNTS), required=True)
    args = parser.parse_args()
    try:
        if args.report_file.is_symlink() or not args.report_file.is_file():
            raise ValueError("INVALID_REPORT_FILE")
        if args.report_file.stat().st_size > MAX_BYTES:
            raise ValueError("OVERSIZED_REPORT_FILE")
        document = json.loads(args.report_file.read_text(encoding="utf-8"))
        line, code = summarize(document, args.account_id)
    except (OSError, ValueError, UnicodeError, TypeError):
        line, code = f"SLOT_AUDIT_UNVERIFIED_REPORT account={args.account_id}", 78
    print(line)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
