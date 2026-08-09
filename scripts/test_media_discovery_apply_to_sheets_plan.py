#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

import discover_approved_source_videos as d


def fake_real_discovery(
    source,
    config,
    scan_plan=None,
):
    platform = str(
        source.get(
            "source_platform",
            "",
        )
    )

    source_id = str(
        source.get(
            "source_id",
            "",
        )
    )

    digest = hashlib.sha256(source_id.encode("utf-8")).hexdigest()

    if platform == "youtube":
        video_id = digest[:11]
        video_url = "https://www.youtube.com/" f"watch?v={video_id}"
    else:
        video_id = str(
            int(
                digest[:16],
                16,
            )
        )
        video_url = (
            str(
                source.get(
                    "source_url",
                    "",
                )
            ).rstrip("/")
            + f"/video/{video_id}"
        )

    row = d.build_source_video(
        source,
        index=1,
        video_url=video_url,
        title="real metadata test",
        duration_seconds=30,
        description="verified test metadata",
        discovery_status="DISCOVERED",
    )

    row["source_position"] = 1
    row["discovery_mode"] = str(
        (scan_plan or {}).get(
            "mode",
            "initial",
        )
    )

    return [row], "REAL_DISCOVERY"


original_real_discovery = d.discover_source_videos_real

d.discover_source_videos_real = fake_real_discovery

try:
    plan = d.build_discovery_plan(
        "liver_manager",
        apply=True,
        confirm_discovery=True,
        existing_source_videos=[],
        discovery_state_rows=[],
        fetch_real=True,
    )
finally:
    d.discover_source_videos_real = original_real_discovery


checks = [
    (
        "apply remains blocked while discovery persistence is disabled",
        "source_video_discovery_apply_disabled" in plan["blocked_reasons"],
    ),
    (
        "apply save is not planned while disabled",
        (plan["would_save_source_videos"] is False),
    ),
    (
        "new videos available",
        plan["new_video_count"] > 0,
    ),
    (
        "all rows are persistable",
        all(d.is_persistable_source_video(row) for row in plan["new_videos"]),
    ),
    (
        "dedupe keys present",
        ("video_id" in plan["dedupe_keys"] and "canonical_video_url" in plan["dedupe_keys"]),
    ),
    (
        "approved sources only",
        all(source["source_id"].startswith("src_lm_") for source in plan["selected_sources"]),
    ),
]

failed = [name for name, ok in checks if not ok]

for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} " f"{name}")

print(f"PASS: {len(checks) - len(failed)} " f"/ FAIL: {len(failed)}")

raise SystemExit(1 if failed else 0)
