#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from source_discovery_policy import (  # noqa: E402
    build_failed_state_update,
    build_state_update,
    latest_state,
    plan_source_scan,
    select_unique_candidates,
)


CONFIG = {
    "initial_source_scan_limit": 30,
    "incremental_source_scan_limit": 12,
    "backfill_source_scan_limit": 30,
    "consecutive_existing_stop": 5,
    "backfill_overlap_items": 3,
    "min_unprocessed_source_inventory_per_account": 3,
    "max_new_videos_per_source_per_run": 3,
    "max_total_new_videos_per_run": 12,
}


def duplicate_by_id(
    candidate: dict,
    existing: list[dict],
) -> bool:
    candidate_id = str(candidate.get("video_id", ""))

    return any(str(row.get("video_id", "")) == candidate_id for row in existing)


initial = plan_source_scan(
    source_id="src_1",
    account_id="night_scout",
    item_type="video",
    existing_rows=[],
    state_rows=[],
    config=CONFIG,
)

assert initial["mode"] == "initial"
assert initial["start_position"] == 1
assert initial["scan_limit"] == 30


existing_available = [
    {
        "source_id": "src_1",
        "account_id": "night_scout",
        "video_id": f"existing_{index}",
        "source_position": index,
        "post_status": "NOT_POSTED",
    }
    for index in range(1, 6)
]

incremental = plan_source_scan(
    source_id="src_1",
    account_id="night_scout",
    item_type="video",
    existing_rows=existing_available,
    state_rows=[],
    config=CONFIG,
)

assert incremental["mode"] == "incremental"
assert incremental["scan_limit"] == 12

incremental_candidates = [
    {
        "video_id": f"existing_{index}",
        "source_position": index,
    }
    for index in range(1, 6)
] + [
    {
        "video_id": "new_after_duplicates",
        "source_position": 6,
    }
]

incremental_selection = select_unique_candidates(
    candidates=incremental_candidates,
    existing_rows=existing_available,
    selected_this_run=[],
    duplicate_checker=duplicate_by_id,
    scan_plan=incremental,
)

assert incremental_selection["new_count"] == 0
assert incremental_selection["duplicate_count"] == 5
assert incremental_selection["stop_reason"] == "consecutive_existing_stop"


existing_low_inventory = [
    {
        "source_id": "src_1",
        "account_id": "night_scout",
        "video_id": f"old_{index}",
        "source_position": index,
        "post_status": "POSTED",
    }
    for index in range(1, 11)
]

state_rows = [
    {
        "state_id": ("src_1:night_scout:video"),
        "source_id": "src_1",
        "account_id": "night_scout",
        "item_type": "video",
        "backfill_cursor": 8,
        "updated_at": ("2026-07-31T00:00:00+00:00"),
    },
    {
        "state_id": ("src_1:night_scout:video"),
        "source_id": "src_1",
        "account_id": "night_scout",
        "item_type": "video",
        "backfill_cursor": 11,
        "updated_at": ("2026-08-01T00:00:00+00:00"),
    },
]

assert (
    latest_state(
        state_rows,
        source_id="src_1",
        account_id="night_scout",
        item_type="video",
    )["backfill_cursor"]
    == 11
)

backfill = plan_source_scan(
    source_id="src_1",
    account_id="night_scout",
    item_type="video",
    existing_rows=existing_low_inventory,
    state_rows=state_rows,
    config=CONFIG,
)

assert backfill["mode"] == "backfill"
assert backfill["start_position"] == 11
assert backfill["scan_limit"] == 30

backfill_candidates = [
    {
        "video_id": f"old_{index}",
        "source_position": index + 10,
    }
    for index in range(1, 6)
] + [
    {
        "video_id": "new_backfill_video",
        "source_position": 16,
    }
]

backfill_selection = select_unique_candidates(
    candidates=backfill_candidates,
    existing_rows=existing_low_inventory,
    selected_this_run=[],
    duplicate_checker=duplicate_by_id,
    scan_plan=backfill,
)

assert backfill_selection["new_count"] == 1
assert backfill_selection["selected"][0]["video_id"] == "new_backfill_video"
assert backfill_selection["stop_reason"] == "scan_exhausted"

state_update = build_state_update(
    scan_plan=backfill,
    selection=backfill_selection,
    latest_seen_item_id=("new_backfill_video"),
    platform="youtube",
)

assert state_update["backfill_cursor"] == 14
assert state_update["last_scan_mode"] == "backfill"
assert state_update["last_new_count"] == 1
assert state_update["consecutive_no_new_runs"] == 0

no_new_update = build_state_update(
    scan_plan={
        **backfill,
        "previous_state": state_update,
    },
    selection={
        "new_count": 0,
        "duplicate_count": 6,
        "max_scanned_position": 43,
    },
    platform="youtube",
)

assert no_new_update["backfill_cursor"] == 41
assert no_new_update["consecutive_no_new_runs"] == 1

# Both a completed and failed backfill return to latest before resuming history.
failed_update = build_failed_state_update(scan_plan={**backfill, "previous_state": state_update},
                                        platform="youtube")
assert failed_update["last_scan_mode"] == "backfill_failed"
assert failed_update["backfill_cursor"] == state_update["backfill_cursor"]
assert failed_update["last_scanned_position"] == state_update["last_scanned_position"]
assert failed_update["latest_seen_item_id"] == state_update["latest_seen_item_id"]
assert failed_update["last_new_count"] == 0
assert failed_update["last_duplicate_count"] == 0
for previous in (state_update, failed_update):
    poll = plan_source_scan(source_id="src_1", account_id="night_scout", item_type="video",
                            existing_rows=existing_low_inventory, state_rows=[previous], config=CONFIG)
    assert poll["mode"] == "incremental"
    assert poll["start_position"] == 1
    assert poll["scan_limit"] == CONFIG["incremental_source_scan_limit"]
    polled_state = build_state_update(scan_plan=poll, selection={"max_scanned_position": 12})
    assert polled_state["backfill_cursor"] == previous["backfill_cursor"]
    resume = plan_source_scan(source_id="src_1", account_id="night_scout", item_type="video",
                              existing_rows=existing_low_inventory, state_rows=[polled_state], config=CONFIG)
    assert resume["mode"] == "backfill"
    assert resume["start_position"] == previous["backfill_cursor"]
    assert resume["scan_limit"] == CONFIG["backfill_source_scan_limit"]
    assert resume["max_total_new"] == CONFIG["max_total_new_videos_per_run"]
    assert resume["per_source_new_limit"] == CONFIG["max_new_videos_per_source_per_run"]

# Failed reads without a persisted cursor keep their requested position.
first_failed = build_failed_state_update(scan_plan=backfill, platform="threads")
assert first_failed["backfill_cursor"] == 11
assert first_failed["last_scanned_position"] == 0
# Other accounts cannot change this source's scan mode or history cursor.
foreign_state = {**failed_update, "state_id": "src_1:beauty_account:video"}
isolated = plan_source_scan(source_id="src_1", account_id="night_scout", item_type="video",
                            existing_rows=existing_low_inventory, state_rows=[foreign_state], config=CONFIG)
assert isolated["mode"] == "backfill"
assert isolated["start_position"] == 8

print("PASS " "test_incremental_source_discovery_policy.py")
