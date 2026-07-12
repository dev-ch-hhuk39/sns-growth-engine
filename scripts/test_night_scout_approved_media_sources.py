#!/usr/bin/env python3
"""Ensure only explicitly authorized night_scout YouTube sources enter media autopilot."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sources = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text(encoding="utf-8"))["sources"]
config = json.loads((ROOT / "config/media_growth_engine.json").read_text(encoding="utf-8"))

EXPECTED = {f"src_ns_yt_cand_{index:03d}" for index in range(1, 10)}
rows = {row["source_id"]: row for row in sources if row.get("source_id") in EXPECTED}

checks = [
    ("all nine authorized night YouTube sources are registered", set(rows) == EXPECTED),
    ("source-level media autopilot is explicit", all(row.get("media_autopilot_enabled") is True for row in rows.values())),
    ("rights and permission evidence are present", all(row.get("rights_status") == "approved_creator_clip" and row.get("permission_status") == "approved" and row.get("permission_evidence_note") for row in rows.values())),
    ("repost scope is Threads only", all(row.get("allowed_platforms_for_repost") == ["threads"] for row in rows.values())),
    ("night sources are allowed by media config", EXPECTED.issubset(set(config.get("allowed_source_ids", []))) and "night_scout" in config.get("allowed_target_account_ids", [])),
    ("night TikTok TODO stays disabled", all(not row.get("media_autopilot_enabled") for row in sources if row.get("source_id") == "tiktok_night_scout_reference_todo")),
]

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
