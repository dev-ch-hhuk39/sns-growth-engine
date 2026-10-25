#!/usr/bin/env python3
"""Zero-write SNS three-account READY coverage audit; VPS systemd, no GitHub Actions."""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
SOURCE = Path("/opt/github-runners/sns-growth-engine/.buffered-runtime/current")
sys.path.insert(0, str(SOURCE / "scripts"))
from ready_inventory_diagnostics import render_report

ACCOUNTS = ('night_scout', 'liver_manager', 'beauty_account')

def run_one(account: str) -> tuple[int, str]:
    cmd = [sys.executable, str(SOURCE / 'scripts/maintain_text_ready_inventory.py'),
           '--account-id', account, '--dry-run', '--use-sheets', '--horizon-hours', '24']
    try:
        result = subprocess.run(cmd, cwd=SOURCE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, timeout=240, check=False)
        if len(result.stdout) > 1_000_000:
            return 1, 'SNS_READY_LOCAL_AUDIT=BLOCKED account=' + account + ' reason=OVERSIZED_PRIVATE_REPORT'
        data = json.loads(result.stdout)
        if not isinstance(data, dict) or data.get('would_post') is not False:
            raise ValueError('not_a_no_post_report')
        rendered = render_report(data, account)
        # Renderer exposes only fixed status/category counts; no drafts, IDs or credentials.
        return (0 if result.returncode == 0 and data.get('status') == 'PASS' else 1,
                rendered)
    except (OSError, ValueError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return 1, 'SNS_READY_LOCAL_AUDIT=BLOCKED account=' + account + ' reason=REPORT_UNVERIFIED'

def main() -> int:
    failures = 0
    for account in ACCOUNTS:
        status, summary = run_one(account)
        print(summary, flush=True)
        failures += int(status != 0)
    print(f'SNS_READY_LOCAL_AUDIT={"PASS" if failures == 0 else "BLOCKED"} accounts=3 failures={failures} posts=0 writes=0')
    return int(failures != 0)

if __name__ == '__main__':
    raise SystemExit(main())
