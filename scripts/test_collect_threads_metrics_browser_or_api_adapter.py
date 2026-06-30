#!/usr/bin/env python3
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; SCRIPT=ROOT/"scripts/collect_threads_metrics.py"
spec=importlib.util.spec_from_file_location("m", SCRIPT); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
row={"result_id":"r1","post_url":""}
metrics, confidence, error = m.collect_public_threads_metrics(row, "browser")
checks=[("keys", set(metrics)==set(m.METRIC_KEYS)), ("unknown nulls", all(v is None for v in metrics.values())), ("error", bool(error)), ("confidence none", confidence=="none")]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
