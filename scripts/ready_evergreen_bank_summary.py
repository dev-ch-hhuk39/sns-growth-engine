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
})


def safe_bank_failure_category(report: dict, account: str) -> str:
    results = report.get("results")
    if not isinstance(results, list) or len(results) > 20:
        return "UNCLASSIFIED"
    for row in results:
        if not isinstance(row, dict) or row.get("account_id") != account:
            continue
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
            + " category=" + reason + " no_post=true"), False


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
        data = json.loads(path.read_text(encoding="utf-8"))
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
