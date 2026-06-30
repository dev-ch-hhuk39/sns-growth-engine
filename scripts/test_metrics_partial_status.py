#!/usr/bin/env python3
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; SCRIPT=ROOT/"scripts/collect_threads_metrics.py"
spec=importlib.util.spec_from_file_location("m", SCRIPT); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
metrics={k:None for k in m.METRIC_KEYS}; metrics["likes"]=0
s=m.build_snapshot(row={"result_id":"r1"}, source="browser", confidence="low", metrics=metrics, memo="")
checks=[("partial", s["metrics_status"]=="PARTIAL"), ("zero preserved", s["likes"]==0), ("unknown null", s["views"] is None)]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
