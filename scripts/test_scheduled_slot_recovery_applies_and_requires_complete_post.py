#!/usr/bin/env python3
from pathlib import Path

from backfill_missed_content_slots import _complete_post


ROOT = Path(__file__).resolve().parents[1]
workflow = (ROOT / ".github/workflows/content-slot-recovery.yml").read_text(encoding="utf-8")
runner = (ROOT / "scripts/backfill_missed_content_slots.py").read_text(encoding="utf-8")

assert "github.event_name == 'schedule' ||" in workflow
assert "--apply --confirm-backfill" in workflow
assert 'PUBLISH_ENABLED: "true"' in workflow
assert 'ALLOW_REAL_THREADS_POST: "true"' in workflow
assert 'ALLOW_REAL_X_POST: "false"' in workflow
assert "at most one slot per account" in workflow
assert "allow_media_slot_safe_text_fallback=True" in runner
assert '"OPERATIONAL_FAILURE"' in runner

complete = {
    "status": "POSTED",
    "post_result": {
        "result_id": "result_1",
        "external_post_id": "external_1",
        "post_url": "https://www.threads.com/@example/post/1",
        "metrics_collection_job_count": 3,
        "warning": "",
    },
}
assert _complete_post(complete)
assert not _complete_post({**complete, "status": "POSTED_SAVE_FAILED"})
assert not _complete_post({**complete, "post_result": {**complete["post_result"], "metrics_collection_job_count": 2}})

print("PASS test_scheduled_slot_recovery_applies_and_requires_complete_post.py")
