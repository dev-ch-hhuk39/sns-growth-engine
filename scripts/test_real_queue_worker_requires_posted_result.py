#!/usr/bin/env python3
from pathlib import Path

source = Path(__file__).with_name("process_threads_queue.py").read_text(encoding="utf-8")
assert "incomplete_real" in source
assert 'str(row.get("status", "")).upper() == "POSTED"' in source
assert "not args.dry_run" in source
assert "bad or blocked or incomplete_real" in source
assert 'metrics_collection_job_count", 0' in source
assert 'row.get("warning", "")' in source
print("PASS test_real_queue_worker_requires_posted_result.py")
