#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from activation_route_contract import (
    ACCOUNTS,
    ACTIVATION_CANARY_TYPES,
    activation_slot,
    canonical_activation_type,
)
from build_bounded_media_canary_plan import (
    build_plan,
)

ROOT = Path(__file__).resolve().parents[1]

schedule = json.loads(
    (
        ROOT
        / "config/content_schedule.json"
    ).read_text(encoding="utf-8")
)

scheduled = {
    str(slot["post_type"])
    for rows in schedule[
        "accounts"
    ].values()
    for slot in rows
}

assert scheduled == set(
    ACTIVATION_CANARY_TYPES
)

assert (
    canonical_activation_type(
        "direct_video"
    )
    == "direct_reference_media"
)

assert (
    canonical_activation_type(
        "original_text",
        content_route="pdca_text",
    )
    == "pdca_text"
)

assert activation_slot(
    {
        "account_id": "night_scout",
        "canary_id": (
            "canary_fresh_old_"
            "night_scout_direct_carousel"
        ),
    }
) == (
    "night_scout",
    "direct_reference_media",
)

empty = build_plan([])

assert empty["total_canaries"] == (
    len(ACCOUNTS)
    * len(ACTIVATION_CANARY_TYPES)
)

assert empty["total_canaries"] == 10

print(
    "PASS "
    "test_activation_route_canary_contract.py"
)
