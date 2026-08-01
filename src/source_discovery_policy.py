"""Pure policy for incremental account/channel discovery.

This module performs no network access and no persistence. It decides:

- initial, incremental, or backfill scan mode
- scan start and bounded scan size
- when incremental discovery may stop after consecutive duplicates
- when inventory shortage requires historical backfill
- the next append-only discovery state row
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable


Row = dict[str, Any]
DuplicateChecker = Callable[[Row, list[Row]], bool]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _positive_int(
    value: Any,
    default: int,
    *,
    minimum: int = 1,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default

    return max(minimum, parsed)


@dataclass(frozen=True)
class DiscoveryPolicy:
    initial_scan_limit: int
    incremental_scan_limit: int
    backfill_scan_limit: int
    consecutive_existing_stop: int
    backfill_overlap_items: int
    min_unprocessed_inventory_per_account: int
    per_source_new_limit: int
    max_total_new: int

    @classmethod
    def from_config(
        cls,
        config: Row,
    ) -> "DiscoveryPolicy":
        return cls(
            initial_scan_limit=_positive_int(
                config.get("initial_source_scan_limit"),
                30,
            ),
            incremental_scan_limit=_positive_int(
                config.get("incremental_source_scan_limit"),
                config.get(
                    "max_videos_per_source_scan",
                    12,
                ),
            ),
            backfill_scan_limit=_positive_int(
                config.get("backfill_source_scan_limit"),
                30,
            ),
            consecutive_existing_stop=_positive_int(
                config.get("consecutive_existing_stop"),
                5,
            ),
            backfill_overlap_items=_positive_int(
                config.get("backfill_overlap_items"),
                3,
            ),
            min_unprocessed_inventory_per_account=(
                _positive_int(
                    config.get("min_unprocessed_source_inventory_per_account"),
                    12,
                    minimum=0,
                )
            ),
            per_source_new_limit=_positive_int(
                config.get("max_new_videos_per_source_per_run"),
                3,
            ),
            max_total_new=_positive_int(
                config.get("max_total_new_videos_per_run"),
                12,
            ),
        )


def state_id(
    source_id: str,
    account_id: str,
    item_type: str,
) -> str:
    return f"{source_id}:{account_id}:{item_type}"


def latest_state(
    rows: list[Row],
    *,
    source_id: str,
    account_id: str,
    item_type: str,
) -> Row:
    expected = state_id(
        source_id,
        account_id,
        item_type,
    )

    matching = [row for row in rows if str(row.get("state_id", "")) == expected]

    return max(
        matching,
        key=lambda row: (
            str(row.get("updated_at", "")),
            str(row.get("last_scan_at", "")),
        ),
        default={},
    )


def row_is_available(
    row: Row,
) -> bool:
    terminal = {
        "POSTED",
        "SKIPPED",
        "BLOCKED",
        "QUARANTINED",
        "INVALID",
    }

    statuses = {
        str(row.get("post_status", "")).upper(),
        str(row.get("processing_status", "")).upper(),
        str(row.get("collection_status", "")).upper(),
        str(row.get("discovery_status", "")).upper(),
    }

    if terminal & statuses:
        return False

    if str(row.get("skip_reason", "")).strip():
        return False

    if str(row.get("quarantined_at", "")).strip():
        return False

    return True


def available_inventory_count(
    rows: list[Row],
    *,
    account_id: str,
) -> int:
    return sum(
        1
        for row in rows
        if str(
            row.get(
                "account_id",
                row.get(
                    "target_account_id",
                    "",
                ),
            )
        )
        == account_id
        and row_is_available(row)
    )


def _position(
    row: Row,
    fallback: int,
) -> int:
    for key in (
        "source_position",
        "playlist_index",
        "scan_position",
    ):
        value = row.get(key)

        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue

        if parsed > 0:
            return parsed

    return fallback


def plan_source_scan(
    *,
    source_id: str,
    account_id: str,
    item_type: str,
    existing_rows: list[Row],
    state_rows: list[Row],
    config: Row,
) -> Row:
    policy = DiscoveryPolicy.from_config(config)

    source_rows = [row for row in existing_rows if str(row.get("source_id", "")) == source_id]

    inventory_count = available_inventory_count(
        existing_rows,
        account_id=account_id,
    )

    previous = latest_state(
        state_rows,
        source_id=source_id,
        account_id=account_id,
        item_type=item_type,
    )

    if not source_rows:
        mode = "initial"
        start_position = 1
        scan_limit = policy.initial_scan_limit
    elif inventory_count < policy.min_unprocessed_inventory_per_account:
        mode = "backfill"

        saved_cursor = previous.get("backfill_cursor")

        try:
            start_position = int(saved_cursor)
        except (TypeError, ValueError):
            max_existing_position = max(
                (
                    _position(row, index)
                    for index, row in enumerate(
                        source_rows,
                        start=1,
                    )
                ),
                default=1,
            )

            start_position = max(
                1,
                max_existing_position + 1 - policy.backfill_overlap_items,
            )

        scan_limit = policy.backfill_scan_limit
    else:
        mode = "incremental"
        start_position = 1
        scan_limit = policy.incremental_scan_limit

    return {
        "source_id": source_id,
        "account_id": account_id,
        "item_type": item_type,
        "mode": mode,
        "start_position": max(
            1,
            start_position,
        ),
        "scan_limit": scan_limit,
        "inventory_count": inventory_count,
        "inventory_target": (policy.min_unprocessed_inventory_per_account),
        "per_source_new_limit": (policy.per_source_new_limit),
        "max_total_new": (policy.max_total_new),
        "consecutive_existing_stop": (policy.consecutive_existing_stop),
        "backfill_overlap_items": (policy.backfill_overlap_items),
        "previous_state": previous,
    }


def select_unique_candidates(
    *,
    candidates: list[Row],
    existing_rows: list[Row],
    selected_this_run: list[Row],
    duplicate_checker: DuplicateChecker,
    scan_plan: Row,
) -> Row:
    selected: list[Row] = []
    duplicate_count = 0
    duplicate_streak = 0
    max_duplicate_streak = 0
    scanned_count = 0
    max_scanned_position = (
        int(
            scan_plan.get(
                "start_position",
                1,
            )
        )
        - 1
    )
    stop_reason = "scan_exhausted"

    per_source_limit = int(scan_plan["per_source_new_limit"])
    max_total = int(scan_plan["max_total_new"])
    streak_limit = int(scan_plan["consecutive_existing_stop"])
    mode = str(scan_plan.get("mode", ""))

    for offset, candidate in enumerate(
        candidates,
        start=0,
    ):
        scanned_count += 1

        position = _position(
            candidate,
            int(
                scan_plan.get(
                    "start_position",
                    1,
                )
            )
            + offset,
        )

        max_scanned_position = max(
            max_scanned_position,
            position,
        )

        comparison_rows = existing_rows + selected_this_run + selected

        if duplicate_checker(
            candidate,
            comparison_rows,
        ):
            duplicate_count += 1
            duplicate_streak += 1
            max_duplicate_streak = max(
                max_duplicate_streak,
                duplicate_streak,
            )

            if mode == "incremental" and duplicate_streak >= streak_limit:
                stop_reason = "consecutive_existing_stop"
                break

            continue

        duplicate_streak = 0

        if len(selected_this_run) + len(selected) >= max_total:
            stop_reason = "max_total_new_reached"
            break

        selected.append(candidate)

        if len(selected) >= per_source_limit:
            stop_reason = "per_source_new_limit_reached"
            break

    return {
        "selected": selected,
        "new_count": len(selected),
        "duplicate_count": duplicate_count,
        "scanned_count": scanned_count,
        "max_duplicate_streak": (max_duplicate_streak),
        "max_scanned_position": (max_scanned_position),
        "stop_reason": stop_reason,
    }


def build_state_update(
    *,
    scan_plan: Row,
    selection: Row,
    latest_seen_item_id: str = "",
    latest_seen_published_at: str = "",
    platform: str = "",
) -> Row:
    previous = dict(
        scan_plan.get(
            "previous_state",
            {},
        )
    )

    new_count = int(selection.get("new_count", 0))

    previous_no_new = int(
        previous.get(
            "consecutive_no_new_runs",
            0,
        )
        or 0
    )

    if new_count:
        no_new_runs = 0
    else:
        no_new_runs = previous_no_new + 1

    mode = str(scan_plan.get("mode", ""))

    if mode in {
        "initial",
        "backfill",
    }:
        next_cursor = max(
            1,
            int(
                selection.get(
                    "max_scanned_position",
                    scan_plan.get(
                        "start_position",
                        1,
                    ),
                )
            )
            + 1
            - int(
                scan_plan.get(
                    "backfill_overlap_items",
                    3,
                )
            ),
        )
    else:
        next_cursor = int(
            previous.get(
                "backfill_cursor",
                1,
            )
            or 1
        )

    timestamp = now_iso()

    return {
        "state_id": state_id(
            str(scan_plan["source_id"]),
            str(scan_plan["account_id"]),
            str(scan_plan["item_type"]),
        ),
        "source_id": str(scan_plan["source_id"]),
        "account_id": str(scan_plan["account_id"]),
        "platform": platform,
        "item_type": str(scan_plan["item_type"]),
        "latest_seen_item_id": (
            latest_seen_item_id
            or str(
                previous.get(
                    "latest_seen_item_id",
                    "",
                )
            )
        ),
        "latest_seen_published_at": (
            latest_seen_published_at
            or str(
                previous.get(
                    "latest_seen_published_at",
                    "",
                )
            )
        ),
        "backfill_cursor": (next_cursor),
        "last_scanned_position": int(
            selection.get(
                "max_scanned_position",
                0,
            )
            or 0
        ),
        "last_scan_mode": mode,
        "last_scan_at": timestamp,
        "last_new_count": new_count,
        "last_duplicate_count": int(
            selection.get(
                "duplicate_count",
                0,
            )
            or 0
        ),
        "consecutive_no_new_runs": (no_new_runs),
        "updated_at": timestamp,
    }
