#!/usr/bin/env python3
import json
from pathlib import Path

import prepare_bounded_canary_publish as module

BATCH_ID = "fresh_remaining_eight_test"
MEDIA_TYPES = {
    "direct_video",
    "direct_carousel",
    "generated_clip",
}


def fake_inventory(
    _datasets,
    wave="all_12",
    batch_id="",
):
    assert wave == "all_12"

    if batch_id != BATCH_ID:
        return {
            "candidates": [],
            "canaries": [],
        }

    candidates = []
    canaries = []

    for account_id, canary_type in sorted(module.REMAINING_EIGHT):
        canary_id = (
            f"canary_{BATCH_ID}_{account_id}_{canary_type}"
        )
        candidate = {
            "account_id": account_id,
            "canary_type": canary_type,
            "canary_id": canary_id,
            "queue_id": f"q_{canary_id}",
            "batch_id": BATCH_ID,
            "public_post_text": "This is an approved test post.",
        }

        if canary_type in MEDIA_TYPES:
            candidate.update({
                "source_id": f"source_{canary_id}",
                "source_post_id": f"post_{canary_id}",
                "rights_status": "owned",
                "permission_status": "approved",
                "permission_evidence": "test",
            })

        if canary_type in {
            "direct_video",
            "generated_clip",
        }:
            candidate.update({
                "media_asset_id": f"asset_{canary_id}",
                "media_url": "https://example.invalid/video.mp4",
            })

        if canary_type == "generated_clip":
            candidate.update({
                "source_video_id": f"video_{canary_id}",
                "clip_candidate_id": f"clip_{canary_id}",
            })

        if canary_type == "direct_carousel":
            candidate.update({
                "media_asset_ids": [
                    f"asset_{canary_id}_1",
                    f"asset_{canary_id}_2",
                ],
                "media_urls": [
                    "https://example.invalid/1.png",
                    "https://example.invalid/2.png",
                ],
            })

        candidates.append(candidate)
        canaries.append({
            "account_id": account_id,
            "canary_type": canary_type,
            "canary_id": canary_id,
            "status": "READY_FOR_HUMAN_CANARY",
        })

    return {
        "candidates": candidates,
        "canaries": canaries,
    }


module.build_inventory = fake_inventory
module.final_public_post_validator = (
    lambda _text, _account_id: {"status": "PASS"}
)

queue = []
for account_id, canary_type in sorted(module.REMAINING_EIGHT):
    canary_id = f"canary_{BATCH_ID}_{account_id}_{canary_type}"
    row = {
        "account_id": account_id,
        "canary_id": canary_id,
        "queue_id": f"q_{canary_id}",
        "status": "WAITING_REVIEW",
    }

    if canary_type in {
        "direct_video",
        "generated_clip",
    }:
        row.update({
            "media_status": "ATTACHED",
            "media_url": "https://example.invalid/video.mp4",
        })

    if canary_type == "direct_carousel":
        row.update({
            "media_status": "ATTACHED",
            "media_urls_json": json.dumps([
                "https://example.invalid/1.png",
                "https://example.invalid/2.png",
            ]),
        })

    queue.append(row)

datasets = {"queue": queue}

plan = module.build_plan(
    datasets,
    "remaining_eight",
    BATCH_ID,
)

assert plan["status"] == "PASS", plan
assert len(plan["rows"]) == 8
assert {
    (row["account_id"], row["canary_type"])
    for row in plan["rows"]
} == module.REMAINING_EIGHT
assert all(
    row["status"] == "READY_TO_PROMOTE"
    for row in plan["rows"]
)

recovery = module.build_plan(
    datasets,
    "remaining_seven_recovery",
    BATCH_ID,
)

assert recovery["status"] == "PASS", recovery
assert len(recovery["rows"]) == 7
assert {
    (row["account_id"], row["canary_type"])
    for row in recovery["rows"]
} == module.REMAINING_SEVEN_RECOVERY
assert (
    "night_scout",
    "reference_text",
) not in module.REMAINING_SEVEN_RECOVERY

wrong_batch = module.build_plan(
    datasets,
    "remaining_eight",
    "fresh_wrong_batch",
)

assert wrong_batch["status"] == "BLOCKED"
assert all(
    "CANARY_BATCH_MISMATCH" in row["reasons"]
    for row in wrong_batch["rows"]
)

workflow = Path(
    ".github/workflows/bounded-canary-publish.yml"
).read_text(encoding="utf-8")

assert "remaining_eight" in workflow
assert "PUBLISH_APPROVED_REMAINING_EIGHT" in workflow
assert "expected=8" in workflow
assert "canary_batch_id" in workflow
assert "remaining_seven_recovery" in workflow
assert "PUBLISH_APPROVED_REMAINING_SEVEN_RECOVERY" in workflow
assert "expected=7" in workflow
assert 'mapfile -t queue_ids' in workflow
assert '--max-posts "${#queue_ids[@]}"' in workflow

publisher = Path(
    "src/publishers/threads_publisher.py"
).read_text(encoding="utf-8")

assert "_wait_for_media_container(child, access_token)" in publisher
assert "_safe_api_error" in publisher

processor = Path(
    "scripts/process_threads_queue.py"
).read_text(encoding="utf-8")

assert "get_all_records:" in processor
assert "_call_with_rate_limit_retry" in processor

print("PASS test_remaining_eight_publish_scope.py")
