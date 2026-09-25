#!/usr/bin/env python3
"""Production completion requires real media inventory, never text fallback."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
config = json.loads((ROOT / "config/production_inventory.json").read_text())
acceptance = (ROOT / "scripts/run_production_readiness_acceptance.py").read_text()
scheduler = (ROOT / ".github/workflows/media-preparation-scheduler.yml").read_text()
host_scheduler = (ROOT / "scripts/install_buffered_production_runtime.sh").read_text()

assert config["media_shortage_text_fallback"] is False
assert config["slot_route_cycles"]["beauty_account"]["beauty_2030"] == [
    "direct_reference_media"
]
assert "blockers.append(shortage)" in acceptance
assert "MEDIA_TEXT_FALLBACK:" in acceptance
assert "night_scout" in scheduler and "liver_manager" in scheduler
assert 'workflow_dispatch:' in scheduler and 'schedule:' not in scheduler
assert "run_buffered_media_preparation_host.sh" in host_scheduler
assert '15 5 * * *' in host_scheduler

print("PASS test_media_inventory_completion_contract.py")
