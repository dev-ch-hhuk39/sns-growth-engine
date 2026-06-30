#!/usr/bin/env python3
from pathlib import Path
src=(Path(__file__).resolve().parents[1]/"scripts/run_growth_loop.py").read_text(encoding="utf-8")
checks=[("metrics browser", '"--source", "browser"' in src), ("metric post url option", "--metric-post-url" in src), ("source url option", "--source-url" in src), ("fetch real option", "--fetch-real" in src), ("collect source", "collect_source_posts.py" in src), ("scores real rows", "build_scores" in src), ("generates candidates", "build_generation_rows" in src), ("summary field", "real_collection_pipeline" in src)]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
