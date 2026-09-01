#!/usr/bin/env python3
from datetime import datetime, timezone, timedelta
from pathlib import Path

from maintain_text_ready_inventory import _generation_commands, future_text_slots, next_text_slot

jst = timezone(timedelta(hours=9))
night = next_text_slot("night_scout", now=datetime(2026, 8, 31, 13, 0, tzinfo=jst))
assert night["slot_id"] == "ns_1400_reference", night
liver = next_text_slot("liver_manager", now=datetime(2026, 8, 31, 20, 0, tzinfo=jst))
assert liver["slot_id"] == "lm_2100_pdca", liver
night_24h = future_text_slots("night_scout", now=datetime(2026, 8, 31, 13, 0, tzinfo=jst))
assert [row["slot_id"] for row in night_24h] == [
    "ns_1400_reference", "ns_1600_original", "ns_2500_pdca"
]
pdca_routes = _generation_commands("liver_manager", liver)
assert [route for route, _command in pdca_routes] == ["measured_pdca", "safe_original_fallback"]
assert "--require-measured-pdca" in pdca_routes[0][1]
fallback_command = pdca_routes[1][1]
assert fallback_command[fallback_command.index("--post-type") + 1] == "original_text"
reference_routes = _generation_commands("night_scout", night)
assert [route for route, _command in reference_routes] == ["primary", "safe_original_fallback"]
reference_fallback = reference_routes[1][1]
assert reference_fallback[reference_fallback.index("--post-type") + 1] == "original_text"
source = Path(__file__).with_name("maintain_text_ready_inventory.py").read_text(encoding="utf-8")
assert "process_threads_queue.py" not in source
assert "--autonomous-low-risk" in source
assert "QUALITY_EXHAUSTED" in source
workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/autopilot-auto-ready.yml").read_text(encoding="utf-8")
assert "maintain_text_ready_inventory.py" in workflow
assert "--text-inventory-scope" in workflow
assert "GEMINI_API_KEY" in workflow
print("PASS test_ready_inventory_maintenance_contract.py")
