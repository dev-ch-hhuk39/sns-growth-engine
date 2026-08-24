#!/usr/bin/env python3
"""Mixed account records never leak except explicitly global facts."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from accounts.managed_accounts import filter_account_rows, require_account_match  # noqa: E402

rows = [
    {"account_id": "night_scout", "value": "night"},
    {"target_account_id": "liver_manager", "value": "liver"},
    {"pdca_account_scope": "beauty_account", "value": "beauty"},
    {"account_id": "tiktok_shop", "value": "shop"},
    {"scope": "global_fact", "value": "official fact"},
]

for account_id, expected in (
    ("night_scout", "night"),
    ("liver_manager", "liver"),
    ("beauty_account", "beauty"),
    ("tiktok_shop", "shop"),
):
    selected = filter_account_rows(rows, account_id)
    assert [row["value"] for row in selected] == [expected]
    selected_with_fact = filter_account_rows(rows, account_id, allow_global_fact=True)
    assert [row["value"] for row in selected_with_fact] == [expected, "official fact"]

for bad in ({}, {"account_id": "liver_manager"}):
    try:
        require_account_match("night_scout", bad)
    except ValueError:
        pass
    else:
        raise AssertionError(f"account mismatch was accepted: {bad}")

require_account_match("tiktok_shop", {"scope": "global_fact"}, allow_global_fact=True)
print("PASS: adversarial account isolation and global-fact exception")
