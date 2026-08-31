#!/usr/bin/env python3
from run_scheduled_text_slot_pipeline import verified_publish_result

complete = {
    "status": "POSTED",
    "result_id": "result-1",
    "external_post_id": "post-1",
    "post_url": "https://www.threads.com/@example/post/one",
    "metrics_collection_job_count": 3,
    "warning": "",
}
assert verified_publish_result(0, complete)
assert not verified_publish_result(0, {"status": "NO_POST", "reason": "NO_READY_QUEUE"})
for missing in ("result_id", "external_post_id", "post_url"):
    payload = dict(complete)
    payload[missing] = ""
    assert not verified_publish_result(0, payload), missing
assert not verified_publish_result(1, complete)
missing_metrics = dict(complete)
missing_metrics["metrics_collection_job_count"] = 2
assert not verified_publish_result(0, missing_metrics)
warning = dict(complete)
warning["warning"] = "pdca_or_log_save_failed:RuntimeError"
assert not verified_publish_result(0, warning)
print("PASS test_scheduled_publish_requires_verified_post.py")
