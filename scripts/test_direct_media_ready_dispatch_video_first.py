#!/usr/bin/env python3
"""READY direct-media dispatch prefers video over an earlier image."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

import run_direct_reference_media_pipeline as pipeline

target_date = pipeline.business_date()

image_queue = {
    "queue_id": "queue_image",
    "account_id": "night_scout",
    "platform": "threads",
    "priority": "1",
    "status": "READY",
    "human_review_decision": "OK",
    "generation_mode": "direct_reference_media",
    "slot_id": "ns_1800_direct_media",
    "business_date_jst": target_date,
    "media_type": "image",
    "created_at": "2026-08-01T00:00:00+00:00",
}

video_queue = {
    "queue_id": "queue_video",
    "account_id": "night_scout",
    "platform": "threads",
    "priority": "99",
    "status": "READY",
    "human_review_decision": "OK",
    "generation_mode": "direct_reference_media",
    "slot_id": "ns_1800_direct_media",
    "business_date_jst": target_date,
    "media_type": "video",
    "created_at": "2026-08-01T01:00:00+00:00",
}

original_records = pipeline._records
original_existing = pipeline.existing_slot_status
original_process = pipeline.process_one
original_load = pipeline._load

try:
    pipeline._records = (
        lambda _client, logical: (
            [image_queue, video_queue]
            if logical == "queue"
            else []
        )
    )

    pipeline.existing_slot_status = (
        lambda *_args, **_kwargs: ""
    )

    pipeline.process_one = (
        lambda *_args, **_kwargs: {
            "status": "DRY_RUN",
            "would_post": False,
        }
    )

    pipeline._load = (
        lambda _path: {
            "direct_media_preferred_type": "video",
        }
    )

    result = pipeline.dispatch_ready(
        object(),
        "night_scout",
        "ns_1800_direct_media",
        dry_run=True,
    )

finally:
    pipeline._records = original_records
    pipeline.existing_slot_status = original_existing
    pipeline.process_one = original_process
    pipeline._load = original_load

assert result.get(
    "selected_queue_id"
) == "queue_video", result

assert result.get(
    "would_post"
) is False, result

print(
    "PASS "
    "test_direct_media_ready_dispatch_video_first.py"
)
