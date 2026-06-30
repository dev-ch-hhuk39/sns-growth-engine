#!/usr/bin/env python3
"""Metrics dry-run without values must not fabricate MEASURED metrics."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    proc = subprocess.run(
        [sys.executable, "scripts/import_threads_metrics_manual.py", "--result-id", "sample_result", "--dry-run"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    payload = json.loads(proc.stdout or "{}")
    checks = [
        ("exit 0", proc.returncode == 0),
        ("dry run", payload.get("dry_run") is True),
        ("missing metrics listed", set(payload.get("missing_metrics", [])) == {"views", "likes", "comments", "follows", "profile_clicks", "line_adds"}),
        ("not measured", payload.get("would_mark_measured") is False),
        ("no fabricated views", "views" not in payload.get("fields", {})),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
