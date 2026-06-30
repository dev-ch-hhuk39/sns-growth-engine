#!/usr/bin/env python3
from pathlib import Path
src=(Path(__file__).resolve().parents[1]/"scripts/collect_threads_metrics.py").read_text(encoding="utf-8")
checks=[("none used", "{k: None for k in METRIC_KEYS}" in src), ("not zero default", "0 for k in METRIC_KEYS" not in src), ("updates posted", "_update_posted_result" in src), ("unavailable allowed", "UNAVAILABLE" in src)]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
