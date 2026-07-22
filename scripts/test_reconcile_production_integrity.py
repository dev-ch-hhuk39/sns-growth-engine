#!/usr/bin/env python3
from datetime import datetime, timezone

from reconcile_production_integrity import (
    plan_posted_annotations,
    plan_queue_duplicate_repairs,
    plan_stale_slot_run_recovery,
)

queue = [
    {"queue_id": "q1", "status": "READY"},
    {"queue_id": "q1", "status": "WAITING_REVIEW"},
    {"queue_id": "slot_fallback_20260717_night_scout_ns_1400_reference_1", "status": "READY"},
]
repairs = plan_queue_duplicate_repairs(queue, business_date_jst="20260719")
duplicate_repairs = [item for item in repairs if item["changes"].get("status") == "DUPLICATE_BLOCKED"]
stale_repairs = [item for item in repairs if item["changes"].get("blocked_reason") == "stale_slot_fallback_expired"]

posted = [
    {"result_id": "r1", "account_id": "liver_manager", "platform": "threads", "status": "POSTED",
     "posted_at": "2026-07-17", "posted_text": "same", "media_used": "true", "media_asset_id": "m1",
     "validator_status": "PASS", "alignment_status": "", "unsupported_claim_count": ""},
    {"result_id": "r2", "account_id": "liver_manager", "platform": "threads", "status": "POSTED",
     "posted_at": "2026-07-18", "posted_text": "same", "media_used": "true", "media_asset_id": "m2",
     "validator_status": "PASS", "alignment_status": "PASS", "unsupported_claim_count": "0"},
    {"result_id": "r3", "account_id": "night_scout", "platform": "threads", "status": "POSTED",
     "posted_at": "2026-07-18", "posted_text": "unique", "media_used": "false"},
]
annotations = plan_posted_annotations(posted)
by_id = {item["result_id"]: item for item in annotations}
slot_repairs = plan_stale_slot_run_recovery([
    {"slot_run_id": "expired", "status": "RUNNING", "lease_expires_at": "2026-07-20T00:00:00+00:00"},
    {"slot_run_id": "active", "status": "CLAIMED", "lease_expires_at": "2026-07-23T00:00:00+00:00"},
    {"slot_run_id": "posted", "status": "RUNNING", "lease_expires_at": "2026-07-20T00:00:00+00:00", "post_url": "https://www.threads.com/@a/post/b"},
], now=datetime(2026, 7, 22, tzinfo=timezone.utc))
checks = [
    ("one duplicate queue row repaired", len(duplicate_repairs) == 1),
    ("duplicate queue row retained under unique ID", duplicate_repairs[0]["changes"]["queue_id"].startswith("q1__duplicate_row_")),
    ("duplicate queue row blocked", duplicate_repairs[0]["changes"]["status"] == "DUPLICATE_BLOCKED"),
    ("stale fallback is expired", len(stale_repairs) == 1 and stale_repairs[0]["changes"]["status"] == "FAILED"),
    ("missing media evidence annotated", "HISTORICAL_MEDIA_EVIDENCE_MISSING" in by_id["r1"]["markers"]),
    ("later exact duplicate annotated", "HISTORICAL_DUPLICATE_RECORDED" in by_id["r2"]["markers"]),
    ("valid unique text row untouched", "r3" not in by_id),
    ("posted text is never changed", all("posted_text" not in item["changes"] for item in annotations)),
    ("expired slot is quarantined", len(slot_repairs) == 1 and slot_repairs[0]["changes"]["status"] == "RECOVERY_REQUIRED"),
    ("stale slot is not given a second claim", slot_repairs[0]["changes"]["claim_status"] == "EXPIRED"),
]
for label, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {label}")
print(f"PASS: {sum(ok for _, ok in checks)} / FAIL: {sum(not ok for _, ok in checks)}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
