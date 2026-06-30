#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=subprocess.run([sys.executable,"scripts/collect_source_posts.py","--platform","threads","--account-id","night_scout","--source-url","https://www.threads.com/@example","--dry-run","--fetch-real"],cwd=ROOT,text=True,capture_output=True)
d=json.loads(p.stdout)
row=d["rows"][0]
checks=[("plan", d["status"]=="PLAN_ONLY"), ("real fetch flag", d["real_fetch"] is True), ("selected", d["selected_count"]==1), ("no media", d["media_download"] is False), ("source_account_post row", "post_id" in row and "post_text" in row and row["source_platform"]=="threads")]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
