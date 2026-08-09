#!/usr/bin/env python3
"""A requested YouTube channel must not widen a bounded discovery run."""

from discover_approved_source_videos import build_discovery_plan


def main() -> int:
    plan = build_discovery_plan(
        "night_scout",
        source_ids=["src_ns_yt_cand_006"],
    )
    selected_ids = {row["source_id"] for row in plan["selected_sources"]}
    checks = [
        ("only requested source selected", selected_ids == {"src_ns_yt_cand_006"}),
        ("requested ID recorded", plan["requested_source_ids"] == ["src_ns_yt_cand_006"]),
        ("bounded limit retained", plan["limits"]["max_total_new_videos_per_run"] == 12),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
