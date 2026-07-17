#!/usr/bin/env python3
from discover_approved_source_videos import build_discovery_plan

def main() -> int:
    p = build_discovery_plan("liver_manager")
    yt = [r for r in p["source_results"] if r["platform"] == "youtube"]
    selected_yt = [r for r in p["selected_sources"] if r["platform"] == "youtube"]
    ok = len(yt) == len(selected_yt) and len(yt) > 0 and all(
        row["discovery_status"] == "YOUTUBE_CHANNEL_DISCOVERY_PLAN" for row in yt
    )
    print(f"  {'PASS' if ok else 'FAIL'} youtube channel discovery plan")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
