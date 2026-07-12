#!/usr/bin/env python3
from discover_approved_source_videos import build_discovery_plan
from run_media_growth_engine import build_media_growth_plan


def main() -> int:
    discovery = build_discovery_plan("night_scout")
    growth = build_media_growth_plan("night_scout")
    checks = [
        ("night discovery selects authorized sources", len(discovery["selected_sources"]) == 9),
        ("night discovery is bounded", discovery["limits"]["max_total_new_videos_per_run"] == 12),
        ("night growth plan is valid", growth["status"] == "PLAN_ONLY"),
        ("night growth creates candidates", growth["clip_candidate_count"] > 0),
        ("night candidate metadata is night-specific", all("配信初心者" not in row.get("target_audience", "") for row in growth["top_clip_candidates"])),
        ("night public text passes validator", growth["final_public_post_validator"] == "PASS"),
        ("dry-run never performs external media actions", not any(growth[key] for key in ("would_download", "would_cut", "would_upload", "would_post_video"))),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
