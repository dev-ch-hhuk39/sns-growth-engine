#!/usr/bin/env python3
"""Metrics import supports dry-run after the first real post."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/import_threads_metrics_manual.py",
            "--result-id",
            "threads_first_post_test",
            "--views",
            "0",
            "--likes",
            "0",
            "--comments",
            "0",
            "--follows",
            "0",
            "--profile-clicks",
            "0",
            "--line-adds",
            "0",
            "--memo",
            "first post dry-run",
            "--dry-run",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    payload = json.loads(proc.stdout or "{}")
    checks = [
        ("exit 0", proc.returncode == 0),
        ("dry run true", payload.get("dry_run") is True),
        ("zero metrics accepted", payload.get("fields", {}).get("views") == 0),
        ("measured status planned", payload.get("fields", {}).get("metrics_status") == "MEASURED"),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
