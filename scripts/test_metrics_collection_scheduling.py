#!/usr/bin/env python3
from datetime import datetime, timezone
from metrics_collection_schedule import build_metric_collection_jobs, due_jobs
from collect_threads_metrics import classify_collection_status

posted = [{"result_id": "r1", "account_id": "night_scout", "platform": "threads", "post_url": "https://www.threads.com/@a/post/x", "posted_at": "2026-07-20T00:00:00+00:00"}]
now = datetime(2026, 7, 24, tzinfo=timezone.utc)
jobs = build_metric_collection_jobs(posted, [], now=now)
assert [j["window_hours"] for j in jobs] == [24, 72, 168]
assert [j["status"] for j in jobs] == ["DUE", "DUE", "SCHEDULED"]
assert len(build_metric_collection_jobs(posted, jobs, now=now)) == 0
assert len(due_jobs(jobs, now=now)) == 2
empty = {"views": None, "likes": None, "comments": None, "reposts": None, "quotes": None, "profile_clicks": None, "follows": None, "line_adds": None}
assert classify_collection_status(metrics=empty, error_reason="HTTPError: 404") == "POST_NOT_FOUND"
assert classify_collection_status(metrics=empty, error_reason="HTTPError: 403") == "AUTH_ERROR"
assert classify_collection_status(metrics=empty, error_reason="public_html_no_metrics") == "NOT_AVAILABLE"
assert classify_collection_status(metrics={**empty, "likes": 0}, error_reason="") == "PARTIAL"
print("PASS test_metrics_collection_scheduling.py")
