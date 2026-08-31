#!/usr/bin/env python3
from datetime import datetime, timezone, timedelta
from pathlib import Path

from maintain_text_ready_inventory import next_text_slot

jst = timezone(timedelta(hours=9))
night = next_text_slot("night_scout", now=datetime(2026, 8, 31, 13, 0, tzinfo=jst))
assert night["slot_id"] == "ns_1400_reference", night
liver = next_text_slot("liver_manager", now=datetime(2026, 8, 31, 20, 0, tzinfo=jst))
assert liver["slot_id"] == "lm_2100_pdca", liver
source = Path(__file__).with_name("maintain_text_ready_inventory.py").read_text(encoding="utf-8")
assert "process_threads_queue.py" not in source
assert "--autonomous-low-risk" in source
assert "QUALITY_EXHAUSTED" in source
workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/autopilot-auto-ready.yml").read_text(encoding="utf-8")
assert "maintain_text_ready_inventory.py" in workflow
print("PASS test_ready_inventory_maintenance_contract.py")
