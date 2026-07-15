#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
from run_autonomous_loop import build_autonomous_plan, build_results
from types import SimpleNamespace
plan = build_autonomous_plan("night_scout", slot_id="ns_1400_reference")
rows = build_results(SimpleNamespace(apply=False, confirm_autonomous=False, account_id="night_scout"), plan)
assert any("--slot-id ns_1400_reference --post-type reference_text --theme shop_selection" in str(row.get("cmd", "")) for row in rows)
print("PASS test_text_slot_passes_slot_type_and_theme_to_generator.py")
