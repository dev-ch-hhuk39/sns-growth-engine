#!/usr/bin/env python3
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; SCRIPT=ROOT/"scripts/collect_threads_metrics.py"
spec=importlib.util.spec_from_file_location("m", SCRIPT); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
row={"result_id":"r1","account_id":"night_scout","platform":"threads","post_url":"u"}
s1=m.build_snapshot(row=row, source="manual", confidence="high", metrics={k:1 for k in m.METRIC_KEYS}, memo="a")
s2=m.build_snapshot(row=row, source="manual", confidence="high", metrics={k:2 for k in m.METRIC_KEYS}, memo="b")
checks=[("same result", s1["result_id"]==s2["result_id"]=="r1"), ("snapshot ids exist", s1["snapshot_id"].startswith("ms_r1_") and s2["snapshot_id"].startswith("ms_r1_")), ("measured", s1["metrics_status"]=="MEASURED")]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
