#!/usr/bin/env python3
"""Redacted, account-scoped summary for READY maintenance JSON (no writes)."""
from __future__ import annotations

import argparse
import json
import re
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
    "READY_CREATED_NOT_PUBLISHABLE": "A generated READY did not pass exact-slot dry-run gates; inspect redacted rejection counts.",
    "GENERATION_PROCESS_FAILED": "Inspect redacted generator diagnostics.",
    "GENERATION_PROCESS_TIMEOUT": "Review timeout and bounded retry settings.",
    "PERMISSION_OR_SAFETY_FAILURE": "Do not bypass the fail-closed safety gate.",
    "KILL_SWITCH_ACTIVE": "Do not enable publishing.",
    "PROVIDER_TIMEOUT": "Check provider latency.",
}
UNKNOWN = "UNCLASSIFIED_FAILURE"
# Stable, privacy-preserving categories only. No queue IDs, captions, freeform
# provider text or exception details are allowed through this renderer.
READY_REJECTION_CODES = frozenset({
    "GENERATION_REPORTED_NO_IDS",
    "GENERATED_ID_LIST_UNVERIFIABLE",
    "QUEUE_ID_NOT_UNIQUE_OR_NOT_VISIBLE",
    "ACCOUNT_ID_MISMATCH",
    "EXACT_SLOT_OR_DATE_MISMATCH",
    "STATUS_NOT_READY",
    "READY_APPROVAL_FLAGS_INCOMPLETE",
    "NON_TEXT_POST_TYPE",
    "RUNTIME_ELIGIBILITY_OR_MEDIA_GATE",
    "FINAL_PUBLIC_TEXT_VALIDATOR",
    "HYBRID_AI_SOURCE_GATE",
    "RUNTIME_DRY_RUN_GATE",
    "PUBLISHABILITY_AUDIT_INCONSISTENT",
    "RUNTIME_DIAGNOSTIC_UNAVAILABLE",
})


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


def validated_no_due_slot_skip(data: dict[str, Any], account: str) -> bool:
    """A no-op is not proof of READY coverage; verify its exact scope."""
    if data.get("status") != "SKIPPED_NO_DUE_TEXT_SLOTS":
        return False
    horizon = data.get("horizon_hours")
    return (
        account in ACCOUNTS
        and type(horizon) is int and 1 <= horizon < 24
        and data.get("would_post") is False
        and data.get("coverage_failure_reason") == "NO_REQUIRED_TEXT_SLOTS"
        and data.get("text_delivery_coverage_72h_percent") is None
        and data.get("text_delivery_coverage_by_account") ==
            {account: {"covered_slots": 0, "required_slots": 0}}
        and data.get("results") == []
        and data.get("hard_delivery_failures") == []
        and data.get("reserve_status") == "NOT_APPLICABLE"
    )


def render_report(data: Any, account: str) -> str:
    if account not in ACCOUNTS or not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ValueError("invalid_diagnostics_scope_or_input")
    if data.get("status") == "SKIPPED_NO_DUE_TEXT_SLOTS":
        if not validated_no_due_slot_skip(data, account):
            raise ValueError("invalid_no_due_slot_skip")
        return "\n".join((
            "### READY inventory diagnosis: " + account,
            "- Delivery slots: 0/0 verified; 0 missing",
            "- Maintenance outcome: SKIPPED_NO_DUE_TEXT_SLOTS (not READY coverage PASS)",
            "- Evidence: NO_DUE_TEXT_SLOTS_IN_REQUESTED_HORIZON",
            "- Safety: no approval bypass, no queue-status rewrite, no SNS post.",
        ))
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
    rejection_counts: Counter[str] = Counter()
    for row in failed:
        if row.get("delivery_generation_failure_category") != "READY_CREATED_NOT_PUBLISHABLE":
            continue
        details = row.get("generated_ready_rejection_counts")
        if not isinstance(details, dict) or len(details) > 20:
            rejection_counts["UNCLASSIFIED_REJECTION"] += 1
            continue
        for code, value in details.items():
            sanitized = code if isinstance(code, str) and code in READY_REJECTION_CODES else "UNCLASSIFIED_REJECTION"
            count = value if type(value) is int and 0 < value <= 12 else 1
            rejection_counts[sanitized] += count
    for code, count in sorted(rejection_counts.items()):
        lines.append("- Generated READY rejection " + code + ": " + str(count) + " candidates")
    lines.append("- Safety: no approval bypass, no queue-status rewrite, no SNS post.")
    return "\n".join(lines)


# Exact error identities only. Never derive public hints from arbitrary
# exception messages, paths, IDs, provider responses, captions or secrets.
# These codes identify the branch to inspect and never authorize a retry.
SAFE_EVERGREEN_EXCEPTION_CODES = frozenset({
    "EVERGREEN_APPROVAL_READ_AFTER_WRITE_FAILED",
    "EVERGREEN_BATCH_READ_AFTER_WRITE_FAILED",
    "EVERGREEN_ADMISSION_RECEIPT_UNVERIFIED",
    "EVERGREEN_ALLOCATION_RELEASE_READ_AFTER_WRITE_FAILED",
    "EVERGREEN_RELEASE_READ_AFTER_WRITE_FAILED",
    "EVERGREEN_QUEUE_SCHEMA_MISSING",
    "EVERGREEN_BANK_SCHEMA_MISSING",
    "EVERGREEN_CANONICAL_IDENTITY_CONFLICT",
    "EVERGREEN_QUEUE_CHANGED",
    "EVERGREEN_BANK_IDENTITY_CONFLICT",
    "EVERGREEN_BATCH_LIMIT_OR_DUPLICATE",
})


def fixed_evergreen_exception_hint(stderr: str) -> str:
    """Extract only an approved literal exception code, not trace contents."""
    if not isinstance(stderr, str):
        return ""
    # Parse only exception terminator lines, never arbitrary provider prose.
    for line in reversed(stderr.splitlines()[-256:]):
        match = re.fullmatch(
            r"(?:RuntimeError|ValueError|PermissionError|AssertionError): "
            r"([A-Z][A-Z0-9_]{4,96})",
            line.strip(),
        )
        if match and match.group(1) in SAFE_EVERGREEN_EXCEPTION_CODES:
            return match.group(1)
    return ""


def classify_private_stderr(path: Path | None) -> str:
    """Return one fixed error code from private diagnostics, never their contents."""
    if path is None:
        return "NO_PRIVATE_DIAGNOSTICS"
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 2_000_000:
            return "PRIVATE_DIAGNOSTICS_UNAVAILABLE"
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "PRIVATE_DIAGNOSTICS_UNAVAILABLE"
    data = raw.lower()
    # Provider quota/timeout markers remain the higher-priority circuit
    # breakers; otherwise classify exact known bank readback faults.
    for code, phrases in (
        ("API_QUOTA_OR_RATE_LIMIT", ("resourceexhausted", "quota exceeded", "429 too many requests")),
        ("PROCESS_TIMEOUT", ("timeoutexpired", "readtimeout", "timed out", "deadlineexceeded")),
    ):
        if any(phrase in data for phrase in phrases):
            return code
    fixed = fixed_evergreen_exception_hint(raw)
    if fixed:
        return fixed
    indicators = (
        ("API_QUOTA_OR_RATE_LIMIT", ("resourceexhausted", "quota exceeded", "429 too many requests")),
        ("PROCESS_TIMEOUT", ("timeoutexpired", "readtimeout", "timed out", "deadlineexceeded")),
        ("PERMISSION_REJECTED", ("permissionerror", "permissiondenied", "403 forbidden")),
        ("PROVIDER_UNAVAILABLE", ("connectionerror", "connectionrefusederror", "serviceunavailable")),
        ("PYTHON_EXCEPTION", ("traceback (most recent call last)",)),
    )
    for code, phrases in indicators:
        if any(phrase in data for phrase in phrases):
            return code
    return "UNCLASSIFIED_FAILURE" if data.strip() else "EMPTY_PRIVATE_DIAGNOSTICS"


EARLY_BLOCK_CODES = {
    "apply requires confirmation and --use-sheets": "APPLY_CONFIRMATION_MISSING",
    "choose exactly one of --dry-run or --apply": "MODE_SELECTION_INVALID",
    "apply_requires_one_account": "MULTI_ACCOUNT_APPLY_BLOCKED",
    "max_bank_allocations_must_be_0_to_6": "BANK_ALLOCATION_LIMIT_INVALID",
    "reuse_only_requires_single_account_apply_without_evergreen_bank": "REUSE_MODE_INVALID",
    "inventory_horizon_must_be_1_to_168_hours": "HORIZON_INVALID",
}


def render_early_blocked_report(data: dict[str, Any]) -> str:
    """Only fixed identifiers may pass through from a blocked CLI response."""
    reason = data.get("reason")
    code = EARLY_BLOCK_CODES.get(reason, "UNCLASSIFIED_EARLY_BLOCK") if isinstance(reason, str) else "UNCLASSIFIED_EARLY_BLOCK"
    return "READY_INVOCATION_BLOCKED: " + code + "; no SNS post or approval bypass."


def parse_bounded_ready_json(raw: str) -> dict[str, Any]:
    """Decode a final READY report despite unrelated stdout lines.

    Never return arbitrary preceding generator objects or echo their text.
    Candidate starts are restricted to column zero JSON object braces,
    and the scan is strictly bounded.
    """
    if not raw or len(raw) > 5_000_000:
        raise ValueError("ready_output_size_invalid")
    try:
        direct = json.loads(raw)
        if isinstance(direct, dict):
            return direct
    except json.JSONDecodeError:
        pass

    starts = []
    position = 0
    for line in raw.splitlines(keepends=True):
        if line.startswith("{"):
            starts.append(position)
            if len(starts) > 512:
                raise ValueError("too_many_output_objects")
        position += len(line)
    decoder = json.JSONDecoder()
    for position in reversed(starts):
        try:
            value, _end = decoder.raw_decode(raw, position)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            regular_ready = (
                value.get("status") in ("PASS", "FAILED", "PLAN_ONLY", "SKIPPED_NO_DUE_TEXT_SLOTS")
                and value.get("would_post") is False
                and isinstance(value.get("results"), list)
                and isinstance(value.get("text_delivery_coverage_by_account"), dict)
            )
            early_block = (
                value.get("status") == "BLOCKED"
                and isinstance(value.get("reason"), str)
            )
            if regular_ready or early_block:
                return value
    raise ValueError("no_final_ready_report")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", choices=ACCOUNTS, required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--private-stderr", help="Private subprocess errors; emits fixed status only")
    args = parser.parse_args(argv)
    try:
        path = Path(args.report)
        if path.stat().st_size > 5_000_000:
            raise ValueError("report_too_large")
        report = parse_bounded_ready_json(path.read_text(encoding="utf-8"))
        result = (
            render_early_blocked_report(report)
            if report.get("status") == "BLOCKED"
            else render_report(report, args.account_id)
        )
    except (OSError, UnicodeError, ValueError, TypeError):
        hint = classify_private_stderr(Path(args.private_stderr) if args.private_stderr else None)
        print("READY_DIAGNOSTICS_UNAVAILABLE: invalid or missing report; original step failure remains authoritative. PRIVATE_FAILURE_HINT=" + hint)
        return 2
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
