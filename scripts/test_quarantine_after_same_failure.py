#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.reliability import is_quarantined, register_failure

first = register_failure({"retry_count": "0"}, "caption_alignment_failed", now="2026-07-19T00:00:00+00:00")
second = register_failure(first, "caption_alignment_failed", now="2026-07-19T01:00:00+00:00")
different = register_failure(first, "network_timeout", now="2026-07-19T01:00:00+00:00")
checks = [
    ("first matching failure remains retryable", not is_quarantined(first)),
    ("second same failure is quarantined", is_quarantined(second) and second["same_failure_count"] == "2"),
    ("different failure resets same-reason count", not is_quarantined(different) and different["same_failure_count"] == "1"),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
failed = [name for name, ok in checks if not ok]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
