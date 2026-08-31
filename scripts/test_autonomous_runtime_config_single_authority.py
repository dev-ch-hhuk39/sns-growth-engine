#!/usr/bin/env python3
from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from autonomous_runtime_config import load_runtime_policy, validate_runtime_configuration  # noqa: E402

autonomous, rules = load_runtime_policy()
assert autonomous["auto_post_enabled"] is True
assert "auto_post_enabled" not in rules["defaults"]
assert not validate_runtime_configuration(autonomous, rules)

contradictory = copy.deepcopy(rules)
contradictory["defaults"]["auto_post_enabled"] = False
assert "duplicate_auto_post_authority" in validate_runtime_configuration(autonomous, contradictory)

bad_activation = copy.deepcopy(autonomous)
bad_activation["production_publish_activation_approved"] = False
assert "scheduled_publish_requires_activation_approval" in validate_runtime_configuration(bad_activation, rules)

print("PASS test_autonomous_runtime_config_single_authority.py")
