#!/usr/bin/env python3
from build_bounded_media_canary_plan import build_plan

empty = build_plan([])
assert empty["total_canaries"] == 12
assert all(row["status"] == "PENDING_EVIDENCE" for row in empty["canaries"])
candidate = {
    "account_id": "night_scout", "canary_type": "direct_image", "source_id": "s", "rights_status": "approved_creator_clip",
    "permission_status": "approved", "permission_evidence": "ledger row", "public_post_text": "読者向けの自然な投稿文です。",
    "source_post_id": "p", "media_asset_id": "m", "media_url": "https://example.invalid/image.jpg",
}
plan = build_plan([candidate])
row = next(row for row in plan["canaries"] if row["canary_id"] == "canary_night_scout_direct_image")
assert row["status"] == "READY_FOR_HUMAN_CANARY"
assert plan["would_fetch"] is False and plan["would_post"] is False
text_plan = build_plan([{"account_id": "liver_manager", "canary_type": "original_text", "public_post_text": "配信を始める前に不安を一つずつ整理すると続けやすいです。", "persona_validator_status": "PASS", "final_public_post_validator_status": "PASS"}])
assert next(row for row in text_plan["canaries"] if row["canary_id"] == "canary_liver_manager_original_text")["status"] == "READY_FOR_HUMAN_CANARY"
print("PASS test_bounded_media_canary_plan.py")
