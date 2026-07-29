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
    for kind in ("original_text", "reference_text", "direct_image", "direct_video", "direct_carousel", "generated_clip"):
        cid=canary_id(account, kind); result_id=f"r_{cid}"
        posted.append({"canary_id": cid, "result_id": result_id, "status": "POSTED", "post_url": "https://www.threads.com/@a/post/b", "external_post_id": "1", "verification_status": "READ_AFTER_WRITE_PASS"})
        jobs.extend({"canary_id": cid, "window_hours": hours, "status": "SCHEDULED"} for hours in (24,72,168))
assert activation_evidence(posted, jobs)["status"] == "READY_FOR_ACTIVATION"
assert activation_evidence(posted[:-1], jobs)["status"] == "BLOCKED"
print("PASS test_final_production_contracts.py")
