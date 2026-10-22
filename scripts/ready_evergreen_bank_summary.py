#!/usr/bin/env python3
"""Fail-closed, fixed-field CI receipt for private evergreen bank JSON."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ACCOUNTS = ("night_scout", "liver_manager", "beauty_account")
MAX_REPORT_BYTES = 5_000_000


def redacted_bank_summary(report: object, account: str) -> tuple[str, bool]:
    """Never interpolate untrusted values from the report into public logs."""
    prefix = "EVERGREEN_BANK_REDACTED: account=" + account
    if not isinstance(report, dict) or report.get("mode") != "EVERGREEN_BANK":
        return prefix + " status=INVALID_REPORT", False
    if report.get("status") != "PASS" or report.get("would_post") is not False:
        return prefix + " status=NOT_READY", False
    by_account = report.get("evergreen_bank_by_account")
    if not isinstance(by_account, dict) or set(by_account) != {account}:
        return prefix + " status=INCOMPLETE_ACCOUNT_SCOPE", False
    bank = by_account.get(account)
    if not isinstance(bank, dict) or bank.get("status") != "READY_INVENTORY_OK":
        return prefix + " status=NOT_READY", False
    count = bank.get("usable_evergreen")
    minimum = bank.get("minimum")
    if (type(count) is not int or type(minimum) is not int
            or minimum <= 0 or count < minimum or count > 100000):
        return prefix + " status=INVALID_COUNTS", False
    return prefix + f" status=PASS usable={count} minimum={minimum} no_post=true", True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--account-id", choices=ACCOUNTS, required=True)
    args = parser.parse_args()
    try:
        path = Path(args.report)
        if path.stat().st_size > MAX_REPORT_BYTES:
            raise ValueError("oversized_report")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, TypeError):
        print("EVERGREEN_BANK_REDACTED: status=UNAVAILABLE")
        return 2
    result, ok = redacted_bank_summary(data, args.account_id)
    print(result)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
