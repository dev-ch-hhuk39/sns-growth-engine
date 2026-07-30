#!/usr/bin/env python3
from scheduled_publish_activation_gate import _decision, evaluate
from final_production_contracts import canary_id

# No Sheets evidence remains fail-closed.
result = evaluate(use_sheets=False)
assert result["status"] == "BLOCKED"
assert result["would_post"] is False

posted=[]; jobs=[]
for account in ("night_scout", "liver_manager"):
    for kind in ("original_text", "reference_text", "direct_image", "direct_video", "direct_carousel", "generated_clip"):
        cid=f"canary_fresh_activation_{account}_{kind}"
        posted.append({"canary_id": cid, "account_id": account, "content_type": kind, "status": "POSTED", "post_url": "https://www.threads.com/@a/post/b", "external_post_id": "1", "verification_status": "READ_AFTER_WRITE_PASS"})
        jobs.extend({"canary_id": cid, "window_hours": hours, "status": "SCHEDULED"} for hours in (24,72,168))
config={"kill_switch": False, "production_publish_activation_approved": False, "scheduled_publish_enabled": False}
readiness=_decision(config, posted, jobs, evidence_source="FIXTURE", require_persisted_activation=False)
assert readiness["status"] == "ALLOW", readiness
runtime=_decision(config, posted, jobs, evidence_source="FIXTURE", require_persisted_activation=True)
assert runtime["status"] == "BLOCKED", runtime
config.update({"production_publish_activation_approved": True, "scheduled_publish_enabled": True})
assert _decision(config, posted, jobs, evidence_source="FIXTURE", require_persisted_activation=True)["status"] == "ALLOW"
print("PASS test_scheduled_publish_activation_gate.py")
