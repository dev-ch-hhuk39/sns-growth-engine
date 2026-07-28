#!/usr/bin/env python3
"""Contract tests for generic, read-only source identity repair planning."""
from __future__ import annotations

from source_identity_repair_contract import build_identity_repair_plan, verify_identity_repair_outcome


def datasets(child_url: str, media_count: int) -> dict:
    return {
        "source_posts": [{"source_post_id": "parent-1", "target_account_id": "night_scout", "canonical_post_url": "https://threads.net/@a/post/1", "media_count": media_count}],
        "source_post_media": [{"source_post_media_id": "child-1", "source_post_id": "parent-1", "media_index": 0, "canonical_post_url": child_url, "content_hash": "hash-1"}],
    }


before = build_identity_repair_plan(
    datasets("https://threads.net/@a/post/wrong", 2),
    implementation_head="head", origin_main="main", planned_at="2026-07-28T00:00:00+00:00",
)
assert before["apply_allowed"] is False
assert before["approval_requirement"] == "HUMAN_APPROVAL_REQUIRED"
assert before["affected_row_count"] == 1
assert before["repair_plan_id"].startswith("source_identity_")
assert before["audit_records"][0]["old_hash"]
assert before["audit_records"][0]["new_hash"] == ""
assert before["audit_records"][0]["verifier_result"] == "PENDING_HUMAN_APPROVAL"

after = datasets("https://threads.net/@a/post/1", 1)
verified = verify_identity_repair_outcome(before, after, verified_at="2026-07-28T01:00:00+00:00")
assert verified["status"] == "PASS"
assert verified["audit_records"][0]["old_hash"] != verified["audit_records"][0]["new_hash"]
assert verified["audit_records"][0]["verifier_result"] == "PASS"

unresolved = verify_identity_repair_outcome(before, datasets("https://threads.net/@a/post/wrong", 2))
assert unresolved["status"] == "FAIL"
assert unresolved["audit_records"][0]["verifier_result"] == "FAIL_REMAINING_IDENTITY_DEFECT"

print("PASS test_source_identity_repair_contract.py")
