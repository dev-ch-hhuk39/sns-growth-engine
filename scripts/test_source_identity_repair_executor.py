#!/usr/bin/env python3
"""Executor must be preconditioned, bounded, and rollback-capable."""
from source_identity_repair_contract import build_identity_repair_plan
from source_identity_repair_executor import apply_plan_in_memory, production_apply_allowed, validate_preconditions
from pathlib import Path


def snapshot(child_url="https://threads.net/@a/post/wrong", media_count=2):
    return {"source_posts": [{"source_post_id": "p1", "target_account_id": "night_scout", "canonical_post_url": "https://threads.net/@a/post/1", "media_count": media_count}], "source_post_media": [{"source_post_media_id": "m1", "source_post_id": "p1", "media_index": 0, "canonical_post_url": child_url, "content_hash": "x"}]}


plan = build_identity_repair_plan(snapshot(), implementation_head="head", origin_main="main", planned_at="2026-07-28T00:00:00Z")
assert validate_preconditions(plan, snapshot())["status"] == "PASS"
result = apply_plan_in_memory(plan, snapshot())
assert result["status"] == "APPLIED"
assert result["verification"]["status"] == "PASS"
assert result["audit_records"] and result["rollback_plan"]
changed = snapshot(child_url="https://threads.net/@a/post/changed")
assert apply_plan_in_memory(plan, changed)["status"] == "BLOCKED_PRECONDITION"
assert production_apply_allowed(apply=False, confirm=True) is False
assert production_apply_allowed(apply=True, confirm=False) is False
adapter = (Path(__file__).resolve().parent / "apply_source_identity_repairs.py").read_text(encoding="utf-8")
assert "ALLOW_SHEETS_IDENTITY_REPAIR" in adapter
assert "confirm-source-identity-repair" in adapter
assert "read_after_write" in adapter
print("PASS test_source_identity_repair_executor.py")
