#!/usr/bin/env python3
"""Operational metrics/PDCA failures must fail production aftercare."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / ".github" / "workflows" / "production-autopilot-aftercare.yml").read_text(encoding="utf-8")

metrics_pos = SOURCE.index("Apply metrics snapshots")
sync_pos = SOURCE.index("Sync source registry and Sheets schema")
checks = [
    ("metrics failure is not swallowed", "set +e" not in SOURCE[metrics_pos:sync_pos] and "exit 0" not in SOURCE[metrics_pos:sync_pos]),
    ("PDCA still follows successful metrics", sync_pos > metrics_pos and "Maintain next 24h READY inventory from measured PDCA" in SOURCE[sync_pos:]),
    ("all managed accounts receive PDCA", "--account-id all" in SOURCE and "beauty_account_pdca_route=dedicated_beauty_generation" in SOURCE),
    ("PDCA failure is operational", "one or more measured PDCA generations failed" in SOURCE),
    ("aftercare health reads operational counts", "--use-sheets" in SOURCE),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"{'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(1 if failed else 0)
