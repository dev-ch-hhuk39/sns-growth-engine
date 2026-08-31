#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
auto = json.loads((ROOT / "config/autonomous_mode.json").read_text(encoding="utf-8"))
media = json.loads((ROOT / "config/media_growth_engine.json").read_text(encoding="utf-8"))

assert auto["media_operations_delegated"] is True
assert auto["media_execution_authority"] == "config/media_growth_engine.json"
assert auto["allow_third_party_media"] is False
assert auto["allow_unknown_rights"] is False
assert media["media_growth_engine_enabled"] is True
assert media["media_schedule_enabled"] is True
assert media["require_permission_evidence"] is True
assert set(media["allowed_target_account_ids"]) == {"night_scout", "liver_manager", "beauty_account"}

print("PASS test_autonomous_media_delegation_contract.py")
