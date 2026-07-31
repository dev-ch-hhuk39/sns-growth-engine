#!/usr/bin/env python3
import json
from update_capability_matrix_from_evidence import build_update

status={"accounts": {account: {kind: {"state":"UNVERIFIED", "evidence":{}} for kind in ("original_text","reference_text","direct_image","direct_video","direct_carousel","approved_source_clip","scheduled_publish","result_persistence","metrics","pdca","persona")} for account in ("night_scout","liver_manager")}}
posted=[{"account_id":"night_scout","canary_id":"canary_night_scout_original_text","status":"POSTED","post_url":"https://www.threads.com/@a/post/b","external_post_id":"1","verification_status":"PASS","result_id":"r","validator_status":"PASS"}]
result=build_update(status,{"posted_results":posted,"metrics_collection_jobs":[],"metric_snapshots":[],"pdca_runs":[],"content_slot_runs":[]},{"scheduled_publish_enabled":False})
rows=result["updated_status"]["accounts"]["night_scout"]
assert rows["original_text"]["state"] == "PASS"
assert rows["result_persistence"]["state"] == "PASS"
assert rows["metrics"]["state"] == "UNVERIFIED"
print("PASS test_capability_matrix_evidence_updater.py")
