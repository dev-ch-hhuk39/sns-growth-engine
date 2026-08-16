#!/usr/bin/env python3
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from discover_approved_source_videos import build_discovery_plan  # noqa: E402
from generation.media_platform_policy import (  # noqa: E402
    PHYSICAL_MEDIA_PLATFORMS,
    normalize_platform,
)
from media.rights_policy import rights_allows_media_use  # noqa: E402


def platform_of(row: dict) -> str:
    return normalize_platform(
        row.get("source_platform")
        or row.get("platform")
        or row.get("source_platform_alias"),
        str(
            row.get("source_url")
            or row.get("canonical_url")
            or row.get("canonical_video_url")
            or ""
        ),
    )


def rights_of(row: dict) -> str:
    return str(row.get("rights_status") or row.get("rights_policy") or "")


def main() -> int:
    plan = build_discovery_plan("liver_manager")
    selected = list(plan.get("selected_sources") or [])
    results = list(plan.get("source_results") or [])

    # selected_sources is intentionally a lightweight selection view. It proves
    # which source/platform entered the physical-media planner, but does not
    # carry the enriched rights/permission fields. Those are asserted on the
    # corresponding source_results rows produced by the planner.
    result_by_source: dict[str, list[dict]] = defaultdict(list)
    for row in results:
        source_id = str(row.get("source_id") or "")
        if source_id:
            result_by_source[source_id].append(row)

    selected_ids = [str(row.get("source_id") or "") for row in selected]
    bad_selected_platform = [
        row
        for row in selected
        if platform_of(row) not in PHYSICAL_MEDIA_PLATFORMS
    ]
    missing_or_ambiguous_results = [
        source_id
        for source_id in selected_ids
        if not source_id or len(result_by_source.get(source_id, [])) != 1
    ]

    enriched_rows = [
        result_by_source[source_id][0]
        for source_id in selected_ids
        if source_id and len(result_by_source.get(source_id, [])) == 1
    ]
    bad_enriched_policy = [
        row
        for row in enriched_rows
        if platform_of(row) not in PHYSICAL_MEDIA_PLATFORMS
        or not rights_allows_media_use(rights_of(row))
        or str(row.get("permission_status") or "").lower() != "approved"
    ]

    ok = bool(selected) and not (
        bad_selected_platform
        or missing_or_ambiguous_results
        or bad_enriched_policy
    )

    if not ok:
        print(
            "selected=",
            [
                (row.get("source_id"), platform_of(row))
                for row in selected
            ],
        )
        print(
            "results=",
            [
                (
                    row.get("source_id"),
                    platform_of(row),
                    rights_of(row),
                    row.get("permission_status"),
                )
                for row in results
            ],
        )
        print("missing_or_ambiguous_results=", missing_or_ambiguous_results)

    print(
        f"  {'PASS' if ok else 'FAIL'} "
        "discover only approved physical-media sources"
    )
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
