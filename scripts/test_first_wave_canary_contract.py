#!/usr/bin/env python3
from pathlib import Path

from build_bounded_media_canary_plan import build_plan
from build_live_canary_inventory import _latest_complete_first_wave_batch, build_inventory
from prepare_first_wave_canaries import _contract, build_first_wave
from prepare_bounded_canary_publish import _field_update, build_plan as build_publish_plan
from media_post_validator import validate_media_post


def check(condition: bool, name: str) -> None:
    assert condition, name


batch_id = "fresh_first_wave_contract_test"
first = build_first_wave([], [], batch_id=batch_id, output_dir=Path("/tmp/first-wave-contract-a"))
second = build_first_wave([], [], batch_id=batch_id, output_dir=Path("/tmp/first-wave-contract-b"))
check(first["status"] == "READY_FOR_FIRST_WAVE_APPLY", "first wave preparation passes")
check(first["contract"]["status"] == "PASS", "four-item contract passes")
check(len(first["candidates"]) == 4, "exactly four candidates")
check({row["batch_id"] for row in first["candidates"]} == {batch_id}, "one shared batch")
check(first["design_manifest_hash"] == second["design_manifest_hash"], "manifest is deterministic")
check(len({row["canary_id"] for row in first["candidates"]}) == 4, "canary ids are unique")

for account in ("night_scout", "liver_manager"):
    rows = [row for row in first["candidates"] if row["account_id"] == account]
    check({row["content_type"] for row in rows} == {"original_text", "direct_image"}, f"{account} exact types")
    check(len({row["primary_topic"] for row in rows}) == 2, f"{account} topics differ")
    check(len({str(row["structure_variant"]) for row in rows}) == 2, f"{account} structures differ")
    image = next(row for row in rows if row["content_type"] == "direct_image")
    check(image["alignment"]["alignment_status"] == "PASS", f"{account} image alignment")
    check(image["alignment"]["main_claim_coverage"] == 1.0, f"{account} image claims")
    check(image["alignment"]["visual_topic_match"] is True, f"{account} visual topic")
    check(image["alignment"]["visual_cta_match"] is True, f"{account} visual CTA")

# Tampering the same-account topic must fail closed.
tampered = [dict(row) for row in first["candidates"]]
night_rows = [row for row in tampered if row["account_id"] == "night_scout"]
night_rows[1]["primary_topic"] = night_rows[0]["primary_topic"]
check(_contract(batch_id, tampered)["status"] == "BLOCKED", "same topic fails closed")

# The bounded first-wave plan itself rejects mixed batches.
plan_candidates = []
for row in first["candidates"]:
    common = {
        "account_id": row["account_id"], "canary_type": row["content_type"], "canary_id": row["canary_id"],
        "batch_id": row["batch_id"], "public_post_text": row["public_post_text"], "queue_id": row["queue_id"],
        "persona_validator_status": "PASS", "final_public_post_validator_status": "PASS", "internal_leak_status": "PASS",
        "batch_diversity_status": "PASS", "topic_coherence_status": "PASS", "primary_topic": row["primary_topic"],
        "topic_confidence": 1.0, "structure_variant": row["structure_variant"], "hook_topic_match": True,
        "closing_topic_match": True, "shared_hook_detected": False, "shared_closing_detected": False,
        "quality_gate_version": "generation_quality_v3",
    }
    if row["content_type"] == "direct_image":
        common.update({
            "source_id": "system", "rights_status": "owned", "permission_status": "approved", "permission_evidence": "generated",
            "publisher_media_type": "IMAGE", "alignment_status": "PASS", "final_alignment_score": 1.0,
            "main_claim_coverage": 1.0, "unsupported_claim_count": 0, "source_copy_similarity": 0,
            "recent_post_similarity": 0, "feature_schema_version": "post_features_v1",
            "media_primary_topic": row["primary_topic"], "visual_topic": row["primary_topic"], "visual_topic_match": True,
            "visual_cta_match": True, "visual_plan_version": "visual_plan_v1", "visual_text_hash": row["visual_text_hash"],
            "claim_support_json": "[{\"verified\":true}]", "source_post_id": "sp", "media_asset_id": "ma",
            "media_url": "https://example.invalid/image.png",
        })
    plan_candidates.append(common)
plan = build_plan(plan_candidates, wave="first_wave")
check(plan["total_canaries"] == 4 and plan["ready_canaries"] == 4, "exact first-wave plan ready")
plan_candidates[0]["batch_id"] = "other_batch"
mixed = build_plan(plan_candidates, wave="first_wave")
check(mixed["same_batch_contract"] == "BLOCKED" and mixed["ready_canaries"] == 0, "mixed batch plan blocked")

# A newer partial batch must not displace the newest complete first-wave batch.
queue = [
    {"account_id": "night_scout", "content_type": "direct_image", "batch_id": "complete", "canary_id": "canary_fresh_complete_nsi", "created_at": "2026-07-30T00:00:00Z"},
    {"account_id": "night_scout", "generation_mode": "original_text", "batch_id": "complete", "canary_id": "canary_fresh_complete_nst", "created_at": "2026-07-30T00:00:00Z"},
    {"account_id": "liver_manager", "content_type": "direct_image", "batch_id": "complete", "canary_id": "canary_fresh_complete_lmi", "created_at": "2026-07-30T00:00:00Z"},
    {"account_id": "liver_manager", "generation_mode": "original_text", "batch_id": "complete", "canary_id": "canary_fresh_complete_lmt", "created_at": "2026-07-30T00:00:00Z"},
    {"account_id": "night_scout", "content_type": "direct_image", "batch_id": "newer_partial", "canary_id": "canary_fresh_partial", "created_at": "2026-07-31T00:00:00Z"},
]
check(_latest_complete_first_wave_batch(queue) == "complete", "latest complete batch wins")


# Live inventory must select and approve the exact same four-row batch.
quality_fields = {
    "batch_diversity_status": "PASS", "topic_coherence_status": "PASS",
    "topic_confidence": "1", "hook_topic_match": "True", "closing_topic_match": "True",
    "shared_hook_detected": "False", "shared_closing_detected": "False",
    "quality_gate_version": "generation_quality_v3",
}
media_fields = {
    "alignment_status": "PASS", "final_alignment_score": "1", "main_claim_coverage": "1",
    "unsupported_claim_count": "0", "source_copy_similarity": "0", "recent_post_similarity": "0",
    "feature_schema_version": "post_features_v1", "visual_topic_match": "True", "visual_cta_match": "True",
    "visual_plan_version": "visual_plan_v1", "visual_text_hash": "vh", "claim_support_json": "[{\"verified\":true}]",
}
datasets = {key: [] for key in ("queue", "source_posts", "source_post_media", "media_permissions", "source_videos", "video_clip_candidates", "media_assets")}
for account, text_topic, image_topic in (
    ("night_scout", "work_conditions", "performance_pressure"),
    ("liver_manager", "continuity", "agency_selection"),
):
    prepared_text = {
        row["content_type"]: row["public_post_text"]
        for row in first["candidates"]
        if row["account_id"] == account
    }
    datasets["queue"].append({
        "account_id": account, "target_account_id": account, "batch_id": batch_id,
        "canary_id": f"canary_fresh_{batch_id}_{account}_original_text", "queue_id": f"q_{account}_text",
        "status": "WAITING_REVIEW", "generation_mode": "original_text", "public_post_text": prepared_text["original_text"],
        "validator_status": "PASS", "account_fit_status": "PASS", "internal_leak_status": "PASS",
        "primary_topic": text_topic, "structure_variant": "1", **quality_fields,
    })
    source_id = f"{batch_id}_{account}_direct_image"
    parent_id = f"sp_{source_id}"
    asset_id = f"ma_{account}"
    media_url = f"https://example.invalid/{account}.png"
    datasets["queue"].append({
        "account_id": account, "target_account_id": account, "batch_id": batch_id,
        "canary_id": f"canary_fresh_{batch_id}_{account}_direct_image", "queue_id": f"q_{account}_image",
        "status": "WAITING_REVIEW", "generation_mode": "system_owned_media", "content_type": "direct_image",
        "public_post_text": prepared_text["direct_image"], "validator_status": "PASS", "account_fit_status": "PASS",
        "internal_leak_status": "PASS", "publisher_media_type": "IMAGE", "source_post_id": parent_id,
        "media_asset_id": asset_id, "media_url": media_url, "primary_topic": image_topic,
        "media_primary_topic": image_topic, "visual_topic": image_topic, "structure_variant": "2",
        **quality_fields, **media_fields,
    })
    datasets["source_posts"].append({"source_post_id": parent_id, "source_id": source_id, "target_account_id": account})
    datasets["media_permissions"].append({
        "source_id": source_id, "account_id": account, "rights_status": "owned", "permission_status": "approved",
        "evidence_reference": batch_id, "allow_original_repost": True, "revoked": False,
    })
    datasets["media_assets"].append({"media_id": asset_id, "storage_url": media_url})
live = build_inventory(datasets, wave="first_wave", batch_id=batch_id)
check(live["selected_batch_id"] == batch_id, "inventory preserves approved batch")
check(live["candidate_count"] == 4, "inventory exposes exact four candidates")
check(live["same_batch_contract"] == "PASS", "inventory same-batch contract")
check(live["ready_canaries"] == 4, "inventory 4/4 ready")

recovery = build_publish_plan(datasets, wave="first_wave_images")
check(recovery["status"] == "PASS", "remaining image recovery plan passes")
check(len(recovery["rows"]) == 2, "remaining image recovery is exactly two")
check(
    all(row["canary_type"] == "direct_image" for row in recovery["rows"]),
    "recovery contains images only",
)
check(
    all(row["updates"]["media_type"] == "image" for row in recovery["rows"]),
    "direct image is normalized to image",
)

generated_image = next(
    row
    for row in first["candidates"]
    if row["account_id"] == "night_scout" and row["content_type"] == "direct_image"
)
alignment = generated_image["alignment"]
validation = validate_media_post({
    "rights_status": "owned",
    "permission_status": "approved",
    "media_url": "https://example.invalid/image.png",
    "media_asset_id": "ma_test",
    "platform": "threads",
    "account_id": "night_scout",
    "media_type": "image",
    "content_type": "direct_image",
    "publisher_media_type": "IMAGE",
    "public_post_text": generated_image["public_post_text"],
    "media_origin": "system_generated_owned",
    "alignment_status": alignment["alignment_status"],
    "final_alignment_score": alignment["final_alignment_score"],
    "main_claim_coverage": alignment["main_claim_coverage"],
    "unsupported_claim_count": alignment["unsupported_claim_count"],
    "source_copy_similarity": 0,
    "recent_post_similarity": alignment["recent_post_similarity"],
})
check(validation["status"] == "PASS", "zero similarity image validator passes")

print("PASS test_first_wave_canary_contract.py")
