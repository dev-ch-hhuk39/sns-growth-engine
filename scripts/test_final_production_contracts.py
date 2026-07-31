#!/usr/bin/env python3
from final_production_contracts import activation_evidence, canary_id, is_active_permission, source_integrity_report

permission = {"account_id": "night_scout", "permission_status": "approved", "rights_status": "owned", "evidence_reference": "ledger", "revoked": "false", "allow_original_repost": "true", "allow_clip_repost": "true"}
assert is_active_permission(permission, account_id="night_scout", operation="direct")
assert is_active_permission(permission, account_id="night_scout", operation="clip")
assert not is_active_permission({**permission, "revoked": "true"}, account_id="night_scout", operation="direct")
integrity = source_integrity_report([{"source_post_id": "p", "canonical_post_url": "https://www.threads.com/@a/post/b"}], [{"source_post_id": "p", "canonical_post_url": "https://www.threads.com/@a/post/b", "media_index": "0"}])
assert integrity["status"] == "PASS"
assert source_integrity_report([], [])["status"] == "NO_EVIDENCE"
posted=[]; jobs=[]
for account in ("night_scout", "liver_manager"):
    for kind in ("original_text", "reference_text", "direct_image", "direct_video", "direct_carousel", "approved_source_clip"):
        cid=canary_id(account, kind); result_id=f"r_{cid}"
        posted.append({"canary_id": cid, "result_id": result_id, "status": "POSTED", "post_url": "https://www.threads.com/@a/post/b", "external_post_id": "1", "verification_status": "READ_AFTER_WRITE_PASS"})
        jobs.extend({"canary_id": cid, "window_hours": hours, "status": "SCHEDULED"} for hours in (24,72,168))
assert activation_evidence(posted, jobs)["status"] == "READY_FOR_ACTIVATION"
assert activation_evidence(posted[:-1], jobs)["status"] == "BLOCKED"

# Batch-specific canary IDs must satisfy the same canonical 12-slot contract.
fresh_posted=[]; fresh_jobs=[]
for account in ("night_scout", "liver_manager"):
    for kind in ("original_text", "reference_text", "direct_image", "direct_video", "direct_carousel", "approved_source_clip"):
        cid=f"canary_fresh_batch_001_{account}_{kind}"
        fresh_posted.append({"canary_id": cid, "account_id": account, "content_type": kind, "status": "POSTED", "post_url": "https://www.threads.com/@a/post/b", "external_post_id": "1", "verification_status": "READ_AFTER_WRITE_PASS"})
        fresh_jobs.extend({"canary_id": cid, "window_hours": hours, "status": "SCHEDULED"} for hours in (24,72,168))
fresh = activation_evidence(fresh_posted, fresh_jobs)
assert fresh["status"] == "READY_FOR_ACTIVATION"
assert fresh["verified_canary_count"] == 12
# Windows from a different batch may not complete a verified canary.
fresh_jobs = [row for row in fresh_jobs if row["canary_id"] != "canary_fresh_batch_001_night_scout_original_text"]
fresh_jobs.extend({"canary_id": "canary_other_batch_night_scout_original_text", "window_hours": hours, "status": "SCHEDULED"} for hours in (24,72,168))
assert activation_evidence(fresh_posted, fresh_jobs)["status"] == "BLOCKED"

print("PASS test_final_production_contracts.py")
