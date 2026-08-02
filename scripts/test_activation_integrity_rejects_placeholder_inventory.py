#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(ROOT / "scripts"),
)

from activation_integrity import (
    empty_activation_datasets,
    evaluate_canary_integrity,
)
from activation_route_contract import (
    ACCOUNTS,
    ACTIVATION_CANARY_TYPES,
)


report = evaluate_canary_integrity(
    empty_activation_datasets()
)

expected = (
    len(ACCOUNTS)
    * len(ACTIVATION_CANARY_TYPES)
)

assert expected == 10
assert report["status"] == "FAIL", report
assert (
    report["expected_candidate_count"]
    == expected
), report
assert report["candidate_count"] == 0, report
assert report["present_slot_count"] == 0, report
assert (
    len(report["missing_canary_slots"])
    == expected
), report
assert (
    report["inventory_candidate_count"]
    >= report["candidate_count"]
), report
assert (
    report[
        "rejected_nonpersisted_candidate_count"
    ]
    == (
        report["inventory_candidate_count"]
        - report["candidate_count"]
    )
), report

print(
    "PASS "
    "test_activation_integrity_rejects_"
    "placeholder_inventory.py"
)
