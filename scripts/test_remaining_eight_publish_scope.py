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


def fake_inventory(_datasets, wave="all_12"):
    assert wave == "all_12"

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

print("PASS test_remaining_eight_publish_scope.py")
