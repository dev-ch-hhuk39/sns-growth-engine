#!/usr/bin/env python3
"""Unavailable metrics must not prevent registry/PDCA aftercare from running."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / ".github" / "workflows" / "production-autopilot-aftercare.yml").read_text(encoding="utf-8")

metrics_pos = SOURCE.index("Apply metrics snapshots")
sync_pos = SOURCE.index("Sync source registry and Sheets schema")
checks = [
    ("metrics step is non-blocking", "set +e" in SOURCE[metrics_pos:sync_pos] and "metrics_snapshot_exit=$metrics_exit" in SOURCE[metrics_pos:sync_pos]),
    ("PDCA still follows metrics step", sync_pos > metrics_pos and "Apply PDCA candidate generation" in SOURCE[sync_pos:]),
    ("aftercare health reads operational counts", "--use-sheets" in SOURCE),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"{'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(1 if failed else 0)
