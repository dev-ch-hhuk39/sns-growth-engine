#!/usr/bin/env python3
"""Verification code must require posted Threads results for both pilot accounts."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "scripts/recover_production_sheets_threads_first.py"


def main() -> int:
    src = VERIFY.read_text(encoding="utf-8")
    checks = [
        ("night_scout posted check exists", "posted_night_scout_threads_exists" in src),
        ("liver_manager posted check exists", "posted_liver_manager_threads_posted" in src),
        ("external id check", "posted_rows_have_external_post_id" in src),
        ("post url check", "posted_rows_have_post_url_or_permalink_pending" in src),
        ("queue consistency check", "queue_posted_has_posted_result" in src),
        ("duplicate text absent", "posted_duplicate_text_absent" in src),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
