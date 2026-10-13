#!/usr/bin/env python3
"""Publisher delivery must read-after-write and never retry an ambiguous post."""
from publisher_delivery_contract import delivery_idempotency_key, retry_disposition, verify_posted_result_persistence


key = delivery_idempotency_key(account_id="night_scout", platform="threads", queue_id="q1", external_post_id="p1")
assert key == delivery_idempotency_key(account_id="night_scout", platform="threads", queue_id="q1", external_post_id="p1")
assert key != delivery_idempotency_key(account_id="night_scout", platform="threads", queue_id="q2", external_post_id="p1")

rows = [{"result_id": "r1", "queue_id": "q1", "account_id": "night_scout", "external_post_id": "p1", "status": "POSTED"}]
assert verify_posted_result_persistence(rows, result_id="r1", queue_id="q1", account_id="night_scout", external_post_id="p1")["status"] == "PASS"
assert verify_posted_result_persistence([], result_id="r1", queue_id="q1", account_id="night_scout", external_post_id="p1")["reason"] == "RESULT_NOT_VISIBLE_AFTER_WRITE"
assert verify_posted_result_persistence([{**rows[0], "account_id": "wrong"}], result_id="r1", queue_id="q1", account_id="night_scout", external_post_id="p1")["reason"] == "RESULT_IDENTITY_MISMATCH"

# A historical duplicate may appear after the first matching good row.
# Never use only the first match for a publish-success acknowledgement.
verify = lambda rr: verify_posted_result_persistence(
    rr, result_id="r1", queue_id="q1",
    account_id="night_scout", external_post_id="p1",
)
assert verify(rows + [{**rows[0], "status": "FAILED"}])["reason"] == "RESULT_IDENTITY_AMBIGUOUS"
assert verify(rows + [{**rows[0], "result_id": "r2"}])["reason"] == "POSTED_QUEUE_ID_AMBIGUOUS"
assert verify(rows + [{
    **rows[0], "result_id": "r2", "queue_id": "q2", "account_id": "liver_manager",
}])["reason"] == "EXTERNAL_POST_ID_AMBIGUOUS"
assert verify(rows + [{
    **rows[0], "result_id": "r2", "queue_id": "q2",
    "external_post_id": "p2",
}])["status"] == "PASS"

assert retry_disposition(publish_succeeded=True, persisted=False, api_outcome_known=True) == "DO_NOT_RETRY_MANUAL_RECOVERY"
assert retry_disposition(publish_succeeded=False, persisted=True, api_outcome_known=False) == "DO_NOT_RETRY_ALREADY_PERSISTED"
assert retry_disposition(publish_succeeded=False, persisted=False, api_outcome_known=False) == "RETRY_SAFE_BEFORE_REMOTE_ACCEPTANCE"
print("PASS test_publisher_delivery_contract.py")
