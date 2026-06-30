#!/usr/bin/env python3
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; SCRIPT=ROOT/"scripts/collect_source_posts.py"
spec=importlib.util.spec_from_file_location("s", SCRIPT); s=importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
rows=[s.normalize_source({"source_id":"a","url":"https://www.threads.com/@x","source_platform":"threads","target_account_ids":["night_scout"]}), s.normalize_source({"source_id":"b","url":"https://www.threads.com/@x","source_platform":"threads","target_account_ids":["night_scout"]})]
urls={r["post_url"] for r in rows}
deduped, skipped=s.dedupe_rows(rows)
checks=[("same url visible", len(urls)==1), ("dedupe keeps one", len(deduped)==1), ("dedupe skips one", skipped==1), ("stable source post id", rows[0]["post_id"] == rows[1]["post_id"])]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
