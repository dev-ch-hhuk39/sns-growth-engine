#!/usr/bin/env python3
"""Night Scout and Liver Manager must retain independent account execution."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from public_post_quality import independent_account_order
from run_autonomous_loop import build_autonomous_plan

config = json.loads((ROOT / "config/autonomous_mode.json").read_text(encoding="utf-8"))
assert config["account_execution_strategy"]["cross_account_rotation"] is False
assert config["account_execution_strategy"]["max_posts_per_run_is_per_account"] is True

all_order = independent_account_order(["night_scout", "liver_manager"])
assert all_order["ordered_accounts"] == ["night_scout", "liver_manager"]
assert all_order["skipped_accounts"] == []

for account_id in ("night_scout", "liver_manager"):
    plan = build_autonomous_plan(account_id)
    assert plan["accounts"] == [account_id], plan
    assert plan["selected_account"] == account_id, plan
    assert plan["account_execution"]["strategy"] == "fixed_account_override", plan

print("PASS test_independent_account_execution.py")
