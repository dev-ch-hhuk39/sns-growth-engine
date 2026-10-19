#!/usr/bin/env python3
"""Redacted, account-scoped summary for READY maintenance JSON (no writes)."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

ACCOUNTS = ("night_scout", "liver_manager", "beauty_account")
REASONS = {
    "OWNER_REVIEW_REQUIRED": "Request content review; do not bypass the approval gate.",
    "PROVIDER_CREDENTIALS_MISSING_OR_REJECTED": "Check the scoped provider setup without displaying credentials.",
    "SHEETS_QUOTA_EXHAUSTED": "Stop retries until Sheets quota recovers.",
    "AI_APPROVAL_BUDGET_EXHAUSTED": "Respect provider budget; reuse only validated inventory.",
    "PROVIDER_RATE_LIMITED": "Use bounded backoff.",
    "PROVIDER_UNAVAILABLE": "Check provider availability.",
    "PROVIDER_CONFIGURATION_ERROR": "Verify scoped provider configuration.",
    "REFERENCE_CONTEXT_UNAVAILABLE": "Provide a verified source instead.",
    "SOURCE_CONTEXT_READ_FAILED": "Check source/read permission.",
    "DUPLICATE_GENERATION_EXHAUSTED": "Do not reuse previously published content.",
    "NO_VALIDATED_BANK_CANDIDATE": "No validated evergreen inventory exists.",
    "QUALITY_EXHAUSTED": "Keep rejected candidates out of READY.",
    "NO_PUBLISHABLE_READY": "No slot-eligible candidate was verified.",
    "GENERATION_PROCESS_FAILED": "Inspect redacted generator diagnostics.",
    "GENERATION_PROCESS_TIMEOUT": "Review timeout and bounded retry settings.",
    "PERMISSION_OR_SAFETY_FAILURE": "Do not bypass the fail-closed safety gate.",
    "KILL_SWITCH_ACTIVE": "Do not enable publishing.",
    "PROVIDER_TIMEOUT": "Check provider latency.",
}
UNKNOWN = "UNCLASSIFIED_FAILURE"


def normalized_reason(value: Any) -> str:
    """Never surface arbitrary provider messages or candidate text."""
    if not isinstance(value, str) or not value.strip():
        return ""
    return value if value in REASONS else UNKNOWN


def reasons_for_slot(row: dict[str, Any]) -> set[str]:
    reasons: set[str] = set()
    for key in ("delivery_generation_failure_category", "reserve_generation_failure_category", "failure_category"):
        code = normalized_reason(row.get(key))
        if code:
            reasons.add(code)
    for key in ("delivery_generation_attempts", "reserve_generation_attempts", "attempts"):
        attempts = row.get(key)
        if isinstance(attempts, list):
            for attempt in attempts:
                if isinstance(attempt, dict):
                    code = normalized_reason(attempt.get("reason"))
                    if code:
                        reasons.add(code)
    if not reasons and row.get("delivery_slo") == "FAIL":
        reasons.add("NO_PUBLISHABLE_READY")
    return reasons


def render_report(data: Any, account: str) -> str:
    if account not in ACCOUNTS or not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ValueError("invalid_diagnostics_scope_or_input")
    scoped = [row for row in data["results"]
              if isinstance(row, dict) and row.get("account_id") == account and "delivery_slo" in row]
    failed = [row for row in scoped if row.get("delivery_slo") != "PASS"]
    passed = len(scoped) - len(failed)
    counts: Counter[str] = Counter()
    for row in failed:
        counts.update(reasons_for_slot(row))
    lines = [
        "### READY inventory diagnosis: " + account,
        "- Delivery slots: " + str(passed) + "/" + str(len(scoped)) + " verified; " + str(len(failed)) + " missing",
        "- Maintenance outcome: " + ("PASS" if scoped and not failed and data.get("status") == "PASS" else "BLOCKED"),
    ]
    if not scoped:
        lines.append("- Evidence: NO_REQUIRED_TEXT_SLOTS_OR_REPORT_INCOMPLETE (not proof of READY coverage)")
    for code, count in sorted(counts.items()):
        lines.append("- " + code + ": " + str(count) + " affected slots")
        lines.append("  Action: " + REASONS.get(code, "Inspect redacted logs; do not automatically retry."))
    lines.append("- Safety: no approval bypass, no queue-status rewrite, no SNS post.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", choices=ACCOUNTS, required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    try:
        path = Path(args.report)
        if path.stat().st_size > 5_000_000:
            raise ValueError("report_too_large")
        report = json.loads(path.read_text(encoding="utf-8"))
        result = render_report(report, args.account_id)
    except (OSError, UnicodeError, ValueError, TypeError):
        print("READY_DIAGNOSTICS_UNAVAILABLE: invalid or missing report; original step failure remains authoritative.")
        return 2
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
