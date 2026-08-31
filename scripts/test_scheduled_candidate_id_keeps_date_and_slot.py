#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate_threads_ideas_from_references import scheduled_candidate_stable_id  # noqa: E402

long_reference = "result_" + "x" * 240
first = scheduled_candidate_stable_id(
    account_id="night_scout",
    reference_id=long_reference,
    schedule_date_jst="2026-08-31",
    slot_id="ns_2500_pdca",
)
second = scheduled_candidate_stable_id(
    account_id="night_scout",
    reference_id=long_reference,
    schedule_date_jst="2026-09-01",
    slot_id="ns_2500_pdca",
)

assert "2026_08_31" in first and "ns_2500_pdca" in first, first
assert "2026_09_01" in second and "ns_2500_pdca" in second, second
assert first != second

print("PASS test_scheduled_candidate_id_keeps_date_and_slot.py")
