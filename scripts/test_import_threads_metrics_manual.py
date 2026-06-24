#!/usr/bin/env python3
"""Validate manual Threads metrics import dry-run path."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    cmd = [
        sys.executable,
        str(ROOT / "scripts/import_threads_metrics_manual.py"),
        "--result-id", "test_result",
        "--views", "100",
        "--likes", "5",
        "--comments", "1",
        "--follows", "0",
        "--profile-clicks", "2",
        "--line-adds", "0",
        "--memo", "dry-run test",
        "--dry-run",
    ]
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    checks = [("exit 0", proc.returncode == 0)]
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {}
    checks.extend([
        ("dry_run true", payload.get("dry_run") is True),
        ("metrics measured", payload.get("fields", {}).get("metrics_status") == "MEASURED"),
        ("manual memo", payload.get("fields", {}).get("manual_memo") == "dry-run test"),
    ])
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    if proc.stderr:
        print(proc.stderr.strip())
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
