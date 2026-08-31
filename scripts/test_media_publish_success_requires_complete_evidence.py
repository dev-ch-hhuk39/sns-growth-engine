#!/usr/bin/env python3
from pathlib import Path

direct = Path(__file__).with_name("run_direct_reference_media_pipeline.py").read_text(encoding="utf-8")
clip = Path(__file__).with_name("run_media_production_pipeline.py").read_text(encoding="utf-8")
for source in (direct, clip):
    assert 'final_status == "POSTED"' in source or 'status == "POSTED"' in source
    assert 'metrics_collection_job_count", 0' in source
    assert 'post_result.get("warning", "")' in source
assert 'in {"POSTED", "POSTED_SAVE_FAILED"}' not in direct
assert 'publisher_complete = final_status == "POSTED"' in clip
assert '"POSTED_SAVE_FAILED",' in clip
assert 'post_status="POSTED" if externally_posted else final_status' in clip
print("PASS test_media_publish_success_requires_complete_evidence.py")
