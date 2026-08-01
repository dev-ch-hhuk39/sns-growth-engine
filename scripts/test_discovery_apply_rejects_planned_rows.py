#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

import discover_approved_source_videos as d


config = d.load_config()

sources = d.select_discovery_sources(
    "liver_manager",
    config,
)

assert sources

source = sources[0]

planned_row = d.build_source_video_candidates(
    source,
    config,
    {
        "mode": "initial",
        "start_position": 1,
        "scan_limit": 1,
    },
)[0]

blocked_plan = d.build_discovery_plan(
    "liver_manager",
    apply=True,
    confirm_discovery=True,
    existing_source_videos=[],
    discovery_state_rows=[],
    fetch_real=False,
)

assert blocked_plan["status"] == "BLOCKED"

assert "--apply requires --fetch-real" in blocked_plan["blocked_reasons"]

assert blocked_plan["would_save_source_videos"] is False

assert not d.is_persistable_source_video(planned_row)


class NoAccessClient:
    def __getattr__(
        self,
        name,
    ):
        raise AssertionError("client must not be accessed " "for invalid rows")


try:
    d.append_source_videos_to_sheets(
        NoAccessClient(),
        [planned_row],
    )
except ValueError as exc:
    assert "non_persistable_source_videos" in str(exc)
else:
    raise AssertionError("planned row was not rejected")


real_row = d.build_source_video(
    source,
    index=1,
    video_url=("https://www.youtube.com/" "watch?v=AbCdEfGhI12"),
    title="verified",
    duration_seconds=30,
    description="verified metadata",
    discovery_status="DISCOVERED",
)

assert d.is_persistable_source_video(real_row)

print("PASS " "test_discovery_apply_rejects_" "planned_rows.py")
