#!/usr/bin/env python3
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; SCRIPT=ROOT/"scripts/collect_threads_metrics.py"
spec=importlib.util.spec_from_file_location("m", SCRIPT); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
from sheets_client import TAB_DEFINITIONS
metrics={k:None for k in m.METRIC_KEYS}; metrics["likes"]=3
s=m.build_snapshot(row={"result_id":"r1"}, source="browser", confidence="low", metrics=metrics, memo="partial", error_reason="public_html_partial")
checks=[("partial", s["metrics_status"]=="PARTIAL"), ("likes", s["likes"]==3), ("views null", s["views"] is None), ("error saved", s["error_reason"]=="public_html_partial"), ("metric_snapshots schema", "metric_snapshots" in TAB_DEFINITIONS and "error_reason" in TAB_DEFINITIONS["metric_snapshots"])]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
