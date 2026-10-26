#!/usr/bin/env python3
"""Local no-post, no-write per-account missed-slot audit; fixed redacted output."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path("/opt/github-runners/sns-growth-engine/.buffered-runtime/current")
sys.path.insert(0, str(ROOT / "scripts"))
from summarize_readonly_slot_audit import summarize  # noqa: E402

ACCOUNTS = ("night_scout", "liver_manager", "beauty_account")
MAX_BYTES = 2_000_000

def check_account(account: str) -> tuple[int, str]:
    if account not in ACCOUNTS:
        return 1, "SLOT_AUDIT=BLOCKED scope=invalid"
    command = [sys.executable, "-B", str(ROOT / "scripts/reconcile_due_production_slots.py"),
               "--account-id", account, "--dry-run"]
    try:
        child = subprocess.run(command, cwd=ROOT, capture_output=True,
                               text=True, timeout=180, check=False)
        if len(child.stdout.encode("utf-8")) > MAX_BYTES:
            raise ValueError("private_report_oversize")
        report = json.loads(child.stdout)
        summary, code = summarize(report, account)
        # Original failure semantics must be retained even if summary looks valid.
        return (0 if child.returncode == 0 and code == 0 else 1, summary)
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        return 1, f"SLOT_AUDIT=BLOCKED account={account} reason=UNVERIFIED_REPORT"

def main() -> int:
    failed = 0
    for account in ACCOUNTS:
        code, safe = check_account(account)
        print(safe, flush=True)
        failed += code != 0
    print(f"SNS_LOCAL_MISSED_SLOT_AUDIT={'PASS' if not failed else 'BLOCKED'} accounts=3 failures={failed} writes=0 posts=0")
    return int(failed != 0)

if __name__ == "__main__":
    raise SystemExit(main())
