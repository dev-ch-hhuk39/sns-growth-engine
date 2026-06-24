#!/usr/bin/env python3
"""Validate metrics dry-run returns before config/Sheets connection."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    env = os.environ.copy()
    for key in ["SNS_MASTER_SHEET_ID", "SPREADSHEET_ID", "SA_JSON_BASE64", "GCP_SA_JSON_BASE64", "GCP_SA_JSON"]:
        env.pop(key, None)
    cmd = [
        sys.executable,
        str(ROOT / "scripts/import_threads_metrics_manual.py"),
        "--result-id", "dummy_result_id",
        "--views", "100",
        "--likes", "5",
        "--comments", "1",
        "--follows", "0",
        "--profile-clicks", "2",
        "--line-adds", "0",
        "--memo", "dry-run test",
        "--dry-run",
    ]
    proc = subprocess.run(cmd, cwd=ROOT, env=env, text=True, capture_output=True, check=False)
    checks = [
        ("exit 0 without sheets env", proc.returncode == 0),
        ("dry_run output", '"dry_run": true' in proc.stdout.lower()),
        ("no config error", "SNS_MASTER_SHEET_ID" not in proc.stderr and "SA_JSON" not in proc.stderr),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    if proc.stderr:
        print(proc.stderr.strip())
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
