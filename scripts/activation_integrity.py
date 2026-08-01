#!/usr/bin/env python3
"""Shared read-only source-integrity contract for production activation."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(ROOT / "src"),
)

from build_live_canary_inventory import build_inventory
from final_production_contracts import (
    ACCOUNTS,
    CANARY_TYPES,
    canary_id,
    canary_source_integrity_report,
)


ACTIVATION_DATASETS = (
    "queue",
    "source_posts",
    "source_post_media",
    "media_permissions",
    "media_assets",
    "source_videos",
    "video_clip_candidates",
    "posted_results",
    "metrics_collection_jobs",
)


def empty_activation_datasets() -> dict[
    str,
    list[dict[str, Any]],
]:
    return {logical: [] for logical in ACTIVATION_DATASETS}


def load_activation_datasets(
    use_sheets: bool,
) -> tuple[
    dict[str, list[dict[str, Any]]],
    str,
]:
    """Read activation datasets without creating or modifying Sheets tabs."""

    if not use_sheets:
        return (
            empty_activation_datasets(),
            "use_sheets_required",
        )

    try:
        from config_loader import get_config
        from sheets_client import SheetsClient

        cfg = get_config()

        client = SheetsClient(
            cfg["sheet_id"],
            cfg["sa_dict"],
            dry_run=True,
        )

        datasets = {
            logical: [dict(row) for row in client._ws(logical).get_all_records()]
            for logical in ACTIVATION_DATASETS
        }

        return datasets, "READ_OK"

    except Exception as exc:
        source = (
            "SCHEMA_MISSING" if type(exc).__name__ == "WorksheetNotFound" else type(exc).__name__
        )

        return (
            empty_activation_datasets(),
            source,
        )


def evaluate_canary_integrity(
    datasets: dict[
        str,
        list[dict[str, Any]],
    ],
) -> dict[str, Any]:
    """Require one persisted, source-valid candidate for every canary slot.

    ``build_inventory`` may return placeholder rows for missing slots so that
    planning reports remain structurally complete. Activation must never treat
    those placeholders as production evidence. A selected canary therefore
    requires both a canary ID and a persisted queue ID.
    """

    inventory = build_inventory(
        datasets,
        wave="all_12",
    )

    inventory_candidates = list(
        inventory.get(
            "canaries",
            inventory.get(
                "candidates",
                [],
            ),
        )
    )

    expected_slots = {
        (
            account_id,
            kind,
        )
        for account_id in ACCOUNTS
        for kind in CANARY_TYPES
    }

    selected_candidates: list[dict[str, Any]] = []

    rejected_candidate_ids: list[str] = []

    for candidate in inventory_candidates:
        account_id = str(
            candidate.get(
                "account_id",
                "",
            )
        ).strip()

        canary_type = str(
            candidate.get(
                "canary_type",
                "",
            )
        ).strip()

        candidate_id = str(
            candidate.get(
                "canary_id",
                "",
            )
        ).strip()

        queue_id = str(
            candidate.get(
                "queue_id",
                "",
            )
        ).strip()

        slot = (
            account_id,
            canary_type,
        )

        if slot not in expected_slots or not candidate_id or not queue_id:
            if candidate_id:
                rejected_candidate_ids.append(candidate_id)

            continue

        selected_candidates.append(dict(candidate))

    report = canary_source_integrity_report(
        datasets,
        selected_candidates,
    )

    slot_counts: dict[
        tuple[str, str],
        int,
    ] = {}

    for candidate in selected_candidates:
        slot = (
            str(
                candidate.get(
                    "account_id",
                    "",
                )
            ),
            str(
                candidate.get(
                    "canary_type",
                    "",
                )
            ),
        )

        slot_counts[slot] = (
            slot_counts.get(
                slot,
                0,
            )
            + 1
        )

    present_slots = set(slot_counts)

    missing_slots = sorted(
        canary_id(
            account_id,
            kind,
        )
        for account_id, kind in expected_slots
        if (
            account_id,
            kind,
        )
        not in present_slots
    )

    duplicate_slots = sorted(
        canary_id(
            account_id,
            kind,
        )
        for (
            account_id,
            kind,
        ), count in slot_counts.items()
        if count != 1
    )

    complete = (
        report.get("status") == "PASS"
        and not missing_slots
        and not duplicate_slots
        and len(selected_candidates) == len(expected_slots)
    )

    return {
        **report,
        "status": ("PASS" if complete else "FAIL"),
        "candidate_count": len(selected_candidates),
        "inventory_candidate_count": len(inventory_candidates),
        "rejected_nonpersisted_candidate_count": (
            len(inventory_candidates) - len(selected_candidates)
        ),
        "rejected_nonpersisted_canary_ids": (sorted(set(rejected_candidate_ids))),
        "expected_candidate_count": len(expected_slots),
        "present_slot_count": len(present_slots),
        "missing_canary_slots": (missing_slots),
        "duplicate_canary_slots": (duplicate_slots),
        "inventory_status": str(
            inventory.get(
                "status",
                "",
            )
        ),
    }
