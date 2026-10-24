#!/usr/bin/env python3
"""Fail-closed, fixed-field CI receipt for private evergreen bank JSON."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ready_inventory_diagnostics import classify_private_stderr

ACCOUNTS = ("night_scout", "liver_manager", "beauty_account")
MAX_REPORT_BYTES = 5_000_000


# Only these known fixed internal categories may reach a public Actions log.
# Any queue text, model response, provider error, or unknown token stays private.
SAFE_BANK_FAILURES = frozenset({
    "AI_APPROVAL_BUDGET_EXHAUSTED",
    "OWNER_REVIEW_REQUIRED",
    "SHEETS_QUOTA_EXHAUSTED",
    "PROVIDER_TIMEOUT",
    "PROVIDER_UNAVAILABLE",
    "QUALITY_EXHAUSTED",
    "NO_VALIDATED_BANK_CANDIDATE",
    "VALIDATOR_REJECTED",
    "GENERATION_OUTPUT_INVALID",
    "READY_REVIEW_REPORT_INVALID",
    "GENERATED_READBACK_UNVERIFIED",
    "GENERATED_RUNTIME_GATE_REJECTED",
})


def safe_bank_failure_category(report: dict, account: str) -> str:
    results = report.get("results")
    if not isinstance(results, list) or len(results) > 20:
        return "UNCLASSIFIED"
    for row in results:
        if not isinstance(row, dict) or row.get("account_id") != account:
            continue
        direct = row.get("failure_category")
        if isinstance(direct, str) and direct in SAFE_BANK_FAILURES:
            return direct
        attempts = row.get("attempts")
        if not isinstance(attempts, list) or len(attempts) > 20:
            continue
        for attempt in reversed(attempts):
            if not isinstance(attempt, dict):
                continue
            category = attempt.get("failure_category")
            if isinstance(category, str) and category in SAFE_BANK_FAILURES:
                return category
    return "UNCLASSIFIED"



# Fixed internal rejection keys only. Never print candidate text or identifiers.
SAFE_READBACK_REJECTIONS = frozenset({
    "GENERATION_REPORTED_NO_IDS",
    "GENERATED_ID_LIST_UNVERIFIABLE",
    "GENERATED_READBACK_UNVERIFIED",
    "GENERATED_IDENTITY_MISMATCH",
    "GENERATED_NOT_READY",
    "GENERATED_APPROVAL_INCOMPLETE",
    "GENERATED_RUNTIME_GATE_REJECTED",
})


def safe_bank_rejection_summary(report: dict, account: str) -> str:
    """Aggregate only allowlisted bounded review rejections, without IDs."""
    results = report.get("results")
    if account not in ACCOUNTS or not isinstance(results, list) or len(results) > 20:
        return ""
    counts: dict[str, int] = {}
    for row in results:
        if not isinstance(row, dict) or row.get("account_id") != account:
            continue
        attempts = row.get("attempts")
        if not isinstance(attempts, list) or len(attempts) > 20:
            continue
        for attempt in attempts:
            if not isinstance(attempt, dict):
                continue
            rejection = attempt.get("verification_rejection_counts")
            if not isinstance(rejection, dict) or len(rejection) > 12:
                continue
            for code, count in rejection.items():
                if (type(code) is str and code in SAFE_READBACK_REJECTIONS
                        and type(count) is int and 0 < count <= 3):
                    counts[code] = min(60, counts.get(code, 0) + count)
    if not counts:
        return ""
    return " readback_rejections=" + ",".join(
        f"{code}:{count}" for code, count in sorted(counts.items())
    )


def redacted_bank_summary(report: object, account: str) -> tuple[str, bool]:
    """Emit only bounded aggregate counts and fixed failure categories."""
    prefix = "EVERGREEN_BANK_REDACTED: account=" + account
    if account not in ACCOUNTS:
        return "EVERGREEN_BANK_REDACTED: status=INVALID_ACCOUNT", False
    if not isinstance(report, dict) or report.get("mode") != "EVERGREEN_BANK":
        return prefix + " status=INVALID_REPORT", False
    by_account = report.get("evergreen_bank_by_account")
    if not isinstance(by_account, dict) or set(by_account) != {account}:
        return prefix + " status=INCOMPLETE_ACCOUNT_SCOPE", False
    bank = by_account.get(account)
    if not isinstance(bank, dict):
        return prefix + " status=NOT_READY", False
    count = bank.get("usable_evergreen")
    minimum = bank.get("minimum")
    if (type(count) is not int or type(minimum) is not int
            or minimum <= 0 or count < 0 or count > 100000
            or minimum > 100000):
        return prefix + " status=INVALID_COUNTS", False
    if (report.get("status") == "PASS"
            and report.get("would_post") is False
            and bank.get("status") == "READY_INVENTORY_OK"
            and count >= minimum):
        return prefix + f" status=PASS usable={count} minimum={minimum} no_post=true", True
    if report.get("would_post") is not False:
        return prefix + " status=UNVERIFIED_NO_POST_GUARD", False
    reason = safe_bank_failure_category(report, account)
    return (prefix + f" status=NOT_READY usable={count} minimum={minimum}"
            + " category=" + reason + " no_post=true"
            + safe_bank_rejection_summary(report, account)), False


def parse_bounded_bank_json(raw: str, account: str) -> dict:
    """Recover only a final, account-scoped bank receipt after noisy stdout.

    A preceding generator object or an incomplete run must never be accepted
    as proof of usable reserves. No raw text is included in public reports.
    """
    if not raw or len(raw) > MAX_REPORT_BYTES:
        raise ValueError("bank_report_size_invalid")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        starts = []
        position = 0
        for line in raw.splitlines(keepends=True):
            if line.startswith("{"):
                starts.append(position)
                if len(starts) > 512:
                    raise ValueError("too_many_bank_output_objects")
            position += len(line)
        if not starts:
            raise ValueError("no_bank_report")
        try:
            value, end = json.JSONDecoder().raw_decode(raw, starts[-1])
        except json.JSONDecodeError as exc:
            raise ValueError("invalid_final_bank_report") from exc
        if raw[starts[-1] + end:].strip():
            raise ValueError("trailing_unverified_bank_output")
    if (not isinstance(value, dict)
            or value.get("mode") != "EVERGREEN_BANK"
            or value.get("would_post") is not False
            or not isinstance(value.get("results"), list)
            or not isinstance(value.get("evergreen_bank_by_account"), dict)
            or set(value["evergreen_bank_by_account"]) != {account}):
        raise ValueError("bank_report_scope_or_safety_invalid")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--account-id", choices=ACCOUNTS, required=True)
    parser.add_argument("--private-stderr")
    args = parser.parse_args()
    try:
        path = Path(args.report)
        if path.stat().st_size > MAX_REPORT_BYTES:
            raise ValueError("oversized_report")
        data = parse_bounded_bank_json(path.read_text(encoding="utf-8"), args.account_id)
    except (OSError, UnicodeError, ValueError, TypeError):
        if args.private_stderr:
            hint = classify_private_stderr(Path(args.private_stderr))
            print("EVERGREEN_BANK_REDACTED: status=UNAVAILABLE PRIVATE_FAILURE_HINT=" + hint)
        else:
            print("EVERGREEN_BANK_REDACTED: status=UNAVAILABLE")
        return 2
    result, ok = redacted_bank_summary(data, args.account_id)
    print(result)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
