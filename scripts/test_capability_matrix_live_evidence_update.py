#!/usr/bin/env python3
import json
from pathlib import Path

from update_capability_matrix_from_evidence import build_update


ROOT = Path(__file__).resolve().parents[1]
status = json.loads((ROOT / "docs" / "capability-matrix-status.json").read_text())
account_id = "beauty_account"
result_id = "result_beauty_live_001"

datasets = {
    "posted_results": [
        {
            "account_id": account_id,
            "canary_id": "scheduled_beauty_original_text",
            "content_type": "original_text",
            "status": "POSTED",
            "post_url": "https://www.threads.com/@beauty/post/live001",
            "external_post_id": "live001",
            "verification_status": "READ_AFTER_WRITE_PASS",
            "result_id": result_id,
            "validator_status": "PASS",
            "posted_at": "2026-08-20T03:00:00Z",
        }
    ],
    "metric_snapshots": [
        {
            "account_id": account_id,
            "result_id": result_id,
            "snapshot_id": f"metric_{hours}",
            "collection_window_hours": hours,
            "metrics_status": "MEASURED",
            "collected_at": f"2026-08-{21 + offset:02d}T03:00:00Z",
        }
        for hours, offset in ((24, 0), (72, 2), (168, 6))
    ],
    "pdca_runs": [
        {
            "account_id": account_id,
            "run_id": "pdca_beauty_live_001",
            "metrics_status": "MEASURED_ONLY",
            "metric_input_refs_json": json.dumps([result_id]),
            "created_at": "2026-08-28T03:00:00Z",
        }
    ],
    "content_slot_runs": [
        {
            "account_id": account_id,
            "slot_run_id": f"slot_{index}",
            "event_name": "schedule",
            "workflow_run_id": f"workflow_{index}",
            "status": "POSTED" if index < 3 else "NO_POST",
            "actual_started_at": f"2026-08-{20 + index:02d}T03:00:00Z",
            "actual_posted_at": f"2026-08-{20 + index:02d}T03:01:00Z",
        }
        for index in range(3)
    ],
}

updated = build_update(
    status,
    datasets,
    {"scheduled_publish_enabled": True, "implementation_head": "live-head"},
)["updated_status"]["accounts"][account_id]

assert updated["original_text"]["state"] == "PASS"
assert updated["scheduled_publish_streak"]["state"] == "PASS"
assert len(updated["scheduled_publish_streak"]["evidence"]["schedule_runs"]) == 3
assert updated["metrics_24_72_168"]["state"] == "PASS"
assert set(updated["metrics_24_72_168"]["evidence"]["metric_windows"]) == {"24", "72", "168"}
assert updated["pdca_measured_feedback"]["state"] == "PASS"
assert updated["pdca_measured_feedback"]["evidence"]["metric_input_refs"] == [result_id]

# A manual dispatch is not a fourth schedule event and cannot create a streak by itself.
datasets["content_slot_runs"] = [
    {**row, "event_name": "workflow_dispatch"} for row in datasets["content_slot_runs"]
]
manual_only = build_update(
    status,
    datasets,
    {"scheduled_publish_enabled": True},
)["updated_status"]["accounts"][account_id]
assert manual_only["scheduled_publish_streak"]["state"] == "UNVERIFIED"

print("PASS test_capability_matrix_live_evidence_update.py")
