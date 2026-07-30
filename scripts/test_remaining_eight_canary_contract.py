#!/usr/bin/env python3
from copy import deepcopy

from prepare_remaining_eight_canaries import (
    ACCOUNTS,
    MEDIA_KINDS,
    REMAINING_TYPES,
    _contract,
    _generation_history,
)


def candidate(
    account: str,
    kind: str,
    index: int,
) -> dict:
    row = {
        "account_id": account,
        "content_type": kind,
        "canary_id": f"canary_fresh_test_{account}_{kind}",
        "batch_id": "fresh_remaining_eight_test",
        "public_post_text": (
            f"{account}向けの{kind}投稿本文です。"
        ),
        "content_hash": f"text-hash-{account}-{kind}",
        "primary_topic": f"topic_{index}",
        "structure_variant": str(index),
        "quality_gate_version": "generation_quality_v3",
        "feature_schema_version": "post_features_v1",
        "media_files": [],
        "media_content_hashes": [],
        "quality": {
            "status": "PASS",
            "batch_diversity_status": "PASS",
            "topic_coherence_status": "PASS",
        },
    }

    if kind in MEDIA_KINDS:
        row["alignment"] = {
            "alignment_status": "PASS",
            "main_claim_coverage": 1,
            "unsupported_claim_count": 0,
            "visual_topic_match": True,
            "visual_cta_match": True,
        }

        if kind == "direct_carousel":
            row["media_files"] = [
                f"/tmp/{account}-{kind}-{number}.png"
                for number in range(4)
            ]
            row["media_content_hashes"] = [
                f"media-hash-{account}-{kind}-{number}"
                for number in range(4)
            ]
        else:
            row["media_files"] = [
                f"/tmp/{account}-{kind}.mp4"
            ]
            row["media_content_hashes"] = [
                f"media-hash-{account}-{kind}"
            ]

    return row


rows = [
    candidate(account, kind, index)
    for account in ACCOUNTS
    for index, kind in enumerate(
        REMAINING_TYPES,
        start=1,
    )
]

result = _contract(
    "fresh_remaining_eight_test",
    rows,
)
assert result["status"] == "PASS", result
assert result["actual_candidate_count"] == 8

mixed = deepcopy(rows)
mixed[0]["batch_id"] = "other_batch"
assert _contract(
    "fresh_remaining_eight_test",
    mixed,
)["status"] == "BLOCKED"

duplicate_topic = deepcopy(rows)
account_rows = [
    row
    for row in duplicate_topic
    if row["account_id"] == "night_scout"
]
account_rows[1]["primary_topic"] = (
    account_rows[0]["primary_topic"]
)
assert _contract(
    "fresh_remaining_eight_test",
    duplicate_topic,
)["status"] == "BLOCKED"

missing = rows[:-1]
assert _contract(
    "fresh_remaining_eight_test",
    missing,
)["status"] == "BLOCKED"

wrong_video = deepcopy(rows)
video = next(
    row
    for row in wrong_video
    if row["content_type"] == "direct_video"
)
video["media_files"] = ["/tmp/not-video.png"]
assert _contract(
    "fresh_remaining_eight_test",
    wrong_video,
)["status"] == "BLOCKED"

history = _generation_history(
    "night_scout",
    [
        {
            "account_id": "night_scout",
            "posted_text": "posted text",
        },
    ],
    [
        {
            "account_id": "night_scout",
            "status": "WAITING_REVIEW",
            "public_post_text": "pending text",
        },
        {
            "account_id": "night_scout",
            "status": "READY",
            "public_post_text": "posted text",
        },
        {
            "account_id": "night_scout",
            "status": "SUPERSEDED_QUALITY",
            "public_post_text": "excluded text",
        },
        {
            "account_id": "liver_manager",
            "status": "WAITING_REVIEW",
            "public_post_text": "other account text",
        },
    ],
)

assert history == [
    "posted text",
    "pending text",
], history

print("PASS test_remaining_eight_canary_contract.py")
