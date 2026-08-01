#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

import discover_approved_source_videos as d


SOURCE = {
    "source_id": "src_test_incremental",
    "source_name": "test source",
    "source_platform": "youtube",
    "source_type": "channel",
    "source_url": ("https://www.youtube.com/" "channel/UC0000000000000000000000"),
    "target_account_ids": ["night_scout"],
    "active": True,
    "media_autopilot_enabled": True,
    "rights_status": ("approved_creator_clip"),
    "permission_status": "approved",
    "permission_evidence_type": ("owner_attestation"),
    "permission_evidence_reference": ("global_owner_attestation_v1"),
    "permission_evidence_note": ("test owner evidence"),
    "permission_approved_by": "test",
}


config = d.load_config()

config.update(
    {
        "allowed_source_ids": [SOURCE["source_id"]],
        "allowed_source_types_for_discovery": ["channel"],
        "require_source_media_autopilot_enabled": (True),
        "initial_source_scan_limit": 30,
        "incremental_source_scan_limit": 12,
        "backfill_source_scan_limit": 30,
        "consecutive_existing_stop": 5,
        "backfill_overlap_items": 3,
        "min_unprocessed_source_inventory_per_account": 3,
        "max_new_videos_per_source_per_run": 3,
        "max_total_new_videos_per_run": 12,
    }
)


original_load_config = d.load_config
original_load_sources = d.load_sources

d.load_config = lambda: config
d.load_sources = lambda: [SOURCE]

try:
    planned = d.build_source_video_candidates(
        SOURCE,
        config,
        {
            "mode": "incremental",
            "start_position": 1,
            "scan_limit": 12,
        },
    )

    existing_incremental = [
        {
            **row,
            "post_status": "NOT_POSTED",
        }
        for row in planned[:5]
    ]

    for position in range(100, 107):
        row = d.build_source_video(
            SOURCE,
            index=position,
            discovery_status="DISCOVERED",
        )

        row["source_position"] = position
        row["post_status"] = "NOT_POSTED"

        existing_incremental.append(row)

    incremental = d.build_discovery_plan(
        "night_scout",
        existing_source_videos=(existing_incremental),
        discovery_state_rows=[],
        fetch_real=False,
    )

    result = incremental["source_results"][0]

    assert result["scan_mode"] == "incremental"
    assert result["start_position"] == 1
    assert result["scan_limit"] == 12
    assert result["new_video_count"] == 0
    assert result["duplicate_video_count"] == 5
    assert result["max_duplicate_streak"] == 5
    assert result["stop_reason"] == "consecutive_existing_stop"
    assert incremental["new_video_count"] == 0

    existing_backfill = []

    for position in range(1, 11):
        row = d.build_source_video(
            SOURCE,
            index=position,
            discovery_status="DISCOVERED",
        )

        row["source_position"] = position
        row["post_status"] = "POSTED"

        existing_backfill.append(row)

    state_rows = [
        {
            "state_id": ("src_test_incremental:" "night_scout:video"),
            "source_id": "src_test_incremental",
            "account_id": "night_scout",
            "item_type": "video",
            "backfill_cursor": 8,
            "last_scan_at": ("2026-08-01T00:00:00+00:00"),
            "updated_at": ("2026-08-01T00:00:00+00:00"),
        }
    ]

    backfill = d.build_discovery_plan(
        "night_scout",
        existing_source_videos=(existing_backfill),
        discovery_state_rows=state_rows,
        fetch_real=False,
    )

    backfill_result = backfill["source_results"][0]

    assert backfill_result["scan_mode"] == "backfill"
    assert backfill_result["start_position"] == 8
    assert backfill_result["scan_limit"] == 30
    assert backfill_result["duplicate_video_count"] == 3
    assert backfill_result["new_video_count"] == 3
    assert backfill_result["stop_reason"] == "per_source_new_limit_reached"

    assert [int(row["source_position"]) for row in backfill["new_videos"]] == [11, 12, 13]

    state_update = backfill["discovery_state_updates"][0]

    assert state_update["last_scan_mode"] == "backfill"
    assert state_update["backfill_cursor"] == 11
    assert state_update["last_new_count"] == 3

finally:
    d.load_config = original_load_config
    d.load_sources = original_load_sources


print("PASS " "test_discovery_plan_uses_" "incremental_policy.py")
